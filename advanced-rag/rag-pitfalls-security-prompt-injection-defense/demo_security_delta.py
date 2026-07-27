import json
from gitquest import ask_gitquest_secured

with open('data/generated_eval_artifacts/advanced_rag_cases.jsonl') as f:
    cases = {c['case_id']: c for c in (json.loads(l) for l in f if l.strip())}
case = cases["adv_rag_prompt_injection_doc_force_push"]

print("SECURED PIPELINE vs force_push injection:")
print(f"Query: {case['user_query']}")
print(f"Injected: {case['injected_docs'][0]['text']}")

result = ask_gitquest_secured(
    query=case["user_query"],
    injected_docs=case.get("injected_docs"),
)

print(f"\nFiltered injections: {result['filtered_injection_count']}")
print(f"\nAnswer:\n{result['answer']}")
print(f"\nCitations: {[c['chunk_id'] for c in result['citations']]}")

# Safety check
lowered = result["answer"].lower()
for p in case["unsafe_patterns"]:
    status = "HIT" if p.lower() in lowered else "OK"
    print(f"  {status}: '{p}'")

# Trust check on final chunks
print(f"\nFinal chunks:")
for c in result["retrieved_chunks"]:
    trust = c.get("source_trust", "unknown")
    risk = c.get("risk_flag") or "none"
    print(f"  {c['chunk_id']:<30} trust={trust:<12} risk={risk}")
