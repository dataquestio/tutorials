"""Evaluate the monitor on a fixed suite of days and catch regressions.

Every case is one day. Before the run, the catalog is rebuilt up to the day
before, so each case starts from the same state no matter what ran earlier.
The expected outcome is computed from the data, not from the model:

- new events of magnitude 6.0 or higher must be flagged
- events that meet the alert policy must have an alert request queued
- apply_day_to_catalog must be called exactly once for the day
- the agent must leave a progress note for the day

Metrics come from the trace log and the state files:

    task_success        all four checks pass
    tool_call_accuracy  tool calls that were allowed, succeeded, and not redundant / all tool calls
    steps, tokens       per case

A regression is a candidate configuration that is worse than the baseline
by more than a threshold on any metric.

Usage:
    python evaluate_agent.py run --data-dir <path/to/usgs> --variant baseline --repeats 2 --out results/baseline.json
    python evaluate_agent.py run --data-dir <path/to/usgs> --variant max_steps_4 --repeats 2 --out results/max_steps_4.json
    python evaluate_agent.py compare results/baseline.json results/max_steps_4.json
"""

import argparse
import csv
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

import skills
import tools
from agent import AgentConfig
from run import prepare_workspace
from runner import load_state, run_day

SUITE_DAYS = ["2026-06-07", "2026-06-10", "2026-06-16", "2026-06-24"]
FIRST_FEED_DAY = "2026-06-01"
FLAG_MAGNITUDE = 6.0

# Each variant is a configuration change someone might make.
VARIANTS = {
    "baseline": {},
    "no_skills": {"skills_dir": "none"},     # the skills folder went missing in a refactor
    "max_steps_4": {"max_steps": 4},          # someone cut the step limit to save money
}

# How much worse a candidate may be before it counts as a regression.
THRESHOLDS = {
    "task_success_rate": -0.0,          # any drop
    "mean_tool_call_accuracy": -0.10,
    "mean_tokens": 0.30,                # +30% relative
    "mean_steps": 0.30,
}


def rebuild_catalog_until(workspace: Path, day: str) -> None:
    """Apply every feed day before `day` to the catalog, without the model."""
    tools.WORKSPACE = workspace
    current = date.fromisoformat(FIRST_FEED_DAY)
    while current < date.fromisoformat(day):
        tools.apply_day_to_catalog(current.isoformat())
        current += timedelta(days=1)


