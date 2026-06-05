"""Evaluating LLM Outputs 3 - Production Evaluation and Observability.

Walkthrough script for batch evaluation, regression detection, and cost/latency
tracking against the shared Run Log contract.

Reuses the summarize/threshold/compare functions from the AR3 monitoring
module so both lessons report identical numbers. The lesson-specific work in
this script is:

1. Slicing runs by tag (cmd:remote, security, self_rag, monitoring) to show
   disaggregated metrics.
2. Detecting which metric tripped a regression between baseline and current.
3. Printing a small "production dashboard" view the lesson can render.
"""

import argparse
import collections
import json
import os
import sys


# Reuse AR3's monitoring helpers so both courses agree on the math.
MONITORING = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "advanced-rag", "production-monitoring-reliability", "solution-files",
))
if MONITORING not in sys.path:
    sys.path.insert(0, MONITORING)

from monitoring import (  # noqa: E402
    check_thresholds,
    compare_summaries,
    make_degraded_copy,
    read_jsonl,
    summarize_runs,
)


def default_rag_dir():
    if os.path.exists("/workspace/rag"):
        return "/workspace/rag"
    return "rag"


def slice_by_tag(runs, tag_prefix):
    """Group runs by the first tag matching tag_prefix. Run logs do not carry
    tags themselves, so we look at the case_type field for advanced cases and
    the query_id prefix for eval items."""
    buckets = collections.defaultdict(list)
    for run in runs:
        case_type = run.get("case_type")
        if case_type:
            buckets[case_type].append(run)
        else:
            buckets["eval_item"].append(run)
    if tag_prefix is None:
        return dict(buckets)
    return {k: v for k, v in buckets.items() if k.startswith(tag_prefix)}


def regression_signals(baseline_summary, current_summary):
    """Return the metrics that got materially worse between baseline and current."""
    comparison = compare_summaries(baseline_summary, current_summary)
    worsened = []
    for metric, values in comparison.items():
        delta = values.get("delta")
        if delta is None:
            continue
        if metric in {"avg_latency_ms", "p95_latency_ms", "avg_cost_usd", "total_cost_usd"}:
            if delta > 0:
                worsened.append({"metric": metric, "delta": delta})
        else:
            if delta < 0:
                worsened.append({"metric": metric, "delta": delta})
    return worsened


def dashboard(runs):
    """Cheap text dashboard: one line per slice with key numbers."""
    sliced = slice_by_tag(runs, None)
    rows = []
    for slice_name in sorted(sliced):
        summary = summarize_runs(sliced[slice_name])
        rows.append({
            "slice": slice_name,
            "n": summary["run_count"],
            "answerability_accuracy": summary["answerability_accuracy"],
            "citation_precision": summary["citation_precision"],
            "citation_recall": summary["citation_recall"],
            "avg_faithfulness_score": summary["avg_faithfulness_score"],
            "p95_latency_ms": summary["p95_latency_ms"],
            "avg_cost_usd": summary["avg_cost_usd"],
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Compare baseline and current run logs.")
    parser.add_argument("--rag-dir", default=default_rag_dir())
    parser.add_argument("--current-log", default=None,
                        help="Path to a current run-log JSONL. Defaults to a degraded copy of the baseline.")
    args = parser.parse_args()

    baseline_path = os.path.join(args.rag_dir, "generated_eval_artifacts", "baseline_run_logs_draft.jsonl")
    baseline_runs = read_jsonl(baseline_path)
    if args.current_log:
        current_runs = read_jsonl(args.current_log)
    else:
        current_runs = make_degraded_copy(baseline_runs)

    baseline_summary = summarize_runs(baseline_runs)
    current_summary = summarize_runs(current_runs)

    report = {
        "baseline_summary": baseline_summary,
        "current_summary": current_summary,
        "baseline_alerts": check_thresholds(baseline_summary),
        "current_alerts": check_thresholds(current_summary),
        "regressions": regression_signals(baseline_summary, current_summary),
        "baseline_dashboard": dashboard(baseline_runs),
        "current_dashboard": dashboard(current_runs),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
