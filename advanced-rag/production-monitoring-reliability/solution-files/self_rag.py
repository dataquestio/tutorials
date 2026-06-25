"""Advanced RAG 2 - Self-RAG driver.

Runs the draft -> judge -> decide loop introduced in
``gitquest.run_self_rag_loop`` against:

1. The ``self_rag_retry`` subset of ``advanced_rag_cases.jsonl`` (built in
   EO1) - cases where the first retrieval is intentionally too narrow.
2. A small sample of curated eval items so the lesson shows the loop on
   ordinary answer / clarify / refuse queries too.

Prints the full attempt trace per item.

Usage:
    python self_rag.py --rag-dir <path/to/rag>
"""

import argparse
import json
from pathlib import Path

from gitquest import run_self_rag_loop


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def default_rag_dir():
    if Path("/workspace/rag").exists():
        return Path("/workspace/rag")
    return Path("rag")


def load_bundle(artifact_dir, eval_sample_size=4):
    advanced_cases = read_jsonl(artifact_dir / "advanced_rag_cases.jsonl")
    self_rag_cases = [c for c in advanced_cases if c["case_type"] == "self_rag_retry"]

    eval_items = read_jsonl(artifact_dir / "eval_items_curated.jsonl")
    sample_eval = [
        item for item in eval_items
        if item["expected_behavior"] in {"answer", "clarify", "refuse"}
    ][:eval_sample_size]

    bundle = []
    for case in self_rag_cases:
        bundle.append({
            "id": case["case_id"],
            "query": case["user_query"],
            "injected_docs": case.get("injected_docs") or [],
            "required_ids": [ev["chunk_id"] for ev in case.get("trusted_evidence", [])],
            "tags": case.get("tags") or [],
            "expected_behavior": case["expected_behavior"],
        })
    for item in sample_eval:
        bundle.append({
            "id": item["query_id"],
            "query": item["user_query"],
            "injected_docs": [],
            "required_ids": item.get("required_citations") or item.get("gold_evidence") or [],
            "tags": item.get("tags") or [],
            "expected_behavior": item["expected_behavior"],
        })
    return bundle


def main():
    parser = argparse.ArgumentParser(description="Run the Advanced RAG 2 Self-RAG loop on cases and eval items.")
    parser.add_argument("--rag-dir", type=Path, default=default_rag_dir())
    parser.add_argument("--eval-sample-size", type=int, default=4)
    args = parser.parse_args()

    bundle = load_bundle(args.rag_dir / "generated_eval_artifacts",
                         eval_sample_size=args.eval_sample_size)

    for entry in bundle:
        history = run_self_rag_loop(
            query=entry["query"],
            injected_docs=entry["injected_docs"],
            required_ids=entry["required_ids"],
            tags=entry["tags"],
            expected_behavior=entry["expected_behavior"],
        )
        # Drop the heavy 'result' field from the printed trace; it's available
        # if the lesson wants to dig in but clutters the on-screen output.
        printable_history = []
        for attempt in history:
            attempt_copy = {k: v for k, v in attempt.items() if k != "result"}
            printable_history.append(attempt_copy)
        print(json.dumps({
            "id": entry["id"],
            "query": entry["query"],
            "expected_behavior": entry["expected_behavior"],
            "attempts": len(history),
            "final_decision": history[-1]["decision"]["decision"],
            "final_reason": history[-1]["decision"]["reason"],
            "final_citations": history[-1]["citations"],
            "trace": printable_history,
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
