"""Self-RAG driver.

Runs the draft -> judge -> decide loop introduced in
`gitquest.run_self_rag_loop` against:

1. The `self_rag_retry` subset of `advanced_rag_cases.jsonl` (built in
   EO1) - cases where the first retrieval is intentionally too narrow.
2. A small sample of curated eval items so the lesson shows the loop on
   ordinary answer / clarify / refuse queries too.

Prints the full attempt trace per item.

Usage:
    python self_rag.py --rag-dir <path/to/rag>
"""

import argparse
import json
from functools import partial
from pathlib import Path

from gitquest import oai, run_self_rag_loop
from judge import llm_judge


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
            "expected_behavior": case["expected_behavior"],
        })
    for item in sample_eval:
        bundle.append({
            "id": item["query_id"],
            "query": item["user_query"],
            "injected_docs": [],
            "required_ids": item.get("required_citations") or item.get("gold_evidence") or [],
            "expected_behavior": item["expected_behavior"],
        })
    return bundle


def main():
    parser = argparse.ArgumentParser(description="Run the Self-RAG loop on cases and eval items.")
    parser.add_argument("--rag-dir", type=Path, default=default_rag_dir())
    parser.add_argument("--eval-sample-size", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true",
                        help="Use the offline heuristic judge. It cannot score relevance, so no "
                             "retry will ever fire. Free, deterministic, and the point of the exercise.")
    args = parser.parse_args()

    # The heuristic judge returns "not_applicable" for relevance, so --dry-run
    # shows a loop that can never decide to retry. The live judge is what makes
    # the loop work; see the module docstring in judge.py.
    judge = None if args.dry_run else partial(llm_judge, client=oai)
    print(f"judge: {'heuristic (offline, cannot score relevance)' if args.dry_run else 'llm_judge (live)'}\n")

    bundle = load_bundle(args.rag_dir / "generated_eval_artifacts",
                         eval_sample_size=args.eval_sample_size)

    for entry in bundle:
        history = run_self_rag_loop(
            query=entry["query"],
            injected_docs=entry["injected_docs"],
            required_ids=entry["required_ids"],
            expected_behavior=entry["expected_behavior"],
            judge=judge,
        )
        # Drop the heavy 'result' field from the printed trace; it's available
        # if the lesson wants to dig in but clutters the on-screen output.
        printable_history = []
        for attempt in history:
            attempt_copy = {k: v for k, v in attempt.items() if k != "result"}
            printable_history.append(attempt_copy)
        final = history[-1]
        print(json.dumps({
            "id": entry["id"],
            "query": entry["query"],
            "expected_behavior": entry["expected_behavior"],
            "attempts": len(history),
            "final_decision": final["decision"]["decision"],
            "final_reason": final["decision"]["reason"],
            "final_citations": final["citations"],
            # Reported, never acted on. Put these two side by side: an item can
            # show missing_evidence (the retrieval metric says it failed) while
            # relevance is 5 (the judge says the answer is the recommended one).
            "answer_key_missing": final["decision"]["missing_evidence"],
            "relevance": final["judgement"].get("relevance"),
            "trace": printable_history,
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
