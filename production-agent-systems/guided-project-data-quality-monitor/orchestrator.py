"""An orchestrator that hands work to subagents with their own contexts.

The orchestrator is a small agent loop with one tool, delegate. Each
delegate call starts a subagent: an ordinary run_agent call with a fresh
conversation. The subagent reads whatever feed data it needs, and only its
short final report comes back to the orchestrator. The bulky tool results
stay in the subagent's context and never reach the orchestrator's.

That keeps every single context small when the work splits into independent
pieces, such as one review per day. It costs extra model calls: the
orchestrator has to plan, and every subagent rereads its own system prompt.
When the pieces depend on each other, such as following the same events
across several days, splitting hurts: the subagents cannot see each other's
data, so the orchestrator ends up passing ids back and forth. One agent with
one context is cheaper and simpler for that kind of task.

Usage:
    python orchestrator.py --data-dir <path/to/usgs> --mode orchestrated --task "..."
    python orchestrator.py --data-dir <path/to/usgs> --mode single --task "..."
"""

import argparse
import json
import os
import time
import uuid
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from agent import AgentConfig, AgentResult, run_agent
from run import prepare_workspace
from tracing import write_event

ORCHESTRATOR_PROMPT = """You coordinate subagents that review a daily earthquake feed.

You cannot read the feed yourself. Use the delegate tool to give a subagent one well-defined piece of work, such as reviewing a single day. A subagent starts with an empty conversation, so write complete instructions: the day, what to report, and to keep the report under 120 words.

Combine the subagents' reports into the final answer. Do not delegate work you can do from the reports you already have."""

DELEGATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate",
        "description": "Start a subagent with its own fresh context and return its final report.",
        "parameters": {
            "type": "object",
            "properties": {"instructions": {"type": "string", "description": "Complete instructions for the subagent"}},
            "required": ["instructions"],
        },
    },
}

# Reviews only read the feed; they must not change the catalog or send anything.
REVIEW_POLICY = {
    "list_files": "allow", "read_file": "allow", "run_python": "allow", "load_skill": "allow",
    "day_summary": "allow", "write_file": "deny", "run_shell": "deny", "apply_day_to_catalog": "deny",
    "flag_anomaly": "deny", "append_progress": "deny", "send_alert": "deny",
}


def run_orchestrator(task: str, config: AgentConfig, client=None, subagent_max_steps: int = 8) -> AgentResult:
    """Run the orchestrator loop. Subagents share the trace file and token totals."""
    client = client or OpenAI()
    run_id = uuid.uuid4().hex[:12]
    sub_config = replace(config, max_steps=subagent_max_steps)
    extra = {"tools": [DELEGATE_SCHEMA]}
    if config.reasoning_effort is not None:
        extra["reasoning_effort"] = config.reasoning_effort

    messages = [{"role": "system", "content": ORCHESTRATOR_PROMPT}, {"role": "user", "content": task}]
    input_tokens = output_tokens = 0
    answer, stop_reason, step = None, "max_steps", 0

    while step < config.max_steps:
        step += 1
        started = time.monotonic()
        response = client.chat.completions.create(model=config.model, messages=messages, **extra)
        usage = response.usage
        input_tokens += usage.prompt_tokens
        output_tokens += usage.completion_tokens
        write_event(config.trace_path, run_id, step, "model_call", input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens, duration_ms=int((time.monotonic() - started) * 1000))

        message = response.choices[0].message
        if not message.tool_calls:
            answer, stop_reason = message.content, "final"
            write_event(config.trace_path, run_id, step, "final")
            break

        messages.append(message)
        for call in message.tool_calls:
            instructions = json.loads(call.function.arguments).get("instructions", "")
            write_event(config.trace_path, run_id, step, "tool_call", tool="delegate", args={"instructions": instructions})
            sub = run_agent(instructions, sub_config, client)
            input_tokens += sub.input_tokens
            output_tokens += sub.output_tokens
            result = {"report": sub.answer, "stop_reason": sub.stop_reason}
            write_event(config.trace_path, run_id, step, "tool_result", tool="delegate", result=result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

        if input_tokens + output_tokens >= config.max_tokens_total:
            stop_reason = "budget"
            break

    return AgentResult(answer=answer, stop_reason=stop_reason, steps=step,
                       input_tokens=input_tokens, output_tokens=output_tokens, files_written=[])


def context_stats(trace_path: Path, start_line: int) -> dict:
    """Largest single prompt, and model calls, for trace events written after start_line."""
    with open(trace_path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f][start_line:]
    calls = [e for e in events if e["type"] == "model_call"]
    per_agent = {}
    for e in calls:
        per_agent[e["run_id"]] = max(per_agent.get(e["run_id"], 0), e["input_tokens"])
    return {"model_calls": len(calls), "agents": len(per_agent),
            "largest_prompt_tokens": max(per_agent.values(), default=0)}


def count_lines(path: Path) -> int:
    if not Path(path).exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--mode", choices=["single", "orchestrated"], required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--trace-path", default="traces/orchestrator_trace.jsonl")
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", "gpt-6-luna"))
    parser.add_argument("--max-steps", type=int, default=20)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    prepare_workspace(workspace, Path(args.data_dir))
    config = AgentConfig(model=args.model, workspace=workspace, trace_path=Path(args.trace_path),
                         max_steps=args.max_steps, policy=dict(REVIEW_POLICY))

    first_line = count_lines(config.trace_path)
    if args.mode == "single":
        result = run_agent(args.task, config)
    else:
        result = run_orchestrator(args.task, config)

    print(result.answer)
    print()
    stats = context_stats(config.trace_path, first_line)
    print(f"Mode: {args.mode}, stopped because: {result.stop_reason}")
    print(f"Total tokens: {result.input_tokens + result.output_tokens} "
          f"({result.input_tokens} in, {result.output_tokens} out)")
    print(f"Model calls: {stats['model_calls']} across {stats['agents']} agent(s)")
    print(f"Largest single prompt: {stats['largest_prompt_tokens']} tokens")
