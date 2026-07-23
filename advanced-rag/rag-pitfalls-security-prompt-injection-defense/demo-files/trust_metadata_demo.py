import json
from gitquest import corpus, chunk_from_corpus, chunk_from_injected

# Show a trusted chunk
trusted = corpus["6754f9f72c9ca2a8"]
enriched_trusted = chunk_from_corpus(trusted, distance=0.3142)
print("TRUSTED CHUNK (enriched):")
display = {k: v for k, v in enriched_trusted.items() if k != "text"}
display["text"] = enriched_trusted["text"][:80] + "..."
print(json.dumps(display, indent=2, default=str))

# Show an injected doc
with open('data/generated_eval_artifacts/advanced_rag_cases.jsonl') as f:
    cases = {c['case_id']: c for c in (json.loads(l) for l in f if l.strip())}
injected = cases["adv_rag_prompt_injection_doc_force_push"]["injected_docs"][0]
enriched_untrusted = chunk_from_injected(injected)
print("\nUNTRUSTED CHUNK (enriched):")
display = {k: v for k, v in enriched_untrusted.items() if k != "text"}
display["text"] = enriched_untrusted["text"][:80] + "..."
print(json.dumps(display, indent=2, default=str))

# Side-by-side of new fields
print("\nSIDE-BY-SIDE (new fields only):")
for field in ["source_trust", "source_origin", "risk_flag"]:
    print(f"  {field:<20} trusted={str(enriched_trusted[field]):<30} untrusted={str(enriched_untrusted[field])}")
