"""Build the usgs snapshots for Course 2.

Step 1 (--fetch) downloads the frozen raw snapshot once into raw/:
  raw/events_2026-06.csv, raw/events_2026-07.csv, raw/events_2026-08.csv
  raw/deleted.csv
Step 2 (default) turns raw/ into two learner-facing datasets:
  <clean-out>/days/YYYY-MM-DD.csv   what the feed "published" each day
  <gp-out>/days/YYYY-MM-DD.csv      same feed with planted data quality issues
  <gp-out>/planted_issues.jsonl     answer key for the planted issues

Everything after the fetch is deterministic (fixed seed).

Usage:
  python build_usgs.py --fetch --clean-out <data>/usgs --gp-out <data>/usgs_gp
  python build_usgs.py --clean-out <data>/usgs --gp-out <data>/usgs_gp
"""

import argparse
import copy
import csv
import json
import random
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "raw"
API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
MONTHS = [("2026-06-01", "2026-07-01"), ("2026-07-01", "2026-08-01"), ("2026-08-01", "2026-09-01")]
FIRST_DAY, LAST_DAY = date(2026, 6, 1), date(2026, 8, 31)
SEED = 20260601
REVISION_SHARE = 0.12
MAX_REVISION_DELAY_DAYS = 5


def fetch():
    RAW.mkdir(exist_ok=True)
    for start, end in MONTHS:
        url = f"{API}?format=csv&orderby=time-asc&starttime={start}&endtime={end}"
        (RAW / f"events_{start[:7]}.csv").write_bytes(urllib.request.urlopen(url, timeout=300).read())
    url = f"{API}?format=csv&orderby=time-asc&includedeleted=only&starttime={MONTHS[0][0]}&endtime={MONTHS[-1][1]}"
    (RAW / "deleted.csv").write_bytes(urllib.request.urlopen(url, timeout=300).read())


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def parse_ts(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def fmt_ts(value):
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def published_at(event_time, day_offset, rng):
    """A publication timestamp day_offset days after the event, a few minutes past it."""
    return fmt_ts(event_time + timedelta(days=day_offset, minutes=rng.randint(2, 50)))


def perturb(row, rng):
    """The first, automatic version of an event that is later reviewed."""
    first = dict(row)
    first["status"] = "automatic"
    if first["mag"]:
        first["mag"] = f"{float(first['mag']) + rng.choice([-1, 1]) * rng.uniform(0.1, 0.4):.2f}"
    first["latitude"] = f"{float(first['latitude']) + rng.uniform(-0.08, 0.08):.4f}"
    first["longitude"] = f"{float(first['longitude']) + rng.uniform(-0.08, 0.08):.4f}"
    if first["depth"]:
        first["depth"] = f"{max(0.0, float(first['depth']) + rng.uniform(-3, 3)):.2f}"
    for column in ("nst", "gap", "dmin", "rms", "horizontalError", "depthError", "magError", "magNst"):
        first[column] = ""
    return first


def build_clean():
    rng = random.Random(SEED)
    fieldnames, events = None, []
    for start, _ in MONTHS:
        fieldnames, rows = read_csv(RAW / f"events_{start[:7]}.csv")
        events.extend(rows)
    _, deleted = read_csv(RAW / "deleted.csv")

    days = {FIRST_DAY + timedelta(days=i): [] for i in range((LAST_DAY - FIRST_DAY).days + 1)}
    stats = {"events": len(events), "revised": 0, "revisions_after_window": 0,
             "deleted_raw": len(deleted), "deleted_published": 0}

    def publish(day, row):
        if day in days:
            days[day].append(row)
            return True
        return False

    for row in events:
        event_time = parse_ts(row["time"])
        day = event_time.date()
        final = dict(row)
        if row["status"] == "reviewed" and rng.random() < REVISION_SHARE:
            real_delay = (parse_ts(row["updated"]) - event_time).days
            delay = min(max(1, real_delay), MAX_REVISION_DELAY_DAYS)
            first = perturb(row, rng)
            first["updated"] = published_at(event_time, 0, rng)
            publish(day, first)
            final["updated"] = published_at(event_time, delay, rng)
            stats["revised"] += 1
            if not publish(day + timedelta(days=delay), final):
                stats["revisions_after_window"] += 1
        else:
            final["updated"] = published_at(event_time, 0, rng)
            publish(day, final)

    # Deleted events: the feed first shows an automatic event, then a deletion
    # notice on the day the real deletion happened. Rows without an id cannot
    # be matched to anything, so they are left out.
    for row in deleted:
        if not row["id"]:
            continue
        event_time = parse_ts(row["time"])
        delay = max(1, (parse_ts(row["updated"]) - event_time).days)
        if event_time.date() + timedelta(days=delay) > LAST_DAY:
            continue
        first = {name: row.get(name, "") for name in fieldnames}
        first["status"] = "automatic"
        first["type"] = "earthquake"
        first["updated"] = published_at(event_time, 0, rng)
        notice = {name: row.get(name, "") for name in fieldnames}
        notice["updated"] = published_at(event_time, delay, rng)
        publish(event_time.date(), first)
        publish(event_time.date() + timedelta(days=delay), notice)
        stats["deleted_published"] += 1

    for rows in days.values():
        rows.sort(key=lambda r: r["updated"])
    return fieldnames, days, stats


def write_days(out_dir, headers, days):
    folder = Path(out_dir) / "days"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.csv"):
        old.unlink()
    for day, rows in days.items():
        if rows is None:
            continue
        with open(folder / f"{day.isoformat()}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers[day])
            writer.writeheader()
            writer.writerows(rows)


def plant_issues(fieldnames, clean_days):
    """Copy the clean feed and plant known data quality issues. Returns days, headers, answer key."""
    rng = random.Random(SEED + 1)
    days = copy.deepcopy(clean_days)
    headers = {day: list(fieldnames) for day in days}
    issues = []

    def add(issue_type, day, **details):
        issues.append({"issue_id": f"issue_{len(issues) + 1:02d}", "type": issue_type,
                       "day": day.isoformat(), "details": details})

    # 1. A day that never arrives.
    missing = date(2026, 6, 19)
    days[missing] = None
    add("missing_day", missing)

    # 2. A day that arrives twice: the next day's file repeats it.
    repeated, duplicate = date(2026, 7, 2), date(2026, 7, 3)
    days[duplicate] = copy.deepcopy(days[repeated])
    add("duplicate_day", duplicate, duplicate_of=repeated.isoformat())

    # 3. Depth reported in meters instead of kilometers for three days.
    for offset in range(3):
        day = date(2026, 7, 14) + timedelta(days=offset)
        for row in days[day]:
            if row["depth"]:
                row["depth"] = f"{float(row['depth']) * 1000:.1f}"
        add("depth_unit_change", day, column="depth", unit="meters")

    # 4. Out-of-range values on individual rows.
    planted_values = [
        (date(2026, 6, 10), "mag", "12.3"),
        (date(2026, 6, 27), "latitude", "-97.5"),
        (date(2026, 7, 23), "longitude", "212.4"),
        (date(2026, 8, 12), "mag", "-4.8"),
    ]
    for day, column, value in planted_values:
        row = rng.choice([r for r in days[day] if r["status"] != "deleted" and r[column]])
        row[column] = value
        add("out_of_range", day, event_id=row["id"], column=column, value=value)

    # 5. The same event reported again under another network's id.
    for day in [date(2026, 6, 8), date(2026, 7, 9), date(2026, 7, 28), date(2026, 8, 17), date(2026, 8, 26)]:
        candidates = [r for r in days[day] if r["status"] == "reviewed" and r["net"] in ("us", "ak", "ci", "nc")]
        original = rng.choice(candidates)
        twin = dict(original)
        twin["net"] = "ew"
        twin["id"] = f"ew{rng.randint(10**9, 10**10 - 1)}"
        twin["time"] = fmt_ts(parse_ts(original["time"]) + timedelta(seconds=rng.uniform(0.5, 4)))
        twin["locationSource"] = twin["magSource"] = "ew"
        days[day].append(twin)
        add("cross_network_duplicate", day, event_id=twin["id"], duplicate_of=original["id"])

    # 6. A sudden drop in volume, as if an upstream feed failed.
    drop = date(2026, 8, 21)
    expected = len(days[drop])
    days[drop] = rng.sample(days[drop], k=max(1, expected // 10))
    add("volume_drop", drop, rows_published=len(days[drop]), rows_expected=expected)

    # 7. A column renamed partway through the window. Planted last so the
    # earlier issues can refer to the original column name.
    renamed_from = date(2026, 8, 5)
    for day in headers:
        if day >= renamed_from:
            headers[day] = ["magnitude" if name == "mag" else name for name in headers[day]]
            for row in days[day] or []:
                row["magnitude"] = row.pop("mag")
    add("renamed_column", renamed_from, old_name="mag", new_name="magnitude", through=LAST_DAY.isoformat())

    for issue in issues:
        issue["source"] = "planted"
    issues.extend(find_real_issues(days, issues))
    issues.sort(key=lambda issue: (issue["day"], issue["type"], json.dumps(issue["details"], sort_keys=True)))
    for number, issue in enumerate(issues, start=1):
        issue["issue_id"] = f"issue_{number:02d}"
    return days, headers, issues


VALID_RANGES = {"mag": (-2.0, 10.0), "magnitude": (-2.0, 10.0), "latitude": (-90.0, 90.0), "longitude": (-180.0, 180.0)}


def find_real_issues(days, planted):
    """Problems that were already in the USGS data, so a monitor that flags them is not penalized.

    Same rules as the reference monitor: values outside VALID_RANGES, and rows
    from different networks within 5 seconds and 0.1 degrees of each other.
    """
    planted_keys = {(i["day"], i["details"].get("event_id")) for i in planted}
    found = []
    for day, rows in days.items():
        if rows is None:
            continue
        key_day = day.isoformat()
        for row in rows:
            for column, (low, high) in VALID_RANGES.items():
                try:
                    value = float(row.get(column) or "")
                except ValueError:
                    continue
                if not low <= value <= high and (key_day, row["id"]) not in planted_keys:
                    found.append({"type": "out_of_range", "day": key_day, "source": "real",
                                  "details": {"event_id": row["id"], "column": column, "value": row[column]}})
        events = sorted(
            (parse_ts(r["time"]), float(r["latitude"]), float(r["longitude"]), r)
            for r in rows if r["status"] != "deleted" and r["latitude"] and r["longitude"]
        ) if rows else []
        for i, (t1, lat1, lon1, a) in enumerate(events):
            for t2, lat2, lon2, b in events[i + 1:]:
                if (t2 - t1).total_seconds() > 5:
                    break
                if a["net"] != b["net"] and a["id"] != b["id"] and abs(lat1 - lat2) <= 0.1 and abs(lon1 - lon2) <= 0.1 \
                        and (key_day, b["id"]) not in planted_keys and (key_day, a["id"]) not in planted_keys:
                    found.append({"type": "cross_network_duplicate", "day": key_day, "source": "real",
                                  "details": {"event_id": b["id"], "duplicate_of": a["id"]}})
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="Download raw/ from the USGS API (run once)")
    parser.add_argument("--clean-out", required=True, help="Learner dataset folder for the lessons, e.g. data/usgs")
    parser.add_argument("--gp-out", required=True, help="Learner dataset folder for the GP, e.g. data/usgs_gp")
    args = parser.parse_args()

    if args.fetch:
        fetch()
        return

    fieldnames, clean_days, stats = build_clean()
    write_days(args.clean_out, {day: fieldnames for day in clean_days}, clean_days)
    gp_days, headers, issues = plant_issues(fieldnames, clean_days)
    write_days(args.gp_out, headers, gp_days)
    with open(Path(args.gp_out) / "planted_issues.jsonl", "w", encoding="utf-8") as f:
        for issue in issues:
            f.write(json.dumps(issue) + "\n")

    stats["clean_rows"] = sum(len(rows) for rows in clean_days.values())
    stats["gp_rows"] = sum(len(rows) for rows in gp_days.values() if rows is not None)
    stats["planted_issues"] = len(issues)
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
