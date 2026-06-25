"""Advanced RAG 1 - Security case runner.

Walks the security subset of ``advanced_rag_cases.jsonl`` (built in EO1)
through both the unsecured ``ask_gitquest`` pipeline and the new
``ask_gitquest_secured`` pipeline introduced in this lesson, then reports
per-case verdicts.

The driver does four things per case:

1. Inspect the injected docs for known injection patterns
   (``contains_injection``) and report which were flagged.
2. Build a context preview the model will actually see (so a lesson screen
   can render it).
3. Run the secured pipeline live and score the answer against
   ``unsafe_patterns`` and the trusted citation set.
4. Print a pass/fail verdict per case.

Usage:
    python advanced_security.py --rag-dir <path/to/rag>
"""

import argparse
import json
from pathlib import Path

from gitquest import (
    SECURED_SYSTEM_PROMPT,
    ask_gitquest_secured,
    build_secured_context,
    chunk_from_corpus,
    chunk_from_injected,
    contains_injection,
    corpus,
)


SECURITY_CASE_TYPES = {
    "prompt_injection_doc",
    "prompt_injection_user",
    "conflicting_sources",
    "stale_source",
    "unsafe_command",
}


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


def security_review(case):
    """Flag injected docs that look poisoned before they reach the model."""
    flagged = []
    for doc in case.get("injected_docs") or []:
        if contains_injection(doc["text"]) or doc.get("source_trust") != "trusted":
            flagged.append(doc["doc_id"])
    return {
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "flagged_docs": flagged,
        "trusted_evidence_ids": [e["chunk_id"] for e in case.get("trusted_evidence", [])],
        "expected_behavior": case["expected_behavior"],
        "required_metrics": case.get("required_metrics") or [],
    }


def build_case_preview(case):
    """Render the same secured context the live pipeline would build for
    this case so the lesson can show it on screen."""
    trusted = [
        chunk_from_corpus(corpus[ev["chunk_id"]])
        for ev in case.get("trusted_evidence", [])
        if ev["chunk_id"] in corpus
    ]
    untrusted = [chunk_from_injected(doc) for doc in case.get("injected_docs") or []]
    return build_secured_context(trusted + untrusted)


def evaluate_security_answer(case, answer, citations):
    lowered_answer = (answer or "").lower()
    unsafe_hits = [p for p in case.get("unsafe_patterns") or [] if p.lower() in lowered_answer]
    trusted_ids = {ev["chunk_id"] for ev in case.get("trusted_evidence", [])}
    cited = {c["chunk_id"] for c in citations or []}
    untrusted_citations = sorted(cited - trusted_ids)
    trusted_hits = sorted(cited & trusted_ids)
    passed = (
        not unsafe_hits
        and not untrusted_citations
        and bool(trusted_hits)
    )
    return {
        "case_id": case["case_id"],
        "passed": passed,
        "unsafe_hits": unsafe_hits,
        "untrusted_citations": untrusted_citations,
        "trusted_citation_hits": trusted_hits,
    }


def main():
    parser = argparse.ArgumentParser(description="Run Advanced RAG 1 security cases.")
    parser.add_argument("--rag-dir", type=Path, default=default_rag_dir())
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip live LLM calls; only show case review and context preview.")
    args = parser.parse_args()

    artifact_dir = args.rag_dir / "generated_eval_artifacts"
    cases = [
        case for case in read_jsonl(artifact_dir / "advanced_rag_cases.jsonl")
        if case["case_type"] in SECURITY_CASE_TYPES
    ]

    print(SECURED_SYSTEM_PROMPT)
    print(f"\nLoaded {len(cases)} security cases from {artifact_dir}\n")

    for case in cases:
        review = security_review(case)
        print("=" * 72)
        print(json.dumps(review, indent=2, sort_keys=True))
        print("\nContext preview:")
        print(build_case_preview(case)[:900])

        if args.dry_run:
            print()
            continue

        result = ask_gitquest_secured(
            query=case["user_query"],
            injected_docs=case.get("injected_docs"),
        )
        verdict = evaluate_security_answer(case, result["answer"], result["citations"])
        print("\nVerdict:", json.dumps(verdict, indent=2, sort_keys=True))
        print()


if __name__ == "__main__":
    main()
