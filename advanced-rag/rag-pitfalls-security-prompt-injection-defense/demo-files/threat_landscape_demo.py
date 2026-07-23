import json

with open('data/generated_eval_artifacts/advanced_rag_cases.jsonl') as f:
    cases = {c['case_id']: c for c in (json.loads(l) for l in f if l.strip())}

examples = {
    "Prompt injection": cases["adv_rag_prompt_injection_doc_force_push"],
    "Source conflicts": cases["adv_rag_conflicting_sources_discard_file"],
    "Unsafe commands": cases["adv_rag_unsafe_command_reset_hard"],
}

for category, case in examples.items():
    print(f"\n{'=' * 60}")
    print(f"CATEGORY: {category}")
    print(f"{'=' * 60}")
    print(f"Case ID: {case['case_id']}")
    print(f"Query: {case['user_query']}")
    print(f"Expected behavior: {case['expected_behavior']}")
    if case.get('injected_docs'):
        print(f"Injected doc: {case['injected_docs'][0]['text']}")
    else:
        print("Injected docs: none (this threat comes from the query itself)")
    print(f"Unsafe patterns: {case['unsafe_patterns']}")
