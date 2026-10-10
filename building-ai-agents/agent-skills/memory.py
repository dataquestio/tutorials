"""Context engineering: what the model sees on each call.

Every model call re-sends the whole conversation, so everything the agent
has done so far costs tokens again on every step. Three tools keep that in
check:

1. Truncation: a tool result can't flood the conversation.
2. Notes: findings worth keeping live in NOTES.md in the workspace, so
   they survive between runs and after compaction.
3. Compaction: when the conversation gets too long, older steps are
   replaced with a model-written summary.
"""

import json
from pathlib import Path

MAX_TOOL_OUTPUT_CHARS = 4_000
NOTES_FILE = "NOTES.md"
KEEP_RECENT_MESSAGES = 6

SUMMARY_PROMPT = """Summarize the agent's work so far for its own future use. Include:
- facts learned about the data (files, columns, value formats, quirks)
- code approaches that worked, and errors to avoid repeating
- intermediate results with their numbers
- what is still left to do for the task
Be specific and brief. Use bullet points."""


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Cut a tool result down to the limit and say how much was cut."""
    if len(text) <= limit:
        return text
    cut = len(text) - limit
    return text[:limit] + f"\n[truncated {cut} characters. Print less, e.g. a summary or the first rows.]"


def load_notes(workspace: Path) -> str | None:
    """Read NOTES.md from the workspace, if the agent has written one."""
    path = Path(workspace) / NOTES_FILE
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def as_dict(message) -> dict:
    """Messages are dicts or SDK message objects. Treat them all as dicts."""
    if isinstance(message, dict):
        return message
    return message.model_dump(exclude_none=True)


def render(messages: list) -> str:
    """Turn messages into plain text so the model can summarize them."""
    lines = []
    for message in map(as_dict, messages):
        if message.get("content"):
            lines.append(f"[{message['role']}] {message['content']}")
        for call in message.get("tool_calls", []):
            lines.append(f"[tool call] {call['function']['name']}({call['function']['arguments']})")
    return "\n".join(lines)


def split_point(messages: list) -> int:
    """Index where the recent messages start.

    A tool result must stay right after the assistant message that asked
    for it, so the split moves back until it lands on an assistant message.
    """
    index = max(2, len(messages) - KEEP_RECENT_MESSAGES)
    while index > 2 and as_dict(messages[index])["role"] != "assistant":
        index -= 1
    return index


def compact(messages: list, client, model: str, reasoning_effort: str | None) -> tuple[list, dict]:
    """Replace older messages with a summary.

    messages[0] is the system prompt and messages[1] is the task. Both stay.
    Returns the new message list and the token usage of the summary call.
    """
    start = split_point(messages)
    older, recent = messages[2:start], messages[start:]
    if not older:
        return messages, {"input_tokens": 0, "output_tokens": 0}

    request = {
        "model": model,
        "messages": [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": render(older)},
        ],
    }
    if reasoning_effort is not None:
        request["reasoning_effort"] = reasoning_effort
    response = client.chat.completions.create(**request)

    summary = {
        "role": "user",
        "content": "Summary of your earlier work on this task (older steps were removed to save space):\n\n"
        + response.choices[0].message.content,
    }
    usage = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
    return messages[:2] + [summary] + recent, usage


def to_tool_message(tool_call_id: str, result: dict) -> dict:
    """The message that carries a tool result back to the model, truncated."""
    return {"role": "tool", "tool_call_id": tool_call_id, "content": truncate(json.dumps(result))}
