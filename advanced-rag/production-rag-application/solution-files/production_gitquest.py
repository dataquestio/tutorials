"""Advanced RAG 4 - Production RAG Application (guided project).

Everything *inside* the pipeline (security overlay, self-RAG loop, judge,
evaluation metrics, run-log schema, monitoring helpers) was introduced in
earlier lessons. AR4 introduces the one missing piece a real production
team needs: a **shape** for wiring them together that's open to extension
without rewriting the harness every time a new failure mode shows up.

Look at how the procedural draft (and ``advanced_security.py``) handled
case dispatch:

    if case["case_type"] == "self_rag_retry":
        ...
    else:
        ...

Adding a new case type means editing the harness. As the set of case
types grows - and a real production deployment will grow it - every new
failure mode would force an edit to the orchestrator, which is exactly
the file you want to touch least often.

``ProductionHarness`` replaces those branches with a small **case-handler
registry**. The harness owns config, accumulated runs, scoring, and
reporting. Handlers are narrow: ``(case, config) -> (result, judgement)``.
Adding a new case type becomes a one-liner from outside the harness:

    harness.register_case_handler("my_new_case", my_handler)

This file also bakes in two production-flavoured additions that are
mechanically small but conceptually load-bearing:

- ``cost_per_passing_answer_usd`` - a derived metric on top of the cost
  tracking already in ``gitquest.py`` / ``monitoring.py``. ``avg_cost_usd``
  tells you what you spent; this tells you what you spent *per correct
  answer*, which is the number a budget owner actually asks for.
- ``run_canary`` - per-item paired runs across two configs. The existing
  ``regressions_by_slice`` compares aggregates; canary mode pairs the same
  input through control and variant configs so behavioural drift surfaces
  before you promote a config change.

Run with:
    python production_gitquest.py --rag-dir <path/to/rag> --limit 12 \\
        --output-log production_gitquest_run_logs.jsonl --canary
"""

import argparse
import copy
import json
import time
from pathlib import Path

from evaluate import score_item
from gitquest import (
    PIPELINE_VERSION,
    ask_gitquest_secured,
    build_run_log,
    corpus,
    run_self_rag_loop,
)
from judge import faithfulness_score, heuristic_judge
from monitoring import (
    PRODUCTION_THRESHOLDS,
    check_thresholds,
    dashboard,
    regressions_by_slice,
    summarize_runs,
)


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def default_rag_dir():
    if Path("/workspace/rag").exists():
        return Path("/workspace/rag")
    return Path("rag")


def evidence_payload(chunk_ids):
    payload = []
    for chunk_id in chunk_ids:
        if chunk_id in corpus:
            payload.append({
                "chunk_id": chunk_id,
                "title": corpus[chunk_id]["title"],
                "text": corpus[chunk_id]["text"],
            })
    return payload


# ---------------------------------------------------------------------------
# Default case handlers.
#
# Handler contract: ``(case, config) -> (result, judgement)``.
#   - ``case`` is a normalised dict with ``user_query``, ``expected_behavior``,
#     ``trusted_evidence`` (list of {"chunk_id": ...}), and optional
#     ``tags`` / ``injected_docs``.
#   - ``config`` is the harness config dict; handlers read whichever keys
#     they care about and ignore the rest.
# ---------------------------------------------------------------------------

def self_rag_retry_handler(case, config):
    trusted_ids = [ev["chunk_id"] for ev in case.get("trusted_evidence", [])]
    history = run_self_rag_loop(
        query=case["user_query"],
        required_ids=trusted_ids,
        tags=case.get("tags") or [],
        expected_behavior=case["expected_behavior"],
    )
    return history[-1]["result"], history[-1]["judgement"]


def secured_pipeline_handler(case, config):
    result = ask_gitquest_secured(
        query=case["user_query"],
        injected_docs=case.get("injected_docs"),
        n_results=config.get("candidate_k", 10),
        token_budget=config.get("token_budget", 6000),
        model=config.get("model", "gpt-4o-mini"),
    )
    trusted_ids = [ev["chunk_id"] for ev in case.get("trusted_evidence", [])]
    judgement = heuristic_judge(
        query=case["user_query"],
        answer=result["answer"],
        evidence=evidence_payload(trusted_ids),
        cited_ids=[c["chunk_id"] for c in result["citations"]],
        expected_behavior=case["expected_behavior"],
    )
    return result, judgement


