"""Context engineering: what the model sees on each call.

Every model call re-sends the whole conversation, so everything the agent
has done so far costs tokens again on every step. Three tools keep that in
check:

1. Truncation: a tool result can't flood the conversation.
2. Notes: findings worth keeping live in NOTES.md in the workspace, so
   they survive between runs and after compaction.
3. Compaction: when the conversation gets too long, older steps are
   replaced with a model-written summary.

as_dict, render, and SUMMARY_PROMPT are provided for you. You fill in truncate,
load_notes, split_point, compact, and to_tool_message as the lesson works through
them.
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


def truncate(text, limit=MAX_TOOL_OUTPUT_CHARS):
    """Cut a tool result down to the limit and say how much was cut."""
    # Return text unchanged when it is within the limit. Otherwise keep the
    # first limit characters and add a note saying how many were removed.
    ...


def load_notes(workspace):
    """Read NOTES.md from the workspace, if the agent has written one."""
    # Build the path to NOTES_FILE in the workspace. If it exists, return its
    # text; otherwise return None.
    ...


def as_dict(message):
    """Messages are dicts or SDK message objects. Treat them all as dicts."""
    if isinstance(message, dict):
        return message
    return message.model_dump(exclude_none=True)


def render(messages):
    """Turn messages into plain text so the model can summarize them."""
    lines = []
    for message in map(as_dict, messages):
        if message.get("content"):
            lines.append(f"[{message['role']}] {message['content']}")
        for call in message.get("tool_calls", []):
            lines.append(f"[tool call] {call['function']['name']}({call['function']['arguments']})")
    return "\n".join(lines)


def split_point(messages):
    """Index where the recent messages start.

    A tool result must stay right after the assistant message that asked
    for it, so the split moves back until it lands on an assistant message.
    """
    # This starting index keeps the last KEEP_RECENT_MESSAGES messages, but never
    # cuts before index 2, so the system prompt and the task always stay.
    index = max(2, len(messages) - KEEP_RECENT_MESSAGES)
    # Now step back until index lands on an assistant message, then return it.
    # Read a message's role with as_dict(messages[index])["role"], since some
    # are SDK objects, not plain dicts.
    ...


def compact(messages, client, model, reasoning_effort):
    """Replace older messages with a summary.

    messages[0] is the system prompt and messages[1] is the task. Both stay.
    Returns the new message list and the token usage of the summary call.
    """
    # Split the conversation. Use split_point for the boundary, then separate the
    # older middle (messages[2:start]) from the recent messages. If there is
    # nothing old to compact, return messages unchanged with zero usage.
    ...

    # The summary call, the same shape as run_agent's model call, is provided:
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

    # Build the result. Wrap the model's reply, response.choices[0].message.content,
    # in a user message that notes the older steps were removed. Then return the
    # rebuilt list (the system prompt and task, the summary, and the recent
    # messages) with a usage dict of the call's prompt_tokens and completion_tokens.
    ...


def to_tool_message(tool_call_id, result):
    """The message that carries a tool result back to the model, truncated."""
    # Return the tool-role message (role, tool_call_id, content), with the
    # result serialized to JSON and passed through truncate.
    ...
