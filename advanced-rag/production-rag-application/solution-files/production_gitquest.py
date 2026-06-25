"""Advanced RAG 4 - Production RAG Application (guided project).

Small production-style harness for the GitQuest assistant. AR4 is
practice: every component used here was introduced earlier in the path.

The harness:

1. Loads the curated eval set and Advanced RAG cases (built in EO1).
2. Runs each item through ``ask_gitquest_secured`` (introduced in AR1) and
   the self-RAG decision loop (introduced in AR2) for cases that benefit.
3. Scores every run with the evaluation metrics (introduced in EO1) and
   the heuristic judge (introduced in EO2).
4. Emits 15-field Run Log entries (introduced in EO3).
5. Summarises the batch with the production monitoring helpers
   (introduced in EO3 and extended in AR3) and prints alerts against the
   production SLOs.

Run with:
    python production_gitquest.py --rag-dir <path/to/rag> --limit 12 \\
        --output-log production_gitquest_run_logs.jsonl
"""

import argparse
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


def run_eval_item(item, config):
    """Run a curated eval item through the secured pipeline and score it.

    Items marked ``retrieve_again`` get the self-RAG loop; everything else
    gets a single secured-pipeline call so the harness is fast."""
    if item.get("expected_behavior") == "retrieve_again":
        history = run_self_rag_loop(
            query=item["user_query"],
            required_ids=item.get("required_citations") or item.get("gold_evidence") or [],
            tags=item.get("tags") or [],
            expected_behavior=item["expected_behavior"],
        )
        result = history[-1]["result"]
        judgement = history[-1]["judgement"]
    else:
        result = ask_gitquest_secured(query=item["user_query"])
        judgement = heuristic_judge(
            query=item["user_query"],
            answer=result["answer"],
            evidence=evidence_payload(item.get("gold_evidence") or []),
            cited_ids=[c["chunk_id"] for c in result["citations"]],
            expected_behavior=item["expected_behavior"],
        )

    metrics = score_item(item, result)
    metrics["faithfulness_score"] = faithfulness_score(judgement)
    return build_run_log(item["query_id"], result, config, metrics=metrics, judgement=judgement)


def run_advanced_case(case, config):
    """Run an Advanced RAG case (security overlay, self-RAG retry, etc.)."""
    if case["case_type"] == "self_rag_retry":
        history = run_self_rag_loop(
            query=case["user_query"],
            required_ids=[ev["chunk_id"] for ev in case.get("trusted_evidence", [])],
            tags=case.get("tags") or [],
            expected_behavior=case["expected_behavior"],
        )
        result = history[-1]["result"]
        judgement = history[-1]["judgement"]
    else:
        result = ask_gitquest_secured(
            query=case["user_query"],
            injected_docs=case.get("injected_docs"),
        )
        judgement = heuristic_judge(
            query=case["user_query"],
            answer=result["answer"],
            evidence=evidence_payload([ev["chunk_id"] for ev in case.get("trusted_evidence", [])]),
            cited_ids=[c["chunk_id"] for c in result["citations"]],
            expected_behavior=case["expected_behavior"],
        )

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
    log = build_run_log(case["case_id"], result, config, metrics=metrics, judgement=judgement)
    log["case_type"] = case["case_type"]
    return log


def main():
    parser = argparse.ArgumentParser(description="GitQuest production harness.")
    parser.add_argument("--rag-dir", type=Path, default=default_rag_dir())
    parser.add_argument("--limit", type=int, default=8,
                        help="Number of eval items and advanced cases to run.")
    parser.add_argument("--output-log", type=Path, default=Path("production_gitquest_run_logs.jsonl"))
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

    eval_items = read_jsonl(artifact_dir / "eval_items_curated.jsonl")
    advanced_cases = read_jsonl(artifact_dir / "advanced_rag_cases.jsonl")

    started = time.time()
    runs = []
    for item in eval_items[: args.limit]:
        runs.append(run_eval_item(item, config))
    for case in advanced_cases[: args.limit]:
        runs.append(run_advanced_case(case, config))
    elapsed = time.time() - started

    write_jsonl(args.output_log, runs)

    summary = summarize_runs(runs)
    report = {
        "run_count": len(runs),
        "wall_clock_seconds": round(elapsed, 2),
        "summary": summary,
        "alerts_vs_production_slos": check_thresholds(summary, thresholds=PRODUCTION_THRESHOLDS),
        "dashboard": dashboard(runs),
        "regressions_by_slice": regressions_by_slice(runs, runs),  # baseline vs itself = no regressions
        "thresholds": PRODUCTION_THRESHOLDS,
    }

    print(f"Wrote {len(runs)} run logs to {args.output_log}")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
