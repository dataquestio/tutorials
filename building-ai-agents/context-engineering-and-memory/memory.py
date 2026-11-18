"""Context engineering: what the model sees on each call.

Every model call re-sends the whole conversation, so everything the agent
has done so far costs tokens again on every step. Three tools keep that in
check:

1. Truncation: a tool result can't flood the conversation.
2. Notes: findings worth keeping live in NOTES.md in the workspace, so
   they survive between runs and after compaction.
3. Compaction: when the conversation gets too long, older steps are
   replaced with a model-written summary.

This is starter code. Complete each TODO as the lesson walks through it.
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
    # TODO:
    # - Return text unchanged if it fits the limit
    # - Keep the first limit characters
    # - Add a note with the number of characters cut
    ...


def load_notes(workspace):
    """Read NOTES.md from the workspace, if the agent has written one."""
    # TODO:
    # - Build the path to NOTES_FILE in workspace
    # - Return its text if it exists
    # - Return None otherwise
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
    index = max(2, len(messages) - KEEP_RECENT_MESSAGES)
    # TODO:
    # - Step index back until it lands on an assistant message
    # - Stop at index 2
    # - Read each role with as_dict
    # - Return index
    ...


def compact(messages, client, model, reasoning_effort):
    """Replace older messages with a summary.

    messages[0] is the system prompt and messages[1] is the task. Both stay.
    Returns the new message list and the token usage of the summary call.
    """
    # TODO:
    # - Find start with split_point
    # - Split older and recent messages
    # - Return messages and zero usage if older is empty
    ...

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

    # TODO:
    # - Wrap the reply in a user summary message
    # - Rebuild the list from the first two messages, summary, and recent
    # - Return the list and the call's token usage
    ...


def to_tool_message(tool_call_id, result):
    """The message that carries a tool result back to the model, truncated."""
    # TODO:
    # - Serialize result to JSON
    # - Pass it through truncate
    # - Return a tool message with tool_call_id and content
    ...
