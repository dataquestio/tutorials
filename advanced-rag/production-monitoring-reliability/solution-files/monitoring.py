"""Advanced RAG 3 - Production Monitoring and Reliability.

Consumes Run Log entries in the 15-field shape emitted by AR4's
`production_gitquest.py` and summarized in the baseline run logs from
`build_eval_artifacts.py`. Demonstrates:

- aggregate metric summaries over a batch run (answerability accuracy,
  citation precision/recall, average faithfulness, p95 latency, average
  and total cost)
- threshold-based alerting against `DEFAULT_THRESHOLDS`
- baseline-versus-current comparison with per-metric deltas
- a deterministic `make_degraded_copy` helper that synthesizes a degraded
  current run from the baseline, so the lesson can demonstrate regressions
  without depending on live API calls

EO3's `compare_runs.py` imports `summarize_runs`, `check_thresholds`, and
`compare_summaries` from this module so both courses report identical
numbers.
"""

import argparse
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


def default_artifact_dir():
    path = Path("/workspace/rag/generated_eval_artifacts")
    if path.exists():
        return path
    return Path("generated_eval_artifacts")


def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    index = int(round((pct / 100) * (len(values) - 1)))
    return values[index]


def average(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def summarize_runs(runs):
    metrics = [run.get("metrics", {}) for run in runs]
    latencies = [run.get("latency_ms") for run in runs if run.get("latency_ms") is not None]
    costs = [run.get("estimated_cost_usd") for run in runs if run.get("estimated_cost_usd") is not None]

    answerability_values = [
        metric.get("answerability_correct")
        for metric in metrics
        if metric.get("answerability_correct") is not None
    ]
    citation_precision_values = [
        metric.get("citation_precision")
        for metric in metrics
        if metric.get("citation_precision") is not None
    ]
    citation_recall_values = [
        metric.get("citation_recall")
        for metric in metrics
        if metric.get("citation_recall") is not None
    ]
    faithfulness_values = [
        metric.get("faithfulness_score")
        for metric in metrics
        if metric.get("faithfulness_score") is not None
    ]

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
    if summary["answerability_accuracy"] is not None:
        if summary["answerability_accuracy"] < thresholds["min_answerability_accuracy"]:
            alerts.append("answerability_accuracy_below_threshold")
    if summary["citation_precision"] is not None:
        if summary["citation_precision"] < thresholds["min_citation_precision"]:
            alerts.append("citation_precision_below_threshold")
    if summary["citation_recall"] is not None:
        if summary["citation_recall"] < thresholds["min_citation_recall"]:
            alerts.append("citation_recall_below_threshold")
    if summary["p95_latency_ms"] is not None:
        if summary["p95_latency_ms"] > thresholds["max_p95_latency_ms"]:
            alerts.append("p95_latency_above_threshold")
    if summary["avg_cost_usd"] is not None:
        if summary["avg_cost_usd"] > thresholds["max_avg_cost_usd"]:
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


def make_degraded_copy(runs):
    degraded = []
    for i, run in enumerate(runs):
        copy = json.loads(json.dumps(run))
        if i % 4 == 0:
            copy["metrics"]["citation_precision"] = 0.0
            copy["citations"] = []
        if i % 5 == 0:
            copy["metrics"]["answerability_correct"] = False
        copy["latency_ms"] = int(copy.get("latency_ms", 0) * 1.8)
        degraded.append(copy)
    return degraded


def main():
    parser = argparse.ArgumentParser(description="Summarize and compare GitQuest production run logs.")
    parser.add_argument("--artifact-dir", type=Path, default=default_artifact_dir())
    parser.add_argument("--current-log", type=Path, default=None)
    args = parser.parse_args()

    baseline_path = args.artifact_dir / "baseline_run_logs_draft.jsonl"
    baseline_runs = read_jsonl(baseline_path)
    current_runs = read_jsonl(args.current_log) if args.current_log else make_degraded_copy(baseline_runs)

    baseline_summary = summarize_runs(baseline_runs)
    current_summary = summarize_runs(current_runs)
    report = {
        "baseline_summary": baseline_summary,
        "current_summary": current_summary,
        "comparison": compare_summaries(baseline_summary, current_summary),
        "baseline_alerts": check_thresholds(baseline_summary),
        "current_alerts": check_thresholds(current_summary),
        "thresholds": DEFAULT_THRESHOLDS,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
