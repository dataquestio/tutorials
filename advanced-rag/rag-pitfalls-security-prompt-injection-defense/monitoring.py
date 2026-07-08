"""Evaluating LLM Outputs 3 - Production monitoring helpers.

Consumes Run Log entries in the 15-field shape emitted by EO3's
``gitquest.build_run_log``. Demonstrates:

- aggregate metric summaries over a batch run (answerability accuracy,
  citation precision/recall, average faithfulness, p95 latency, average
  and total cost)
- threshold-based alerting against ``DEFAULT_THRESHOLDS``
- baseline-versus-current comparison with per-metric deltas
- a deterministic ``make_degraded_copy`` helper that synthesises a
  degraded current run from the baseline so the lesson can demonstrate
  regressions without depending on live API calls

The Advanced RAG monitoring lesson ships its own copy of this module
that adds production wiring on top.
"""

import argparse
import collections
import json
from pathlib import Path


DEFAULT_THRESHOLDS = {
    "min_answerability_accuracy": 0.95,
    "min_citation_precision": 0.90,
    "min_citation_recall": 0.85,
    "max_p95_latency_ms": 3000,
    "max_avg_cost_usd": 0.01,
}


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    index = int(round((pct / 100) * (len(values) - 1)))
    return values[index]


def average(values):
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def summarize_runs(runs):
    metrics = [run.get("metrics", {}) for run in runs]
    latencies = [run.get("latency_ms") for run in runs if run.get("latency_ms") is not None]
    costs = [run.get("estimated_cost_usd") for run in runs if run.get("estimated_cost_usd") is not None]

    answerability_values = [m.get("answerability_correct") for m in metrics if m.get("answerability_correct") is not None]
    citation_precision_values = [m.get("citation_precision") for m in metrics if m.get("citation_precision") is not None]
    citation_recall_values = [m.get("citation_recall") for m in metrics if m.get("citation_recall") is not None]
    faithfulness_values = [m.get("faithfulness_score") for m in metrics if m.get("faithfulness_score") is not None]

    return {
        "run_count": len(runs),
        "answerability_accuracy": average([1.0 if v else 0.0 for v in answerability_values]),
        "citation_precision": average(citation_precision_values),
        "citation_recall": average(citation_recall_values),
        "avg_faithfulness_score": average(faithfulness_values),
        "avg_latency_ms": average(latencies),
        "p95_latency_ms": percentile(latencies, 95),
        "avg_cost_usd": average(costs),
        "total_cost_usd": sum(costs) if costs else None,
    }


def check_thresholds(summary, thresholds=None):
    thresholds = thresholds or DEFAULT_THRESHOLDS
    alerts = []
    if summary["answerability_accuracy"] is not None and summary["answerability_accuracy"] < thresholds["min_answerability_accuracy"]:
        alerts.append("answerability_accuracy_below_threshold")
    if summary["citation_precision"] is not None and summary["citation_precision"] < thresholds["min_citation_precision"]:
        alerts.append("citation_precision_below_threshold")
    if summary["citation_recall"] is not None and summary["citation_recall"] < thresholds["min_citation_recall"]:
        alerts.append("citation_recall_below_threshold")
    if summary["p95_latency_ms"] is not None and summary["p95_latency_ms"] > thresholds["max_p95_latency_ms"]:
        alerts.append("p95_latency_above_threshold")
    if summary["avg_cost_usd"] is not None and summary["avg_cost_usd"] > thresholds["max_avg_cost_usd"]:
        alerts.append("avg_cost_above_threshold")
    return alerts


def compare_summaries(baseline, current):
    comparisons = {}
    for key in sorted(set(baseline) | set(current)):
        if key == "run_count":
            continue
        old = baseline.get(key)
        new = current.get(key)
        if old is None or new is None:
            comparisons[key] = {"baseline": old, "current": new, "delta": None}
        else:
            comparisons[key] = {"baseline": old, "current": new, "delta": new - old}
    return comparisons


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


def slice_by_tag(runs):
    """Group runs by case_type (advanced cases) or by 'eval_item' otherwise."""
    buckets = collections.defaultdict(list)
    for run in runs:
        case_type = run.get("case_type")
        buckets[case_type or "eval_item"].append(run)
    return dict(buckets)


def dashboard(runs):
    """Cheap text dashboard: one row per slice with key numbers."""
    sliced = slice_by_tag(runs)
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


def make_degraded_copy(runs):
    """Synthesise a degraded current run from the baseline, deterministically.

    Useful for the lesson screens that demonstrate regression alerts
    without depending on live API calls."""
    degraded = []
    for i, run in enumerate(runs):
        copy = json.loads(json.dumps(run))
        if i % 4 == 0:
            copy.setdefault("metrics", {})["citation_precision"] = 0.0
            copy["citations"] = []
        if i % 5 == 0:
            copy.setdefault("metrics", {})["answerability_correct"] = False
        if copy.get("latency_ms") is not None:
            copy["latency_ms"] = int(copy["latency_ms"] * 1.8)
        degraded.append(copy)
    return degraded


def main():
    parser = argparse.ArgumentParser(description="Summarise and compare GitQuest run logs.")
    parser.add_argument("--baseline-log", type=Path, required=True,
                        help="Path to baseline_run_logs.jsonl.")
    parser.add_argument("--current-log", type=Path, default=None,
                        help="Path to a current run log. Defaults to a degraded copy of the baseline.")
    args = parser.parse_args()

    baseline_runs = read_jsonl(args.baseline_log)
    current_runs = read_jsonl(args.current_log) if args.current_log else make_degraded_copy(baseline_runs)

    baseline_summary = summarize_runs(baseline_runs)
    current_summary = summarize_runs(current_runs)

    report = {
        "baseline_summary": baseline_summary,
        "current_summary": current_summary,
        "comparison": compare_summaries(baseline_summary, current_summary),
        "regressions": regression_signals(baseline_summary, current_summary),
        "baseline_alerts": check_thresholds(baseline_summary),
        "current_alerts": check_thresholds(current_summary),
        "baseline_dashboard": dashboard(baseline_runs),
        "current_dashboard": dashboard(current_runs),
        "thresholds": DEFAULT_THRESHOLDS,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
