"""Advanced RAG 4 - Production RAG Application.

Small harness that consumes the shared evaluation artifacts, runs them through
the Advanced GitQuest pipeline, scores each run against the shared evaluation
contract, and emits the 15-field Run Log entries used by Advanced RAG 3
(monitoring) and the future Evaluating LLM Outputs 3 lesson.

By default the harness runs offline using the deterministic generator and
heuristic judge in tutorials/advanced-rag/_shared/. Pass real Cohere/OpenAI
clients to AdvancedGitQuest to drive it live.
"""

import argparse
import json
import os
import sys


SHARED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "_shared"))
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

from evaluation import score_run
from gitquest_advanced import AdvancedGitQuest, build_run_log, default_config
from judge import faithfulness_score, heuristic_judge


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def default_rag_dir():
    if os.path.exists("/workspace/rag"):
        return "/workspace/rag"
    return "rag"


def evidence_payload(corpus, chunk_ids):
    payload = []
    for chunk_id in chunk_ids:
        if chunk_id in corpus:
            payload.append({
                "chunk_id": chunk_id,
                "title": corpus[chunk_id]["title"],
                "text": corpus[chunk_id]["text"],
            })
    return payload


def run_eval_item(app, item):
    gold = item.get("gold_evidence") or []
    required = item.get("required_citations") or gold
    outcome = app.run(
        query=item["user_query"],
        trusted_ids=gold,
        expected_behavior=item["expected_behavior"],
    )
    evidence = evidence_payload(app.corpus, gold)
    judgement = heuristic_judge(
        query=item["user_query"],
        answer=outcome["answer"],
        evidence=evidence,
        cited_ids=outcome["citations"],
        expected_behavior=item["expected_behavior"],
    )
    metrics = score_run(
        expected_behavior=item["expected_behavior"],
        answer=outcome["answer"],
        citations=outcome["citations"],
        required_citations=required,
        gold_evidence=gold,
        final_chunk_ids=[c["chunk_id"] for c in outcome["final_chunks"]],
        faithfulness_score=faithfulness_score(judgement),
    )
    log = build_run_log(item["query_id"], outcome, app.config, metrics)
    log["judgement"] = judgement
    return log


def run_advanced_case(app, case):
    trusted_ids = [evidence["chunk_id"] for evidence in case.get("trusted_evidence", [])]
    outcome = app.run(
        query=case["user_query"],
        trusted_ids=trusted_ids,
        injected_docs=case.get("injected_docs"),
        expected_behavior=case["expected_behavior"],
    )
    evidence = evidence_payload(app.corpus, trusted_ids)
    judgement = heuristic_judge(
        query=case["user_query"],
        answer=outcome["answer"],
        evidence=evidence,
        cited_ids=outcome["citations"],
        expected_behavior=case["expected_behavior"],
    )
    metrics = score_run(
        expected_behavior=case["expected_behavior"],
        answer=outcome["answer"],
        citations=outcome["citations"],
        required_citations=trusted_ids,
        gold_evidence=trusted_ids,
        final_chunk_ids=[c["chunk_id"] for c in outcome["final_chunks"]],
        faithfulness_score=faithfulness_score(judgement),
    )
    log = build_run_log(case["case_id"], outcome, app.config, metrics)
    log["case_type"] = case["case_type"]
    log["judgement"] = judgement
    return log


def main():
    parser = argparse.ArgumentParser(description="Run a small production-style GitQuest harness.")
    parser.add_argument("--rag-dir", default=default_rag_dir())
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--output-log",
        default="production_gitquest_run_logs.jsonl",
    )
    args = parser.parse_args()

    artifact_dir = os.path.join(args.rag_dir, "generated_eval_artifacts")
    corpus_path = os.path.join(args.rag_dir, "git_kb_corpus_full", "corpus.jsonl")

    app = AdvancedGitQuest(corpus_path=corpus_path, config=default_config())

    eval_items = read_jsonl(os.path.join(artifact_dir, "eval_items_curated_draft.jsonl"))
    advanced_cases = read_jsonl(os.path.join(artifact_dir, "advanced_rag_cases_draft.jsonl"))

    runs = []
    for item in eval_items[: args.limit]:
        runs.append(run_eval_item(app, item))
    for case in advanced_cases[: args.limit]:
        runs.append(run_advanced_case(app, case))

    write_jsonl(args.output_log, runs)
    print(f"Wrote {len(runs)} run logs to {args.output_log}")
    print(json.dumps(runs[:2], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
