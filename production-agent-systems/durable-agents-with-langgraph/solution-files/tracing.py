"""Trace log for agent runs.

Every model call, tool call, approval decision, skill load, and compaction
is appended to a JSONL file, one event per line. Traces are how you find
out what an unattended agent actually did.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

RESULT_PREVIEW_CHARS = 500


def write_event(
    trace_path: Path,
    run_id: str,
    step: int,
    type: str,
    tool: str | None = None,
    args: dict | None = None,
    result: dict | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration_ms: int = 0,
) -> None:
    """Append one event to the trace file.

    type is one of: model_call, tool_call, tool_result, approval,
    skill_load, compaction, final, stop, error.
    """
    preview = None
    if result is not None:
        preview = json.dumps(result)[:RESULT_PREVIEW_CHARS]

    event = {
        "run_id": run_id,
        "step": step,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type,
        "tool": tool,
        "args": args,
        "result_preview": preview,
        "is_error": bool(result and "error" in result),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
    }
    Path(trace_path).parent.mkdir(parents=True, exist_ok=True)
    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
