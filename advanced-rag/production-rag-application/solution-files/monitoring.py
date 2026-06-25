"""Advanced RAG 3 - Production monitoring and reliability.

Extends the EO3 monitoring helpers with production-scale concepts:

- ``PRODUCTION_THRESHOLDS`` - tighter SLOs than the EO3 defaults
- ``compare_models`` - A/B-style report across multiple named run sets
- ``time_series_drift`` - per-snapshot drift detection for a sequence of
  baselines (e.g. nightly runs)
- ``regressions_by_slice`` - per-case-type regression breakdown so the
  lesson can show "which slice broke" rather than only an overall delta

All EO3 helpers (``summarize_runs``, ``check_thresholds``,
``compare_summaries``, ``make_degraded_copy``, etc.) are preserved
unchanged so AR4's production harness can call them directly.
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


PRODUCTION_THRESHOLDS = {
    "min_answerability_accuracy": 0.97,
    "min_citation_precision": 0.95,
    "min_citation_recall": 0.90,
    "min_avg_faithfulness_score": 4.0,
    "max_p95_latency_ms": 2500,
    "max_avg_cost_usd": 0.008,
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

    def check_min(metric_key, threshold_key, alert):
        threshold = thresholds.get(threshold_key)
        value = summary.get(metric_key)
        if threshold is not None and value is not None and value < threshold:
            alerts.append(alert)

    def check_max(metric_key, threshold_key, alert):
        threshold = thresholds.get(threshold_key)
        value = summary.get(metric_key)
        if threshold is not None and value is not None and value > threshold:
            alerts.append(alert)

    check_min("answerability_accuracy", "min_answerability_accuracy", "answerability_accuracy_below_threshold")
    check_min("citation_precision", "min_citation_precision", "citation_precision_below_threshold")
    check_min("citation_recall", "min_citation_recall", "citation_recall_below_threshold")
    check_min("avg_faithfulness_score", "min_avg_faithfulness_score", "avg_faithfulness_below_threshold")
    check_max("p95_latency_ms", "max_p95_latency_ms", "p95_latency_above_threshold")
    check_max("avg_cost_usd", "max_avg_cost_usd", "avg_cost_above_threshold")
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


def compare_models(named_runs):
    """A/B-style report across multiple named run sets.

    ``named_runs`` is a dict of ``{model_name: [run, ...]}``. Returns a
    dict with per-model summaries, the metric deltas relative to the first
    model, and a list of clear winners per metric."""
    summaries = {name: summarize_runs(runs) for name, runs in named_runs.items()}
    if len(summaries) < 2:
        return {"summaries": summaries, "deltas": {}, "winners": {}}
    baseline_name = next(iter(summaries))
    baseline_summary = summaries[baseline_name]
    deltas = {}
    for name, summary in summaries.items():
        if name == baseline_name:
            continue
        deltas[name] = compare_summaries(baseline_summary, summary)

    winners = {}
    metric_keys = set()
    for summary in summaries.values():
        metric_keys |= set(summary)
    metric_keys.discard("run_count")
    for metric in sorted(metric_keys):
        values = [(name, summary.get(metric)) for name, summary in summaries.items()]
        present = [(name, value) for name, value in values if value is not None]
        if not present:
            winners[metric] = None
            continue
        if metric in {"avg_latency_ms", "p95_latency_ms", "avg_cost_usd", "total_cost_usd"}:
            winners[metric] = min(present, key=lambda kv: kv[1])[0]
        else:
            winners[metric] = max(present, key=lambda kv: kv[1])[0]
    return {"summaries": summaries, "deltas": deltas, "winners": winners}


def time_series_drift(snapshots):
    """Compute per-step drift over an ordered list of (label, runs) snapshots.

    Useful for the AR3 lesson screens that show a metric degrade across
    nightly runs. Returns a list of step dicts with the prior label, this
    label, and the metric deltas between them."""
    summaries = [(label, summarize_runs(runs)) for label, runs in snapshots]
    steps = []
    for i in range(1, len(summaries)):
        prev_label, prev_summary = summaries[i - 1]
        cur_label, cur_summary = summaries[i]
        steps.append({
            "from": prev_label,
            "to": cur_label,
            "comparison": compare_summaries(prev_summary, cur_summary),
            "regressions": regression_signals(prev_summary, cur_summary),
        })
    return {"summaries": [{"label": label, "summary": summary} for label, summary in summaries],
            "steps": steps}


def regressions_by_slice(baseline_runs, current_runs):
    """Per-case-type regression breakdown. Combines slice_by_tag with
    regression_signals so the lesson can say 'security cases regressed by X'
    rather than only producing an overall delta."""
    baseline_buckets = slice_by_tag(baseline_runs)
    current_buckets = slice_by_tag(current_runs)
    out = {}
    for slice_name in sorted(set(baseline_buckets) | set(current_buckets)):
        b = summarize_runs(baseline_buckets.get(slice_name, []))
        c = summarize_runs(current_buckets.get(slice_name, []))
        out[slice_name] = {
            "baseline_summary": b,
            "current_summary": c,
            "regressions": regression_signals(b, c),
        }
    return out


def main():
    parser = argparse.ArgumentParser(description="Summarise and compare GitQuest run logs at production scale.")
    parser.add_argument("--baseline-log", type=Path, required=True,
                        help="Path to baseline_run_logs.jsonl.")
    parser.add_argument("--current-log", type=Path, default=None,
                        help="Path to a current run log. Defaults to a degraded copy of the baseline.")
    parser.add_argument("--use-production-thresholds", action="store_true",
                        help="Check against the tighter PRODUCTION_THRESHOLDS instead of the EO3 defaults.")
    args = parser.parse_args()

    thresholds = PRODUCTION_THRESHOLDS if args.use_production_thresholds else DEFAULT_THRESHOLDS

    baseline_runs = read_jsonl(args.baseline_log)
    current_runs = read_jsonl(args.current_log) if args.current_log else make_degraded_copy(baseline_runs)

    baseline_summary = summarize_runs(baseline_runs)
    current_summary = summarize_runs(current_runs)

    report = {
        "baseline_summary": baseline_summary,
        "current_summary": current_summary,
        "comparison": compare_summaries(baseline_summary, current_summary),
        "regressions": regression_signals(baseline_summary, current_summary),
        "regressions_by_slice": regressions_by_slice(baseline_runs, current_runs),
        "baseline_alerts": check_thresholds(baseline_summary, thresholds=thresholds),
        "current_alerts": check_thresholds(current_summary, thresholds=thresholds),
        "baseline_dashboard": dashboard(baseline_runs),
        "current_dashboard": dashboard(current_runs),
        "thresholds": thresholds,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
