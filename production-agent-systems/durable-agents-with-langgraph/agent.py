"""The earthquake feed monitor agent.

run_agent works on one task with a fresh conversation: it calls the model,
runs the tools the model asks for (if the policy allows them), and stops on
a final answer, the step limit, or the token budget.
"""

import json
import os
import time
import uuid

from openai import OpenAI

import memory
import permissions
import skills
import tools
from tracing import write_event

SYSTEM_PROMPT = """You are an unattended monitor for a daily earthquake feed from the USGS catalog.

Your workspace is a folder. The feed is under data/days/, one CSV file per day. Your state is under state/: the running catalog, flags for human review, alerts, and progress.md, a log that previous runs wrote for you. NOTES.md is your scratch file.

Use the feed tools (day_summary, apply_day_to_catalog, flag_anomaly, append_progress, send_alert) for routine work. Use run_python only when you need an analysis the feed tools cannot do. Never print whole files.

Skills hold detailed procedures. Load a skill with load_skill when its description matches what you are doing.
Available skills:
{skill_index}

Some tools need human approval. If a call is denied, do not retry it; mention it in your final summary.
End every task with a short summary of what you did and found."""

DEFAULT_POLICY = {
    "list_files": "allow",
    "read_file": "allow",
    "write_file": "allow",
    "run_python": "allow",
    "run_shell": "deny",
    "load_skill": "allow",
    "day_summary": "allow",
    "apply_day_to_catalog": "allow",
    "flag_anomaly": "allow",
    "append_progress": "allow",
    "send_alert": "ask",
}


class AgentConfig:
    def __init__(
        self,
        model,
        workspace,
        trace_path,
        max_steps=20,
        max_tokens_total=200_000,
        reasoning_effort="none",
        compact_at_tokens=60_000,
        policy=None,
    ):
        self.model = model
        self.workspace = workspace
        self.trace_path = trace_path
        self.max_steps = max_steps
        self.max_tokens_total = max_tokens_total
        # gpt-6-luna only accepts tools on Chat Completions with reasoning off.
        # Set to None for providers that don't accept this parameter.
        self.reasoning_effort = reasoning_effort
        self.compact_at_tokens = compact_at_tokens
        self.policy = policy if policy is not None else dict(DEFAULT_POLICY)


class AgentResult:
    def __init__(self, answer, stop_reason, steps, input_tokens, output_tokens, files_written):
        self.answer = answer
        self.stop_reason = stop_reason  # "final", "max_steps", "budget", or "error"
        self.steps = steps
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.files_written = files_written


def workspace_files(workspace):
    """All files in the workspace, without following the data/ link."""
    found = set()
    for folder, _, names in os.walk(workspace):
        for name in names:
            found.add(os.path.relpath(os.path.join(folder, name), workspace))
    return found


def run_agent(task, config, client=None):
    """Work on one task with a fresh conversation until done or out of budget."""
    client = client or OpenAI()
    tools.WORKSPACE = config.workspace
    run_id = uuid.uuid4().hex[:12]
    files_before = workspace_files(config.workspace)

    extra = {"tools": tools.tool_schemas()}
    if config.reasoning_effort is not None:
        extra["reasoning_effort"] = config.reasoning_effort

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(skill_index=skills.skill_index())},
        {"role": "user", "content": task},
    ]
    input_tokens = output_tokens = last_prompt_tokens = 0
    answer, stop_reason, step = None, "max_steps", 0

    while step < config.max_steps:
        step += 1

        messages, usage = memory.maybe_compact(
            messages, last_prompt_tokens, config.compact_at_tokens,
            client, config.model, {**extra, "tool_choice": "none"},
        )
        if usage is not None:
            input_tokens += usage.prompt_tokens
            output_tokens += usage.completion_tokens
            write_event(config.trace_path, run_id, step, "compaction",
                        input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens)

        started = time.monotonic()
        try:
            response = client.chat.completions.create(model=config.model, messages=messages, **extra)
        except Exception as e:
            write_event(config.trace_path, run_id, step, "error", result={"error": str(e)})
            stop_reason = "error"
            break

        usage = response.usage
        last_prompt_tokens = usage.prompt_tokens
        input_tokens += usage.prompt_tokens
        output_tokens += usage.completion_tokens
        write_event(config.trace_path, run_id, step, "model_call",
                    input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens,
                    duration_ms=int((time.monotonic() - started) * 1000))

        message = response.choices[0].message
        if not message.tool_calls:
            answer, stop_reason = message.content, "final"
            write_event(config.trace_path, run_id, step, "final")
            break

        messages.append(message)
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            started = time.monotonic()
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                arguments, result = {}, {"error": f"Arguments were not valid JSON: {e}"}
            else:
                write_event(config.trace_path, run_id, step, "tool_call", tool=name, args=arguments)
                decision = permissions.decide(name, arguments, config.policy)
                write_event(config.trace_path, run_id, step, "approval", tool=name, args=arguments,
                            result={"decision": decision})
                if decision == "deny":
                    result = {"error": f"Permission denied for {name}. Do not retry."}
                else:
                    result = tools.call_tool(name, arguments)
                    if name == "load_skill" and "error" not in result:
                        write_event(config.trace_path, run_id, step, "skill_load", tool=name, args=arguments)

            write_event(config.trace_path, run_id, step, "tool_result", tool=name, args=arguments, result=result,
                        duration_ms=int((time.monotonic() - started) * 1000))
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tools.format_result(result)})

        if input_tokens + output_tokens >= config.max_tokens_total:
            stop_reason = "budget"
            break

    if stop_reason != "final":
        write_event(config.trace_path, run_id, step, "stop", result={"stop_reason": stop_reason})

    return AgentResult(
        answer=answer,
        stop_reason=stop_reason,
        steps=step,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        files_written=sorted(workspace_files(config.workspace) - files_before),
    )
