"""Memory: a notes file and context compaction.

NOTES.md lives in the workspace, so the agent reads and writes it with the
ordinary file tools.

Compaction keeps a long run inside the context window. When the last
request used more prompt tokens than the threshold, older messages are
replaced by a short summary the model writes itself. The system prompt and
the most recent messages stay as they are.
"""

NOTES_FILE = "NOTES.md"
KEEP_RECENT_MESSAGES = 6

SUMMARY_PROMPT = (
    "Summarize the work so far for your own future reference: what you did, what you found, "
    "the numbers that matter, and what is left to do. Be brief."
)


def split_point(messages):
    """Index where the recent messages start.

    The cut lands on an assistant message, so a tool result is never kept
    without the assistant message that requested it.
    """
    index = max(1, len(messages) - KEEP_RECENT_MESSAGES)
    while index < len(messages):
        message = messages[index]
        role = message["role"] if isinstance(message, dict) else message.role
        if role == "assistant":
            return index
        index += 1
    return len(messages)


def maybe_compact(messages, last_prompt_tokens, threshold, client, model, request_extra):
    """Compact messages if the last request was over the threshold.

    Returns (messages, usage). usage is None when nothing was compacted.
    """
    if last_prompt_tokens <= threshold:
        return messages, None
    cut = split_point(messages)
    if cut <= 1:
        return messages, None

    older = messages[1:cut]
    response = client.chat.completions.create(
        model=model,
        messages=[messages[0], *older, {"role": "user", "content": SUMMARY_PROMPT}],
        **request_extra,
    )
    summary = response.choices[0].message.content or ""
    compacted = [
        messages[0],
        {"role": "user", "content": f"Summary of earlier work in this run:\n{summary}"},
        *messages[cut:],
    ]
    return compacted, response.usage
