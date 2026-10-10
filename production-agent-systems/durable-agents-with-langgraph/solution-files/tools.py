"""Tools for the earthquake feed monitor.

Two kinds of tools live here:

- General tools (files, Python, shell), the same ones a data analysis agent uses.
- Feed tools that read one day of the USGS feed, keep the running catalog
  up to date, and record what the agent found.

Every tool returns a dict. When something goes wrong, the tool returns
{"error": "..."} instead of raising, so the model can read the problem and
react to it.
"""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import skills

RUN_TIMEOUT_SECONDS = 60
MAX_TOOL_OUTPUT_CHARS = 6_000

# Set by run_agent before the first tool call.
WORKSPACE = None

# Feed tools keep their files here, relative to the workspace.
STATE_FOLDER = "state"
CATALOG_FILE = "state/catalog.jsonl"
FLAGS_FILE = "state/flags.jsonl"
PROGRESS_FILE = "state/progress.md"
ALERTS_FILE = "state/alerts.jsonl"


def resolve_in_workspace(path):
    """Turn a path from the model into a path inside the workspace.

    The path is normalized (so "a/../.." collapses) but symlinks are not
    followed. That keeps the data/ link usable while refusing anything that
    climbs out of the workspace.
    """
    workspace = os.path.abspath(WORKSPACE)
    full = os.path.abspath(os.path.join(workspace, path))
    if os.path.commonpath([workspace, full]) != workspace:
        raise ValueError(f"Path is outside the workspace: {path}")
    return Path(full)


# ---------------------------------------------------------------------------
# General tools
# ---------------------------------------------------------------------------

def list_files(path="."):
    """List the files and folders in a workspace directory."""
    try:
        folder = resolve_in_workspace(path)
        entries = []
        for entry in sorted(folder.iterdir()):
            if entry.is_dir():
                entries.append({"name": entry.name + "/", "type": "dir"})
            else:
                entries.append({"name": entry.name, "type": "file", "bytes": entry.stat().st_size})
        return {"path": path, "entries": entries}
    except Exception as e:
        return {"error": str(e)}


def read_file(path, start_line=1, max_lines=50):
    """Read a slice of lines from a text file."""
    try:
        lines = []
        with open(resolve_in_workspace(path), encoding="utf-8", errors="replace") as f:
            for number, line in enumerate(f, start=1):
                if number < start_line:
                    continue
                if len(lines) == max_lines:
                    return {"path": path, "lines": lines, "next_line": number}
                lines.append(line.rstrip("\n"))
        return {"path": path, "lines": lines, "next_line": None}
    except Exception as e:
        return {"error": str(e)}


def write_file(path, content):
    """Create or overwrite a text file in the workspace."""
    try:
        target = resolve_in_workspace(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}


