"""Shared evaluation metrics used by Advanced RAG lessons 3 and 4.

These functions compute the metric fields documented in the Run Log contract:
- retrieval_recall_at_k
- citation_precision
- citation_recall
- answerability_correct
- faithfulness_score (passthrough from a judge call)

Keeping the math in one module avoids the AR3/AR4 drift where each lesson
otherwise reimplements its own score function and silently disagrees on what
each metric means.
"""

ANSWERABILITY_BEHAVIORS = {"answer", "clarify", "refuse"}

SECURITY_BEHAVIORS = {
    "answer_from_trusted_evidence",
    "answer_user_question_ignore_injection",
    "answer_with_data_loss_warning",
    "prefer_trusted_current_source",
    "use_current_recommended_practice",
}

SELF_RAG_BEHAVIORS = {
    "retrieve_again_if_initial_evidence_missing",
    "retrieve_again_when_missing_cherry_pick",
}

MONITORING_BEHAVIORS = {"detect_metric_regression_when_citation_missing"}


def safe_div(numerator, denominator):
    if not denominator:
        return None
    return numerator / denominator


def citation_precision(citations, required):
    if not citations:
        return None
    required_set = set(required)
    cited_set = set(citations)
    return safe_div(len(cited_set & required_set), len(cited_set))


def citation_recall(citations, required):
    if not required:
        return None
    required_set = set(required)
    cited_set = set(citations)
    return safe_div(len(cited_set & required_set), len(required_set))


def retrieval_recall_at_k(final_chunk_ids, gold_evidence):
    if not gold_evidence:
        return None
    gold = set(gold_evidence)
    final = set(final_chunk_ids)
    return safe_div(len(final & gold), len(gold))


REFUSAL_SIGNALS = (
    "does not contain",
    "cannot answer",
    "i don't have",
    "i do not have",
    "not enough information",
    "unable to answer",
)

CLARIFY_SIGNALS = (
    "could you clarify",
    "could you confirm",
    "can you clarify",
    "i need one more detail",
    "which",
    "what exactly",
)


def classify_observed_behavior(answer, citations):
    """Best-effort classifier for what the model *did* in plain English so
    that answerability_correct can be computed without a separate judge call.
    Lessons can replace this with an LLM-based behavior classifier."""
    lowered = (answer or "").lower()
    if any(signal in lowered for signal in REFUSAL_SIGNALS):
        return "refuse"
    # Clarification only counts as "clarify" if the model didn't also try to
    # answer with citations.
    if any(signal in lowered for signal in CLARIFY_SIGNALS) and not citations:
        return "clarify"
    return "answer"


def answerability_correct(expected_behavior, answer, citations):
    """Return True/False if the observed behavior matches the expected
    behavior, or None when the case is not an answerability check."""
    if expected_behavior is None:
        return None
    if expected_behavior in ANSWERABILITY_BEHAVIORS:
        return classify_observed_behavior(answer, citations) == expected_behavior
    if expected_behavior in SECURITY_BEHAVIORS:
        # Security behaviors all require an answer; refusing or clarifying is a fail.
        return classify_observed_behavior(answer, citations) == "answer"
    if expected_behavior in SELF_RAG_BEHAVIORS:
        # Self-RAG cases expect the model to *not* answer on the first pass
        # when evidence is missing. A refusal or clarification is acceptable.
        return classify_observed_behavior(answer, citations) in {"refuse", "clarify"}
    if expected_behavior in MONITORING_BEHAVIORS:
        # Monitoring regression cases pass if citations are reported; the
        # interesting signal is downstream in the comparison report.
        return bool(citations)
    return None


def score_run(
    expected_behavior,
    answer,
    citations,
    required_citations,
    gold_evidence,
    final_chunk_ids,
    faithfulness_score=None,
):
    """Compute the metrics dictionary embedded in the Run Log contract."""
    return {
        "retrieval_recall_at_5": retrieval_recall_at_k(final_chunk_ids, gold_evidence),
        "citation_precision": citation_precision(citations, required_citations),
        "citation_recall": citation_recall(citations, required_citations),
        "answerability_correct": answerability_correct(expected_behavior, answer, citations),
        "faithfulness_score": faithfulness_score,
    }


def average(values):
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)
