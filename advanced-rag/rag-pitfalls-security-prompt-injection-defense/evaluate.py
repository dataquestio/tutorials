"""Foundation evaluation metrics for the GitQuest pipeline.

Computes the retrieval, citation, lexical, and answerability metrics
introduced in Evaluating LLM Outputs 1. Reads runs and the curated eval
set from JSONL files and prints aggregate scores.

Usage:
    python evaluate.py \\
        --eval-path data/generated_eval_artifacts/eval_items_curated.jsonl \\
        --runs-path runs.jsonl
"""

import argparse
import json
from collections import Counter
from pathlib import Path


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def safe_div(numerator, denominator):
    if not denominator:
        return None
    return numerator / denominator


def retrieval_recall_at_k(final_chunk_ids, gold_evidence):
    if not gold_evidence:
        return None
    gold = set(gold_evidence)
    final = set(final_chunk_ids)
    return safe_div(len(final & gold), len(gold))


def retrieval_mrr(final_chunk_ids, gold_evidence):
    if not gold_evidence:
        return None
    gold = set(gold_evidence)
    for rank, chunk_id in enumerate(final_chunk_ids, start=1):
        if chunk_id in gold:
            return 1.0 / rank
    return 0.0


def citation_precision(citations, required):
    if not citations:
        return None
    cited = set(citations)
    required_set = set(required)
    return safe_div(len(cited & required_set), len(cited))


def citation_recall(citations, required):
    if not required:
        return None
    cited = set(citations)
    required_set = set(required)
    return safe_div(len(cited & required_set), len(required_set))


def tokenize(text):
    return (text or "").lower().split()


def lexical_overlap(reference, hypothesis):
    ref = Counter(tokenize(reference))
    hyp = Counter(tokenize(hypothesis))
    if not hyp or not ref:
        return 0.0, 0.0, 0.0
    overlap = sum((ref & hyp).values())
    precision = overlap / sum(hyp.values())
    recall = overlap / sum(ref.values())
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def bleu_1(reference, hypothesis):
    """Unigram BLEU baseline. Real BLEU uses higher-order n-grams; one-gram
    precision is enough for the lesson to motivate why lexical metrics are
    a limited grading target."""
    p, _, _ = lexical_overlap(reference, hypothesis)
    return p


def rouge_1(reference, hypothesis):
    """Unigram ROUGE baseline."""
    _, r, _ = lexical_overlap(reference, hypothesis)
    return r


def f1_score(reference, hypothesis):
    _, _, f = lexical_overlap(reference, hypothesis)
    return f


REFUSAL_SIGNALS = (
    "does not contain",
    "cannot answer",
    "not enough information",
    "unable to answer",
)

CLARIFY_SIGNALS = (
    "could you clarify",
    "could you confirm",
    "can you clarify",
    "i need one more detail",
    "what exactly",
)


def classify_observed_behavior(answer, cited_ids):
    lowered = (answer or "").lower()
    if any(signal in lowered for signal in REFUSAL_SIGNALS):
        return "refuse"
    if any(signal in lowered for signal in CLARIFY_SIGNALS) and not cited_ids:
        return "clarify"
    return "answer"


def answerability_correct(expected_behavior, answer, cited_ids):
    if expected_behavior is None:
        return None
    return classify_observed_behavior(answer, cited_ids) == expected_behavior


def average(values):
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def score_item(eval_item, run):
    """Compute the metric block for one (eval_item, run) pair."""
    final_ids = [c["chunk_id"] for c in run.get("retrieved_chunks", [])]
    cited_ids = [c["chunk_id"] for c in run.get("citations", [])]
    reference = eval_item.get("reference_answer") or ""
    answer = run.get("answer") or ""
    return {
        "retrieval_recall_at_5": retrieval_recall_at_k(final_ids, eval_item.get("gold_evidence") or []),
        "retrieval_mrr": retrieval_mrr(final_ids, eval_item.get("gold_evidence") or []),
        "citation_precision": citation_precision(cited_ids, eval_item.get("required_citations") or []),
        "citation_recall": citation_recall(cited_ids, eval_item.get("required_citations") or []),
        "bleu_1": bleu_1(reference, answer),
        "rouge_1": rouge_1(reference, answer),
        "f1": f1_score(reference, answer),
        "answerability_correct": answerability_correct(
            eval_item.get("expected_behavior"), answer, cited_ids
        ),
    }


def aggregate(scored_rows):
    if not scored_rows:
        return {}
    keys = list(scored_rows[0].keys())
    summary = {}
    for key in keys:
        values = [row[key] for row in scored_rows]
        if all(isinstance(v, bool) or v is None for v in values):
            present = [v for v in values if v is not None]
            summary[key] = average([1.0 if v else 0.0 for v in present]) if present else None
        else:
            summary[key] = average(values)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Compute foundation evaluation metrics over GitQuest runs.")
    parser.add_argument("--eval-path", type=Path, required=True, help="Path to eval_items_curated.jsonl.")
    parser.add_argument("--runs-path", type=Path, required=True, help="Path to a JSONL of GitQuest run outputs.")
    args = parser.parse_args()

    eval_items = {item["query_id"]: item for item in read_jsonl(args.eval_path)}
    runs = read_jsonl(args.runs_path)

    scored = []
    skipped = 0
    for run in runs:
        item = eval_items.get(run.get("query_id"))
        if item is None:
            skipped += 1
            continue
        scored.append(score_item(item, run))

    print(json.dumps({
        "scored_count": len(scored),
        "skipped_count": skipped,
        "aggregate": aggregate(scored),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
