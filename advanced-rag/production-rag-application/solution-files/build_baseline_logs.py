"""Evaluating LLM Outputs 3 - Baseline run-log builder.

Generates a synthetic ``baseline_run_logs.jsonl`` file in the 15-field
Run Log shape. The file is consumed by ``monitoring.py`` to teach
baseline-versus-current comparison, threshold alerts, and drift
detection in EO3, and by the Advanced RAG monitoring lesson later.

Each generated row is built directly from the EO1 curated eval set so
the ``query_id``s match the ones EO/AR use everywhere else.

Usage:
    python build_baseline_logs.py --rag-dir <path/to/rag>
"""

import argparse
import hashlib
import json
from pathlib import Path


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


def stable_id(prefix, text):
    return f"{prefix}_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def find_rag_dir():
    cwd = Path.cwd()
    if (cwd / "generated_eval_artifacts").exists():
        return cwd
    if Path("/workspace/rag/generated_eval_artifacts").exists():
        return Path("/workspace/rag")
    raise FileNotFoundError("Could not find generated_eval_artifacts/. Pass --rag-dir.")


def build_log(index, item):
    evidence = item.get("gold_evidence") or []
    required = item.get("required_citations") or []
    citations = required if item.get("expected_behavior") == "answer" else []
    retrieved = [
        {
            "chunk_id": chunk_id,
            "distance": round(0.34 + (i * 0.037), 4),
            "source_type": "unknown",
            "title": "filled by live pipeline",
        }
        for i, chunk_id in enumerate(evidence[:5])
    ]
    return {
        "run_id": stable_id("baseline_run", item["query_id"]),
        "query_id": item["query_id"],
        "pipeline_version": "gitquest_eo3_baseline_v1",
        "retrieval_config": {
            "corpus": "full",
            "candidate_k": 10,
            "rerank_top_n": 5,
            "token_budget": 6000,
            "model": "gpt-4o-mini",
        },
        "retrieved_candidates": retrieved,
        "final_chunks": evidence[:5],
        "answer": item.get("reference_answer") or "",
        "citations": citations,
        "dropped_citations": [],
        "metrics": {
            "retrieval_recall_at_5": 1 if evidence else None,
            "citation_precision": 1.0 if citations else None,
            "citation_recall": 1.0 if citations else None,
            "answerability_correct": True,
            "faithfulness_score": None,
        },
        "latency_ms": 900 + (index * 37),
        "input_tokens": 1500 + (len(evidence) * 260),
        "output_tokens": max(80, len((item.get("reference_answer") or "").split())),
        "estimated_cost_usd": round(0.0008 + (index * 0.00003), 6),
        "notes": "Synthetic baseline run log for observability lessons; replace with live run output when available.",
    }


def build_baseline_run_logs(curated_items, limit=24):
    selected = []
    for item in curated_items:
        if len(selected) >= limit:
            break
        if item.get("expected_answerability") in {"answerable", "needs_clarification", "unanswerable"}:
            selected.append(item)
    return [build_log(i + 1, item) for i, item in enumerate(selected)]


def main():
    parser = argparse.ArgumentParser(description="Write synthetic baseline run logs for observability lessons.")
    parser.add_argument("--rag-dir", type=Path, default=None,
                        help="Directory containing generated_eval_artifacts/.")
    parser.add_argument("--limit", type=int, default=24,
                        help="Number of rows to emit (default: 24).")
    args = parser.parse_args()

    rag_dir = args.rag_dir or find_rag_dir()
    artifact_dir = rag_dir / "generated_eval_artifacts"
    curated_path = artifact_dir / "eval_items_curated.jsonl"
    output_path = artifact_dir / "baseline_run_logs.jsonl"

    curated_items = read_jsonl(curated_path)
    rows = build_baseline_run_logs(curated_items, limit=args.limit)
    write_jsonl(output_path, rows)

    print(f"Wrote {len(rows)} baseline run logs to {output_path}")


if __name__ == "__main__":
    main()