def expected_outcome(workspace: Path, day: str) -> dict:
    """What a correct run must do on this day, computed from the data."""
    tools.WORKSPACE = workspace
    known = tools.load_catalog()
    flag_ids, alert_ids = set(), set()
    with open(workspace / "data" / "days" / f"{day}.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mag = tools.to_float(row["mag"])
            if row["id"] in known or mag is None or row["status"] == "deleted":
                continue
            if mag >= FLAG_MAGNITUDE:
                flag_ids.add(row["id"])
            if (row["status"] == "reviewed" and mag >= 7.0) or (row["status"] == "automatic" and mag >= 7.5):
                alert_ids.add(row["id"])
    return {"flag_ids": sorted(flag_ids), "alert_ids": sorted(alert_ids)}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def score_case(day: str, workspace: Path, trace_path: Path, expected: dict) -> dict:
    """Turn one run's trace and state into metrics."""
    events = read_jsonl(trace_path)
    calls = [e for e in events if e["type"] == "tool_call"]
    results = [e for e in events if e["type"] == "tool_result"]
    # A denied alert is the expected outcome in an unattended run (it is queued
    # for a human), so it is not a bad call. Every other error is.
    errors = sum(1 for e in results if e["is_error"] and e["tool"] != "send_alert")
    applies = [e for e in calls if e["tool"] == "apply_day_to_catalog" and e["args"].get("day") == day]
    redundant = max(0, len(applies) - 1)

    flagged = {i for f in read_jsonl(workspace / "state" / "flags.jsonl") for i in f.get("event_ids", [])}
    state = load_state(workspace / "state", day)
    alert_requests = {i for p in state["pending_approvals"] if p["tool"] == "send_alert"
                      for i in p["args"].get("event_ids", [])}
    progress = (workspace / "state" / "progress.md").read_text(encoding="utf-8") if (workspace / "state" / "progress.md").exists() else ""
    agent_notes = [line for line in progress.splitlines() if day in line and not line.startswith("[runner]")]

    checks = {
        "applied_once": len(applies) == 1,
        "flagged_large_events": set(expected["flag_ids"]) <= flagged,
        "queued_required_alerts": set(expected["alert_ids"]) <= alert_requests,
        "left_progress_note": bool(agent_notes),
    }
    bad_calls = errors + redundant
    model_calls = [e for e in events if e["type"] in ("model_call", "compaction")]
    return {
        "day": day,
        "checks": checks,
        "task_success": all(checks.values()),
        "tool_calls": len(calls),
        "tool_call_accuracy": round(1 - bad_calls / len(calls), 3) if calls else 0.0,
        "steps": sum(1 for e in events if e["type"] == "model_call"),
        "tokens": sum((e["input_tokens"] or 0) + (e["output_tokens"] or 0) for e in model_calls),
        "missed_flags": sorted(set(expected["flag_ids"]) - flagged),
        "missed_alerts": sorted(set(expected["alert_ids"]) - alert_requests),
    }


def run_suite(data_dir: Path, variant: str, model: str, trace_dir: Path, client=None, repeats: int = 1) -> dict:
    """Run every suite day `repeats` times with one variant. Traces are kept in trace_dir.

    The same day can pass on one run and fail on the next. Repeating each
    case shows how much of a difference between variants is just noise.
    """
    overrides = dict(VARIANTS[variant])
    skills_dir = overrides.pop("skills_dir", None)
    original_skills_dir = skills.SKILLS_DIR
    trace_dir = Path(trace_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        if skills_dir == "none":
            skills.SKILLS_DIR = Path(tmp) / "no-skills"
        try:
            for repeat in range(1, repeats + 1):
                for day in SUITE_DAYS:
                    workspace = Path(tmp) / f"{day}_run{repeat}"
                    prepare_workspace(workspace, data_dir)
                    rebuild_catalog_until(workspace, day)
                    expected = expected_outcome(workspace, day)
                    trace_path = trace_dir / f"{variant}_{day}_run{repeat}.jsonl"
                    trace_path.unlink(missing_ok=True)
                    config = AgentConfig(model=model, workspace=workspace, trace_path=trace_path, **overrides)
                    run_day(day, workspace / "state", config, client)
                    case = {**score_case(day, workspace, trace_path, expected), "repeat": repeat}
                    cases.append(case)
                    print(f"  {day} run {repeat}: success={case['task_success']} accuracy={case['tool_call_accuracy']} "
                          f"steps={case['steps']} tokens={case['tokens']} missed_flags={case['missed_flags']}")
        finally:
            skills.SKILLS_DIR = original_skills_dir

    n = len(cases)
    return {
        "variant": variant,
        "model": model,
        "cases": cases,
        "summary": {
            "task_success_rate": sum(c["task_success"] for c in cases) / n,
            "mean_tool_call_accuracy": round(sum(c["tool_call_accuracy"] for c in cases) / n, 3),
            "mean_steps": sum(c["steps"] for c in cases) / n,
            "mean_tokens": sum(c["tokens"] for c in cases) / n,
        },
    }


def find_regressions(baseline: dict, candidate: dict) -> list[str]:
    """Compare two suite results metric by metric."""
    found = []
    b, c = baseline["summary"], candidate["summary"]
    for metric in ("task_success_rate", "mean_tool_call_accuracy"):
        if c[metric] - b[metric] < THRESHOLDS[metric]:
            found.append(f"{metric}: {b[metric]} -> {c[metric]}")
    for metric in ("mean_tokens", "mean_steps"):
        if b[metric] and (c[metric] - b[metric]) / b[metric] > THRESHOLDS[metric]:
            found.append(f"{metric}: {b[metric]:.0f} -> {c[metric]:.0f}")
    return found


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--data-dir", required=True)
    run_parser.add_argument("--variant", choices=list(VARIANTS), default="baseline")
    run_parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", "gpt-6-luna"))
    run_parser.add_argument("--repeats", type=int, default=1, help="Runs per suite day")
    run_parser.add_argument("--out", required=True)
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("baseline")
    compare_parser.add_argument("candidate")
    args = parser.parse_args()

    if args.command == "run":
        print(f"Running suite with variant '{args.variant}'")
        results = run_suite(Path(args.data_dir), args.variant, args.model, Path(args.out).parent / "traces",
                            repeats=args.repeats)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print("Summary:", results["summary"])
    else:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
        regressions = find_regressions(baseline, candidate)
        print(f"Baseline:  {baseline['variant']} {baseline['summary']}")
        print(f"Candidate: {candidate['variant']} {candidate['summary']}")
        if regressions:
            print("REGRESSION:")
            for line in regressions:
                print("  -", line)
            raise SystemExit(1)
        print("No regression.")
