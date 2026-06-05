import argparse
import json
from pathlib import Path


DECISION_ORDER = ["answer", "clarify", "refuse", "retrieve_again"]


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


def evidence_ids(item):
    if "trusted_evidence" in item:
        return [e["chunk_id"] for e in item.get("trusted_evidence", [])]
    return item.get("gold_evidence") or []


def decide_next_action(item, retrieved_ids=None, judge_score=None):
    retrieved_ids = set(retrieved_ids or [])
    expected_behavior = item.get("expected_behavior")
    expected_answerability = item.get("expected_answerability")
    needed_evidence = set(evidence_ids(item))

    if expected_behavior in {"retrieve_again_if_initial_evidence_missing", "retrieve_again_when_missing_cherry_pick"}:
        if not needed_evidence or not needed_evidence.issubset(retrieved_ids):
            return {
                "decision": "retrieve_again",
                "reason": "Required evidence is missing from the current retrieval set.",
                "missing_evidence": sorted(needed_evidence - retrieved_ids),
            }

    if expected_answerability == "unanswerable" or expected_behavior == "refuse":
        return {
            "decision": "refuse",
            "reason": "The evaluation item is marked unanswerable or unsupported by evidence.",
            "missing_evidence": [],
        }

    if expected_answerability == "needs_clarification" or expected_behavior == "clarify":
        return {
            "decision": "clarify",
            "reason": "The query lacks enough detail for a safe, specific answer.",
            "missing_evidence": [],
        }

    if judge_score is not None and judge_score < 3:
        return {
            "decision": "retrieve_again",
            "reason": "Draft answer judge score is too low for a reliable final answer.",
            "missing_evidence": [],
        }

    if needed_evidence and not needed_evidence.issubset(retrieved_ids):
        return {
            "decision": "retrieve_again",
            "reason": "Gold evidence is known but not present in retrieval results.",
            "missing_evidence": sorted(needed_evidence - retrieved_ids),
        }

    return {
        "decision": "answer",
        "reason": "Required evidence is available and the item is answerable.",
        "missing_evidence": [],
    }


def make_retry_query(item):
    query = item["user_query"]
    tags = set(item.get("tags", []))
    if "cmd:remote" in tags:
        return f"{query} remote URL set-url origin"
    if "cmd:cherry-pick" in tags:
        return f"{query} git cherry-pick apply commit"
    if "cmd:restore" in tags:
        return f"{query} git restore staged index"
    return f"{query} official Git command syntax"


def evaluate_self_rag_cases(items):
    rows = []
    for item in items:
        ids = evidence_ids(item)
        simulated_first_retrieval = ids[:0] if "self_rag" in item.get("tags", []) else ids
        first = decide_next_action(item, retrieved_ids=simulated_first_retrieval)
        retry_query = make_retry_query(item) if first["decision"] == "retrieve_again" else None
        second = None
        if retry_query:
            second = decide_next_action(item, retrieved_ids=ids)
        rows.append({
            "id": item.get("case_id") or item.get("query_id"),
            "query": item["user_query"],
            "first_decision": first,
            "retry_query": retry_query,
            "second_decision": second,
            "expected_behavior": item.get("expected_behavior"),
        })
    return rows


def load_items(artifact_dir):
    eval_items = read_jsonl(artifact_dir / "eval_items_curated_draft.jsonl")
    advanced_cases = read_jsonl(artifact_dir / "advanced_rag_cases_draft.jsonl")
    self_rag_cases = [case for case in advanced_cases if case["case_type"] == "self_rag_retry"]
    sample_eval_items = [
        item for item in eval_items
        if item["expected_behavior"] in {"answer", "clarify", "refuse"}
    ][:12]
    return self_rag_cases + sample_eval_items


def main():
    parser = argparse.ArgumentParser(description="Run deterministic Self-RAG decision examples.")
    parser.add_argument("--artifact-dir", type=Path, default=default_artifact_dir())
    args = parser.parse_args()

    rows = evaluate_self_rag_cases(load_items(args.artifact_dir))
    for row in rows:
        print(json.dumps(row, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