def safe_env():
    """The environment for commands the agent runs, without any secrets."""
    return {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_TOKEN"))}


def run_command(command, shell):
    try:
        completed = subprocess.run(
            command, shell=shell, cwd=WORKSPACE, env=safe_env(),
            capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS,
        )
        return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired:
        return {"error": f"Timed out after {RUN_TIMEOUT_SECONDS} seconds"}
    except Exception as e:
        return {"error": str(e)}


def run_python(code):
    """Run a Python script in the workspace. Only printed output comes back."""
    return run_command([sys.executable, "-c", code], shell=False)


def run_shell(command):
    """Run a shell command in the workspace."""
    return run_command(command, shell=True)


# ---------------------------------------------------------------------------
# Feed tools
# ---------------------------------------------------------------------------

def read_day_rows(day):
    with open(resolve_in_workspace(f"data/days/{day}.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def day_summary(day):
    """Summarize one day of the feed without loading it into the conversation."""
    try:
        rows = read_day_rows(day)
    except FileNotFoundError:
        return {"error": f"No feed file for {day}"}
    except Exception as e:
        return {"error": str(e)}

    columns = list(rows[0].keys()) if rows else []
    by_status, by_type = {}, {}
    for row in rows:
        by_status[row.get("status", "")] = by_status.get(row.get("status", ""), 0) + 1
        by_type[row.get("type", "")] = by_type.get(row.get("type", ""), 0) + 1
    mags = [m for m in (to_float(r.get("mag")) for r in rows) if m is not None]
    largest = sorted(
        (r for r in rows if to_float(r.get("mag")) is not None),
        key=lambda r: to_float(r["mag"]), reverse=True,
    )[:5]
    return {
        "day": day,
        "rows": len(rows),
        "columns": columns,
        "by_status": by_status,
        "by_type": by_type,
        "mag_min": min(mags) if mags else None,
        "mag_max": max(mags) if mags else None,
        "largest": [{"id": r["id"], "mag": r["mag"], "place": r["place"], "status": r["status"]} for r in largest],
    }


def load_catalog():
    path = resolve_in_workspace(CATALOG_FILE)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {event["id"]: event for event in map(json.loads, f)}


def save_catalog(catalog):
    """Write the whole catalog to a temporary file, then swap it in.

    A crash can never leave a half-written catalog behind: the old file
    stays in place until the new one is complete.
    """
    path = resolve_in_workspace(CATALOG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for event in catalog.values():
            f.write(json.dumps(event) + "\n")
    os.replace(tmp, path)


def apply_day_to_catalog(day):
    """Merge one day of the feed into the running catalog.

    New ids are added, rows for known ids replace the stored version, and
    deletion notices mark the event as deleted. Applying the same day twice
    changes nothing the second time.
    """
    try:
        rows = read_day_rows(day)
    except FileNotFoundError:
        return {"error": f"No feed file for {day}"}
    except Exception as e:
        return {"error": str(e)}

    catalog = load_catalog()
    new, revised, deleted, unchanged = [], [], [], 0
    for row in rows:
        event_id = row.get("id")
        if not event_id:
            continue
        old = catalog.get(event_id)
        if old and old["updated"] == row.get("updated"):
            unchanged += 1
            continue
        event = {
            "id": event_id,
            "time": row.get("time"),
            "mag": to_float(row.get("mag")),
            "latitude": to_float(row.get("latitude")),
            "longitude": to_float(row.get("longitude")),
            "depth": to_float(row.get("depth")),
            "place": row.get("place"),
            "type": row.get("type"),
            "status": row.get("status"),
            "updated": row.get("updated"),
            "first_seen": old["first_seen"] if old else day,
            "versions": (old["versions"] + 1) if old else 1,
        }
        if event["status"] == "deleted":
            # Keep what we knew about the event, but mark it deleted.
            if old:
                event = {**old, "status": "deleted", "updated": event["updated"], "versions": event["versions"]}
            deleted.append(event_id)
        elif old is None:
            new.append(event)
        else:
            change = None
            if old["mag"] is not None and event["mag"] is not None:
                change = round(event["mag"] - old["mag"], 2)
            revised.append({"id": event_id, "mag_before": old["mag"], "mag_after": event["mag"], "mag_change": change})
        catalog[event_id] = event
    save_catalog(catalog)

    big_revisions = sorted(
        (r for r in revised if r["mag_change"] is not None),
        key=lambda r: abs(r["mag_change"]), reverse=True,
    )[:10]
    largest_new = sorted((e for e in new if e["mag"] is not None), key=lambda e: e["mag"], reverse=True)[:10]
    return {
        "day": day,
        "new_events": len(new),
        "largest_new_events": [
            {"id": e["id"], "mag": e["mag"], "status": e["status"], "place": e["place"], "time": e["time"]}
            for e in largest_new
        ],
        "revised_events": len(revised),
        "deleted_events": len(deleted),
        "unchanged_rows": unchanged,
        "largest_revisions": big_revisions,
        "deleted_ids": deleted[:20],
        "catalog_size": len(catalog),
    }


def append_jsonl(relative_path, record):
    path = resolve_in_workspace(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def flag_anomaly(day, kind, details, event_ids=None):
    """Record something unusual for a human to look at later."""
    try:
        record = {"day": day, "kind": kind, "details": details, "event_ids": event_ids or []}
        append_jsonl(FLAGS_FILE, record)
        return {"flagged": record}
    except Exception as e:
        return {"error": str(e)}


def append_progress(text):
    """Add a note to the progress log that the next run will read."""
    try:
        path = resolve_in_workspace(PROGRESS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
        return {"appended_chars": len(text)}
    except Exception as e:
        return {"error": str(e)}


def send_alert(message, event_ids=None):
    """Send an alert to the people on call. Needs human approval by default."""
    try:
        append_jsonl(ALERTS_FILE, {"message": message, "event_ids": event_ids or []})
        return {"sent": True}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def tool(fn, description, properties, required):
    """Pair a function with the schema the model sees."""
    return {
        "schema": {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        },
        "fn": fn,
    }


DAY = {"type": "string", "description": "Feed day as YYYY-MM-DD"}

TOOLS = {
    "list_files": tool(list_files, "List files and folders in a workspace directory.",
                       {"path": {"type": "string"}}, []),
    "read_file": tool(read_file, "Read up to max_lines lines of a text file, starting at start_line.",
                      {"path": {"type": "string"}, "start_line": {"type": "integer"}, "max_lines": {"type": "integer"}},
                      ["path"]),
    "write_file": tool(write_file, "Create or overwrite a text file in the workspace.",
                       {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "run_python": tool(run_python, "Run a Python script with the workspace as working directory. Print what you need.",
                       {"code": {"type": "string"}}, ["code"]),
    "run_shell": tool(run_shell, "Run a shell command with the workspace as working directory.",
                      {"command": {"type": "string"}}, ["command"]),
    "load_skill": tool(skills.load_skill, "Load the full instructions of a skill by name.",
                       {"name": {"type": "string"}}, ["name"]),
    "day_summary": tool(day_summary, "Summarize one day of the earthquake feed: row count, columns, statuses, types, largest events.",
                        {"day": DAY}, ["day"]),
    "apply_day_to_catalog": tool(apply_day_to_catalog, "Merge one day of the feed into the running catalog and report new, revised, and deleted events.",
                                 {"day": DAY}, ["day"]),
    "flag_anomaly": tool(flag_anomaly, "Record an anomaly for a human to review.",
                         {"day": DAY, "kind": {"type": "string", "description": "Short category, e.g. large_event"},
                          "details": {"type": "string"},
                          "event_ids": {"type": "array", "items": {"type": "string"}}},
                         ["day", "kind", "details"]),
    "append_progress": tool(append_progress, "Append a short note to state/progress.md for future runs.",
                            {"text": {"type": "string"}}, ["text"]),
    "send_alert": tool(send_alert, "Send an alert to the on-call team about events that need attention now.",
                       {"message": {"type": "string"}, "event_ids": {"type": "array", "items": {"type": "string"}}},
                       ["message"]),
}


def tool_schemas():
    """The tool definitions to send with every model call."""
    return [t["schema"] for t in TOOLS.values()]


def call_tool(name, arguments):
    """Run a tool by name. Unknown tools and bad arguments come back as errors."""
    if name not in TOOLS:
        return {"error": f"Unknown tool: {name}"}
    try:
        return TOOLS[name]["fn"](**arguments)
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}


def format_result(result):
    """Serialize a tool result for the model, cut to a fixed size."""
    text = json.dumps(result)
    if len(text) > MAX_TOOL_OUTPUT_CHARS:
        cut = len(text) - MAX_TOOL_OUTPUT_CHARS
        text = text[:MAX_TOOL_OUTPUT_CHARS] + f"... [truncated {cut} characters; print less or summarize]"
    return text
