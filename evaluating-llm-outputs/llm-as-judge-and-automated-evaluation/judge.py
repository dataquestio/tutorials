import json


class JudgeUnavailable(RuntimeError):
    """Raised when an LLM judge is requested but no client is configured."""


### Add JUDGE_SYSTEM_PROMPT here ###


### Add JUDGE_USER_TEMPLATE here ###


SAFETY_TRIGGERS = (
    "git reset --hard",
    "git push --force",
    "git clean -fdx",
    "rm -rf",
)

REFUSAL_SIGNALS = (
    "does not contain",
    "cannot answer",
    "not enough information",
    "unable to answer",
)


def format_evidence(evidence):
    if not evidence:
        return "(no evidence supplied)"
    parts = []
    for chunk in evidence:
        parts.append(
            f"chunk_id: {chunk['chunk_id']}\n"
            f"title: {chunk.get('title', '')}\n\n"
            f"{chunk.get('text', '')}"
        )
    return "\n\n---\n\n".join(parts)


def normalize_score(value):
    if isinstance(value, int):
        return max(1, min(5, value))
    if isinstance(value, str):
        if value.strip().lower() in {"not_applicable", "n/a", "na"}:
            return "not_applicable"
        try:
            return normalize_score(int(value.strip()))
        except ValueError:
            return "not_applicable"
    return "not_applicable"


def normalize_judgement(raw):
    return {
        "faithfulness": normalize_score(raw.get("faithfulness")),
        "citation_correctness": normalize_score(raw.get("citation_correctness")),
        "command_safety": normalize_score(raw.get("command_safety")),
        "refusal_correctness": normalize_score(raw.get("refusal_correctness")),
        "rationale": str(raw.get("rationale", ""))[:500],
    }


### Add heuristic_judge() here ###


def llm_judge(query, answer, evidence, client=None, model="gpt-4o-mini", cited_ids=None, expected_behavior=None):
    if client is None:
        raise JudgeUnavailable(
            "No OpenAI-compatible client was passed. Either provide a client "
            "or call heuristic_judge() instead."
        )
    user_prompt = JUDGE_USER_TEMPLATE.format(
        query=query,
        evidence=format_evidence(evidence),
        answer=answer,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    return normalize_judgement(parsed)


def faithfulness_score(judgement):
    """Pull the faithfulness number out of a judgement dict for downstream
    consumers that want a single number. Returns None when not applicable."""
    value = judgement.get("faithfulness")
    if isinstance(value, int):
        return float(value)
    return None
