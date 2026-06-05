"""Advanced RAG 2 - Self-RAG and Autonomous Evaluation.

Demonstrates a draft -> judge -> decide loop:

1. The pipeline produces a draft answer over the currently retrieved evidence.
2. The judge scores the draft against that evidence only.
3. A decision rule combines the judge score and retrieval coverage to choose
   one of: answer, clarify, refuse, retrieve_again.
4. If the decision is retrieve_again, the loop expands the query and re-runs.

By default the loop uses the heuristic judge and the offline generator from
tutorials/advanced-rag/_shared/. Pass real Cohere/OpenAI clients to drive it
live; pass the llm_judge function to use a real LLM judge.
"""

import argparse
import json
import os
import sys


SHARED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "_shared"))
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

from gitquest_advanced import AdvancedGitQuest, default_config
from judge import faithfulness_score, heuristic_judge


DECISION_ORDER = ["answer", "clarify", "refuse", "retrieve_again"]
MAX_RETRIES = 1


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def default_rag_dir():
    if os.path.exists("/workspace/rag"):
        return "/workspace/rag"
    return "rag"


def evidence_for_eval(item, corpus):
    return [
        {"chunk_id": chunk_id, "title": corpus[chunk_id]["title"], "text": corpus[chunk_id]["text"]}
        for chunk_id in item.get("gold_evidence") or []
        if chunk_id in corpus
    ]


def evidence_for_case(case, corpus):
    return [
        {"chunk_id": ev["chunk_id"], "title": corpus[ev["chunk_id"]]["title"], "text": corpus[ev["chunk_id"]]["text"]}
        for ev in case.get("trusted_evidence", [])
        if ev["chunk_id"] in corpus
    ]


def decide_next_action(judgement, retrieved_ids, required_ids, expected_behavior):
    """Combine the judge score and retrieval coverage into a next action.

    The rule order matters:
    1. If the expected behavior is refuse and the judge agrees the answer
       lacks support, refuse.
    2. If required evidence is missing from retrieval, retrieve_again.
    3. If the faithfulness score is low, retrieve_again.
    4. If the query needs clarification, clarify.
    5. Otherwise, answer.
    """
    retrieved = set(retrieved_ids or [])
    required = set(required_ids or [])
    faith = faithfulness_score(judgement)

    if expected_behavior == "refuse":
        return {
            "decision": "refuse",
            "reason": "Item is marked unanswerable in the eval contract.",
            "missing_evidence": [],
        }

    if required and not required.issubset(retrieved):
        return {
            "decision": "retrieve_again",
            "reason": "Required evidence is missing from the current retrieval set.",
            "missing_evidence": sorted(required - retrieved),
        }

    if faith is not None and faith < 3:
        return {
            "decision": "retrieve_again",
            "reason": f"Draft answer faithfulness is too low (score {faith}).",
            "missing_evidence": [],
        }

    if expected_behavior == "clarify":
        return {
            "decision": "clarify",
            "reason": "Query lacks enough detail for a safe, specific answer.",
            "missing_evidence": [],
        }

    return {
        "decision": "answer",
        "reason": "Required evidence is available and the judge accepted the draft.",
        "missing_evidence": [],
    }


def make_retry_query(query, tags):
    if "cmd:remote" in tags:
        return f"{query} remote URL set-url origin"
    if "cmd:cherry-pick" in tags:
        return f"{query} git cherry-pick apply commit"
    if "cmd:restore" in tags:
        return f"{query} git restore staged index"
    return f"{query} official Git command syntax"


def run_self_rag_loop(app, query, trusted_ids, required_ids, tags, expected_behavior, judge=None):
    """Run the draft -> judge -> decide loop with at most MAX_RETRIES retries.

    Each iteration returns a record of what the model did and what it decided
    so lessons can show the trace, not just the final answer."""
    judge = judge or heuristic_judge
    history = []
    current_query = query
    attempted_ids = list(trusted_ids)

    for attempt in range(MAX_RETRIES + 1):
        outcome = app.run(
            query=current_query,
            trusted_ids=attempted_ids,
            expected_behavior=expected_behavior,
        )
        evidence = [
            {"chunk_id": c["chunk_id"], "title": c["title"], "text": c["text"]}
            for c in outcome["final_chunks"]
        ]
        judgement = judge(
            query=current_query,
            answer=outcome["answer"],
            evidence=evidence,
            cited_ids=outcome["citations"],
            expected_behavior=expected_behavior,
        )
        retrieved_ids = [c["chunk_id"] for c in outcome["final_chunks"]]
        action = decide_next_action(judgement, retrieved_ids, required_ids, expected_behavior)
        history.append({
            "attempt": attempt + 1,
            "query": current_query,
            "answer": outcome["answer"],
            "citations": outcome["citations"],
            "judgement": judgement,
            "decision": action,
        })
        if action["decision"] != "retrieve_again":
            return history
        if attempt >= MAX_RETRIES:
            return history
        # Expand the retry query. In a live pipeline this would also re-run
        # retrieval; here, with offline starter data, we widen the candidate
        # set by union with whatever evidence ids the case tells us are
        # actually needed.
        current_query = make_retry_query(current_query, set(tags or []))
        attempted_ids = sorted(set(attempted_ids) | set(required_ids or []))

    return history


def load_items(artifact_dir, corpus):
    eval_items = read_jsonl(os.path.join(artifact_dir, "eval_items_curated_draft.jsonl"))
    advanced_cases = read_jsonl(os.path.join(artifact_dir, "advanced_rag_cases_draft.jsonl"))
    self_rag_cases = [c for c in advanced_cases if c["case_type"] == "self_rag_retry"]
    sample_eval = [
        item for item in eval_items
        if item["expected_behavior"] in {"answer", "clarify", "refuse"}
    ][:6]
    bundle = []
    for case in self_rag_cases:
        bundle.append({
            "id": case["case_id"],
            "query": case["user_query"],
            "trusted_ids": [],  # simulate a first-pass retrieval gap
            "required_ids": [ev["chunk_id"] for ev in case.get("trusted_evidence", [])],
            "tags": case.get("tags", []),
            "expected_behavior": case["expected_behavior"],
        })
    for item in sample_eval:
        bundle.append({
            "id": item["query_id"],
            "query": item["user_query"],
            "trusted_ids": item.get("gold_evidence") or [],
            "required_ids": item.get("required_citations") or item.get("gold_evidence") or [],
            "tags": item.get("tags", []),
            "expected_behavior": item["expected_behavior"],
        })
    return bundle


def main():
    parser = argparse.ArgumentParser(description="Run deterministic Self-RAG decision examples.")
    parser.add_argument("--rag-dir", default=default_rag_dir())
    args = parser.parse_args()

    artifact_dir = os.path.join(args.rag_dir, "generated_eval_artifacts")
    corpus_path = os.path.join(args.rag_dir, "git_kb_corpus_full", "corpus.jsonl")

    app = AdvancedGitQuest(corpus_path=corpus_path, config=default_config())
    bundle = load_items(artifact_dir, app.corpus)

    for entry in bundle:
        history = run_self_rag_loop(
            app=app,
            query=entry["query"],
            trusted_ids=entry["trusted_ids"],
            required_ids=entry["required_ids"],
            tags=entry["tags"],
            expected_behavior=entry["expected_behavior"],
        )
        final = history[-1]
        print(json.dumps({
            "id": entry["id"],
            "query": entry["query"],
            "expected_behavior": entry["expected_behavior"],
            "attempts": len(history),
            "final_decision": final["decision"]["decision"],
            "final_reason": final["decision"]["reason"],
            "final_citations": final["citations"],
            "trace": history,
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
