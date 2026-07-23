import json
from gitquest import (
    corpus, build_context, build_secured_context,
    chunk_from_corpus, chunk_from_injected,
    SYSTEM_PROMPT, SECURED_SYSTEM_PROMPT,
)

# Print both prompts (without context)
print("UNSECURED SYSTEM_PROMPT:")
print(SYSTEM_PROMPT.replace("{context}", "[...context...]"))
print(f"\n{'=' * 60}\n")
print("SECURED_SYSTEM_PROMPT:")
print(SECURED_SYSTEM_PROMPT.replace("{context}", "[...context...]"))

# Build same two chunks through both context builders
with open('data/generated_eval_artifacts/advanced_rag_cases.jsonl') as f:
    cases = {c['case_id']: c for c in (json.loads(l) for l in f if l.strip())}
case = cases["adv_rag_prompt_injection_doc_force_push"]
injected = case["injected_docs"][0]
trusted_entry = corpus[case["trusted_evidence"][0]["chunk_id"]]

unsecured = [
    {"chunk_id": trusted_entry["chunk_id"], "text": trusted_entry["text"],
     "title": trusted_entry["title"], "source_type": trusted_entry["source_type"],
     "command": trusted_entry["command"]},
    {"chunk_id": injected["doc_id"], "text": injected["text"],
     "title": "Community Tip", "source_type": "other", "command": "unknown"},
]
secured = [
    chunk_from_corpus(trusted_entry),
    chunk_from_injected(injected),
]

print(f"\n{'=' * 60}")
print("UNSECURED CONTEXT (build_context):")
print(f"{'=' * 60}")
print(build_context(unsecured))

print(f"\n{'=' * 60}")
print("SECURED CONTEXT (build_secured_context):")
print(f"{'=' * 60}")
print(build_secured_context(secured))