class ProductionHarness:
    """Production-shaped orchestrator for the GitQuest assistant.

    Owns config, accumulated run logs, canary diffs, and the case-handler
    registry. Scoring and run-log emission live here so that handlers stay
    narrow and can be added from outside without re-implementing the
    bookkeeping.
    """

    def __init__(self, config, thresholds=PRODUCTION_THRESHOLDS):
        self.config = config
        self.thresholds = thresholds
        self.runs = []
        self.canary_runs = []
        self._case_handlers = {}
        self.register_case_handler("self_rag_retry", self_rag_retry_handler)
        self.register_case_handler("default", secured_pipeline_handler)

    def register_case_handler(self, case_type, handler):
        """Bind ``case_type`` to ``handler``. Overwrites any existing binding."""
        self._case_handlers[case_type] = handler

    def _resolve_handler(self, case_type):
        return self._case_handlers.get(case_type, self._case_handlers["default"])

    @staticmethod
    def _normalise_eval_item(item):
        trusted_ids = item.get("required_citations") or item.get("gold_evidence") or []
        return {
            "user_query": item["user_query"],
            "expected_behavior": item["expected_behavior"],
            "trusted_evidence": [{"chunk_id": cid} for cid in trusted_ids],
            "tags": item.get("tags") or [],
        }

    def run_eval_item(self, item):
        """Run a curated eval item through the registered handler and score it."""
        case_type = "self_rag_retry" if item.get("expected_behavior") == "retrieve_again" else "default"
        case = self._normalise_eval_item(item)
        result, judgement = self._resolve_handler(case_type)(case, self.config)

        metrics = score_item(item, result)
        metrics["faithfulness_score"] = faithfulness_score(judgement)
        log = build_run_log(item["query_id"], result, self.config, metrics=metrics, judgement=judgement)
        self.runs.append(log)
        return log

    def run_advanced_case(self, case):
        """Dispatch an advanced case by ``case_type`` and score it."""
        case_type = case["case_type"]
        result, judgement = self._resolve_handler(case_type)(case, self.config)

        trusted_ids = [ev["chunk_id"] for ev in case.get("trusted_evidence", [])]
        fake_eval_item = {
            "query_id": case["case_id"],
            "expected_behavior": case["expected_behavior"],
            "gold_evidence": trusted_ids,
            "required_citations": trusted_ids,
            "reference_answer": "",
        }
        metrics = score_item(fake_eval_item, result)
        metrics["faithfulness_score"] = faithfulness_score(judgement)
        log = build_run_log(case["case_id"], result, self.config, metrics=metrics, judgement=judgement)
        log["case_type"] = case_type
        self.runs.append(log)
        return log

    def run_batch(self, eval_items, advanced_cases, limit):
        for item in eval_items[:limit]:
            self.run_eval_item(item)
        for case in advanced_cases[:limit]:
            self.run_advanced_case(case)

    def run_canary(self, case, variant_config):
        """Run ``case`` through both ``self.config`` (control) and ``variant_config``
        (variant) and record a paired diff.

        Differs from ``regressions_by_slice``: that compares aggregates across
        two run sets; this pairs the *same input* across two configs so that
        per-item behavioural drift (different citation set, big cost jump,
        faithfulness regression on one specific question) becomes visible
        before a config change ships.
        """
        case_type = case.get("case_type", "default")
        handler = self._resolve_handler(case_type)

        control_result, control_judgement = handler(case, self.config)
        variant_result, variant_judgement = handler(case, variant_config)

        control_citations = [c["chunk_id"] for c in control_result["citations"]]
        variant_citations = [c["chunk_id"] for c in variant_result["citations"]]

        diff = {
            "case_id": case.get("case_id") or case.get("query_id"),
            "case_type": case_type,
            "control_config": self.config,
            "variant_config": variant_config,
            "control": {
                "answer": control_result["answer"],
                "citations": control_citations,
                "estimated_cost_usd": control_result.get("estimated_cost_usd"),
                "latency_ms": control_result.get("latency_ms"),
                "faithfulness_score": faithfulness_score(control_judgement),
            },
            "variant": {
                "answer": variant_result["answer"],
                "citations": variant_citations,
                "estimated_cost_usd": variant_result.get("estimated_cost_usd"),
                "latency_ms": variant_result.get("latency_ms"),
                "faithfulness_score": faithfulness_score(variant_judgement),
            },
            "citation_set_changed": set(control_citations) != set(variant_citations),
            "cost_delta_usd": round(
                (variant_result.get("estimated_cost_usd") or 0.0)
                - (control_result.get("estimated_cost_usd") or 0.0),
                6,
            ),
        }
        self.canary_runs.append(diff)
        return diff

    def write_logs(self, path):
        write_jsonl(path, self.runs)

    def report(self):
        summary = summarize_runs(self.runs)

        # Cost per passing answer: total cost divided by the number of
        # answers that passed answerability. Avg cost alone hides the case
        # where a cheap model returns more wrong answers - this metric
        # exposes it.
        accuracy = summary.get("answerability_accuracy") or 0.0
        passing = (summary.get("run_count") or 0) * accuracy
        total_cost = summary.get("total_cost_usd") or 0.0
        summary["cost_per_passing_answer_usd"] = (
            round(total_cost / passing, 6) if passing else None
        )

        report = {
            "run_count": len(self.runs),
            "summary": summary,
            "alerts_vs_production_slos": check_thresholds(summary, thresholds=self.thresholds),
            "dashboard": dashboard(self.runs),
            "regressions_by_slice": regressions_by_slice(self.runs, self.runs),
            "thresholds": self.thresholds,
        }
        if self.canary_runs:
            report["canary_diffs"] = self.canary_runs
        return report


