"""Build the nyc311 snapshot from the full NYC Open Data 311 export.

Outputs, written to --out-dir (the learner dataset folder, which holds only these
CSV files; this script and its README stay out of it):
  service_requests.csv  raw rows, Jun 1 to Aug 31 2026, reduced columns
  resolutions.csv       lookup for resolution_id -> resolution text
  daily_counts.csv      requests per date, problem, borough, all years

Usage:
  python build_nyc311.py --source 311_Service_Requests_from_2020_to_Present_20260929.csv --out-dir <data>/nyc311
"""

import argparse
import collections
import csv
from pathlib import Path

# source header -> snapshot header
RAW_COLUMNS = {
    "Unique Key": "unique_key",
    "Created Date": "created_date",
    "Closed Date": "closed_date",
    "Agency": "agency",
    "Problem (formerly Complaint Type)": "problem",
    "Problem Detail (formerly Descriptor)": "problem_detail",
    "Additional Details": "additional_details",
    "Location Type": "location_type",
    "Incident Zip": "incident_zip",
    "Borough": "borough",
    "Status": "status",
    "Resolution Description": "resolution_id",
    "Community Board": "community_board",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Open Data Channel Type": "channel",
}
SUMMER_MONTHS = {"06", "07", "08"}
SUMMER_YEAR = "2026"


def iso_date(created):
    # "09/28/2026 02:05:27 AM" -> "2026-09-28"
    return f"{created[6:10]}-{created[0:2]}-{created[3:5]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out-dir", required=True, help="Learner dataset folder, e.g. data/nyc311")
    args = parser.parse_args()
    out = Path(args.out_dir)

    resolutions = {}  # text -> id
    counts = collections.Counter()
    stats = collections.Counter()

    with open(args.source, newline="", encoding="utf-8", errors="replace") as src, \
         open(out / "service_requests.csv", "w", newline="", encoding="utf-8") as raw:
        reader = csv.DictReader(src)
        writer = csv.writer(raw)
        writer.writerow(RAW_COLUMNS.values())
        for row in reader:
            stats["rows_read"] += 1
            created = row["Created Date"]
            if len(created) < 10:
                stats["rows_without_created_date"] += 1
                continue
            counts[(iso_date(created), row["Problem (formerly Complaint Type)"], row["Borough"])] += 1

            if created[6:10] == SUMMER_YEAR and created[0:2] in SUMMER_MONTHS:
                text = row["Resolution Description"]
                if text:
                    rid = resolutions.setdefault(text, len(resolutions) + 1)
                else:
                    rid = ""
                values = [row[c] for c in RAW_COLUMNS]
                values[list(RAW_COLUMNS).index("Resolution Description")] = rid
                writer.writerow(values)
                stats["summer_rows_written"] += 1

    with open(out / "resolutions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["resolution_id", "resolution_text"])
        for text, rid in sorted(resolutions.items(), key=lambda kv: kv[1]):
            writer.writerow([rid, text])

    with open(out / "daily_counts.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "problem", "borough", "request_count"])
        for (date, problem, borough), n in sorted(counts.items()):
            writer.writerow([date, problem, borough, n])

    stats["resolution_texts"] = len(resolutions)
    stats["daily_count_rows"] = len(counts)
    for k, v in stats.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
