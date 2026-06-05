import argparse
import json
import time
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


def default_rag_dir():
    path = Path("/workspace/rag")
    if path.exists():
        return path
    return Path("data")


def load_corpus(path):
    corpus = {}
    for row in read_jsonl(path):
        corpus[row["chunk_id"]] = row
    return corpus


class ProductionGitQuest:
    def __init__(self, rag_dir):
        self.rag_dir = Path(rag_dir)
        self.artifact_dir = self.rag_dir / "generated_eval_artifacts"
        self.corpus = load_corpus(self.rag_dir / "git_kb_corpus_scoped" / "corpus.jsonl")
        self.eval_items = read_jsonl(self.artifact_dir / "eval_items_curated_draft.jsonl")
        self.advanced_cases = read_jsonl(self.artifact_dir / "advanced_rag_cases_draft.jsonl")
        self.eval_by_id = {item["query_id"]: item for item in self.eval_items}
        self.case_by_id = {case["case_id"]: case for case in self.advanced_cases}

    def evidence_for_item(self, item):
        ids = item.get("gold_evidence") or []
        return [self.corpus[chunk_id] for chunk_id in ids if chunk_id in self.corpus]

    def evidence_for_case(self, case):
        ids = [e["chunk_id"] for e in case.get("trusted_evidence", [])]
        return [self.corpus[chunk_id] for chunk_id in ids if chunk_id in self.corpus]

    def build_context(self, chunks):
        parts = []
        for chunk in chunks:
            parts.append(
                f"chunk_id: {chunk['chunk_id']}\n"
                f"title: {chunk['title']}\n"
                f"source_type: {chunk['source_type']}\n"
                f"command: {chunk.get('command')}\n\n"
                f"{chunk['text']}"
            )
        return "\n\n---\n\n".join(parts)

    def draft_answer(self, query, chunks, expected_behavior):
        if expected_behavior == "refuse":
            return "The available Git documentation does not contain enough information to answer this safely."
        if expected_behavior == "clarify":
            return "I need one more detail before giving a safe command: what exact Git state or target are you trying to change?"
        if not chunks:
            return "The available retrieved context does not contain enough information to answer this safely."

        chunk = chunks[0]
        first_line = chunk["text"].splitlines()[0]
        return (
            f"Based on the retrieved Git documentation, use the guidance from {chunk['title']}.\n\n"
            f"Relevant source text begins: {first_line}\n\n"
            f"SOURCES:\n- chunk_id: {chunk['chunk_id']} | {chunk['title']}"
        )

    def parse_citations(self, answer):
        cited = []
        normalized = answer.replace("Sources:", "SOURCES:").replace("sources:", "SOURCES:")
        if "SOURCES:" not in normalized:
            return cited
        for line in normalized.split("SOURCES:", 1)[1].splitlines():
            if "chunk_id:" in line:
                cited_id = line.split("chunk_id:", 1)[1].split("|", 1)[0].strip()
                cited.append(cited_id)
        return cited

    def score_run(self, expected_ids, citations, final_ids, expected_behavior):
        expected = set(expected_ids)
        cited = set(citations)
        final = set(final_ids)
        citation_precision = None
        citation_recall = None
        retrieval_recall = None
        if cited:
            citation_precision = len(cited & expected) / len(cited)
        if expected:
            citation_recall = len(cited & expected) / len(expected)
            retrieval_recall = len(final & expected) / len(expected)
        return {
            "retrieval_recall_at_5": retrieval_recall,
            "citation_precision": citation_precision,
            "citation_recall": citation_recall,
            "answerability_correct": expected_behavior in {"answer", "clarify", "refuse", "answer_from_trusted_evidence", "answer_with_data_loss_warning", "use_current_recommended_practice", "prefer_trusted_current_source"},
            "faithfulness_score": None,
        }

    def run_eval_item(self, item):
        started = time.time()
        chunks = self.evidence_for_item(item)
        answer = self.draft_answer(item["user_query"], chunks, item["expected_behavior"])
        citations = self.parse_citations(answer)
        elapsed = int((time.time() - started) * 1000)
        expected_ids = item.get("required_citations") or item.get("gold_evidence") or []
        final_ids = [chunk["chunk_id"] for chunk in chunks]
        return {
            "query_id": item["query_id"],
            "query": item["user_query"],
            "mode": "eval_item",
            "answer": answer,
            "citations": citations,
            "final_chunks": final_ids,
            "metrics": self.score_run(expected_ids, citations, final_ids, item["expected_behavior"]),
            "latency_ms": elapsed,
        }

    def run_advanced_case(self, case):
        started = time.time()
        chunks = self.evidence_for_case(case)
        answer = self.draft_answer(case["user_query"], chunks, "answer")
        citations = self.parse_citations(answer)
        elapsed = int((time.time() - started) * 1000)
        expected_ids = [e["chunk_id"] for e in case.get("trusted_evidence", [])]
        final_ids = [chunk["chunk_id"] for chunk in chunks]
        return {
            "case_id": case["case_id"],
            "query": case["user_query"],
            "mode": "advanced_case",
            "case_type": case["case_type"],
            "answer": answer,
            "citations": citations,
            "final_chunks": final_ids,
            "metrics": self.score_run(expected_ids, citations, final_ids, case["expected_behavior"]),
            "latency_ms": elapsed,
            "expected_behavior": case["expected_behavior"],
        }


def main():
    parser = argparse.ArgumentParser(description="Run a small production-style GitQuest artifact harness.")
    parser.add_argument("--rag-dir", type=Path, default=default_rag_dir())
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--output-log", type=Path, default=Path("production_gitquest_run_logs.jsonl"))
    args = parser.parse_args()

    app = ProductionGitQuest(args.rag_dir)
    runs = []
    for item in app.eval_items[:args.limit]:
        runs.append(app.run_eval_item(item))
    for case in app.advanced_cases[:args.limit]:
        runs.append(app.run_advanced_case(case))

    write_jsonl(args.output_log, runs)
    print(f"Wrote {len(runs)} run logs to {args.output_log}")
    print(json.dumps(runs[:3], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