def main():
    parser = argparse.ArgumentParser(description="GitQuest production harness.")
    parser.add_argument("--rag-dir", type=Path, default=default_rag_dir())
    parser.add_argument("--limit", type=int, default=8,
                        help="Number of eval items and advanced cases to run.")
    parser.add_argument("--output-log", type=Path, default=Path("production_gitquest_run_logs.jsonl"))
    parser.add_argument("--canary", action="store_true",
                        help="Also run advanced cases through a tighter-budget variant config and report diffs.")
    args = parser.parse_args()

    artifact_dir = args.rag_dir / "generated_eval_artifacts"

    config = {
        "corpus": "full",
        "candidate_k": 10,
        "rerank_top_n": 5,
        "token_budget": 6000,
        "model": "gpt-4o-mini",
        "pipeline_version": PIPELINE_VERSION,
    }

    harness = ProductionHarness(config=config)

    eval_items = read_jsonl(artifact_dir / "eval_items_curated.jsonl")
    advanced_cases = read_jsonl(artifact_dir / "advanced_rag_cases.jsonl")

    started = time.time()
    harness.run_batch(eval_items, advanced_cases, limit=args.limit)

    if args.canary:
        variant_config = copy.deepcopy(config)
        variant_config["token_budget"] = 3000
        variant_config["pipeline_version"] = f"{PIPELINE_VERSION}-canary-budget3k"
        for case in advanced_cases[: args.limit]:
            harness.run_canary(case, variant_config)

    elapsed = time.time() - started

    harness.write_logs(args.output_log)
    report = harness.report()
    report["wall_clock_seconds"] = round(elapsed, 2)

    print(f"Wrote {len(harness.runs)} run logs to {args.output_log}")
    print(json.dumps(report, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Extend the harness yourself.
#
# These are intentionally not in the solution. Each one slots into the
# existing surface (registry, report, run logs) without you having to edit
# the harness internals - that's the point of the design.
#
# A) Custom slicers.
#    ``monitoring.slice_by_tag`` only buckets by ``case_type``. Add a second
#    registry to the harness - ``register_slicer(name, fn)`` where ``fn``
#    takes a run log and returns a bucket name (e.g. query-length bucket,
#    number of citations, tag membership). Have ``report()`` expose
#    ``dashboards_by_slice`` with one dashboard per registered slicer.
#    Use it to find regressions that the case_type view hides.
#
# B) New case type: ``context_poisoning``.
#    Existing security cases attack the *input* via ``injected_docs``. Write
#    a handler that mutates ``gitquest.corpus`` directly (insert a hostile
#    chunk before retrieval, restore the original state after) and verify
#    the secured pipeline still cites trusted IDs. Register it from outside:
#    ``harness.register_case_handler("context_poisoning", your_handler)`` -
#    no edits to this file needed. Add cases of the new type to
#    ``advanced_rag_cases.jsonl`` to exercise it.
#
# C) Failure replay.
#    Add ``replay_from_log(path)`` to the harness: load a prior run-log
#    JSONL, filter to items that breached ``self.thresholds``, re-run those
#    through the current pipeline, and emit a per-item before/after diff.
#    Mirrors the real incident response loop. The interesting design
#    question this forces: how stable does the run-log schema need to be
#    for replay to work N releases later?
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    main()
