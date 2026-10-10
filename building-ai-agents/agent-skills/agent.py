"""A data analysis agent.

This is the tool loop from the Function Calling lesson with three changes:

1. General tools (files, Python, shell) instead of one function per question.
2. Explicit stopping conditions: a final answer, a step limit, or a token budget.
3. A system prompt that tells the model to check its results before answering.
"""

import json
import os
import time
import uuid

from openai import OpenAI

import memory
import tools
from tracing import write_event

SYSTEM_PROMPT = """You are a data analysis agent. You answer questions about the data in your workspace.

Your workspace is a folder. The data is under data/. You can list and read files, write files, and run Python or shell commands with the workspace as the working directory.

How to work:
1. Explore first. List the files, read the first lines of each one you need, and check column names and value formats before analyzing.
2. Analyze with run_python. Print summaries and the numbers you need, never whole tables.
3. If code fails, read the error, fix the code, and run it again.
4. Check your result before answering. Make sure the numbers are plausible: row counts add up, dates fall in the expected range, and nothing is silently dropped. If a check fails, find out why.
5. Answer with the specific numbers, say how you computed them, and say what you checked.

Notes:
Keep NOTES.md in the workspace up to date with facts that will help on later questions: which file holds what, column names, value formats, quirks you found, and code that worked. Update it with write_file before you give your final answer. Keep it short; replace outdated lines instead of appending duplicates.

Large files:
Tool results are cut to a few thousand characters. For large files, use run_python and print only what you need. When a question covers several years, check whether a smaller summary file already has the counts you need before reading raw rows.
"""


def build_system_prompt(workspace):
    """The system prompt, plus notes from earlier runs if there are any."""
    notes = memory.load_notes(workspace)
    if notes:
        return SYSTEM_PROMPT + f"\nYour notes from earlier runs ({memory.NOTES_FILE}):\n\n{notes}\n"
    return SYSTEM_PROMPT


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
    ):
        self.model = model
        self.workspace = workspace
        self.trace_path = trace_path
        self.max_steps = max_steps
        self.max_tokens_total = max_tokens_total
        # gpt-6-luna only accepts tools on Chat Completions with reasoning off.
        # Set to None for providers that don't accept this parameter.
        self.reasoning_effort = reasoning_effort
        # Compact the conversation once a model call's input passes this size.
        self.compact_at_tokens = compact_at_tokens


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
    """Work on a task until the model answers or a limit is reached."""
    client = client or OpenAI()
    tools.WORKSPACE = config.workspace
    run_id = uuid.uuid4().hex[:12]
    files_before = workspace_files(config.workspace)

    messages = [
        {"role": "system", "content": build_system_prompt(config.workspace)},
        {"role": "user", "content": task},
    ]
    input_tokens = output_tokens = 0
    answer, stop_reason, step = None, "max_steps", 0

    while step < config.max_steps:
        step += 1
        request = {"model": config.model, "messages": messages, "tools": tools.tool_schemas()}
        if config.reasoning_effort is not None:
            request["reasoning_effort"] = config.reasoning_effort

        started = time.monotonic()
        try:
            response = client.chat.completions.create(**request)
        except Exception as e:
            write_event(config.trace_path, run_id, step, "error", result={"error": str(e)})
            answer, stop_reason = None, "error"
            break

        usage = response.usage
        input_tokens += usage.prompt_tokens
        output_tokens += usage.completion_tokens
        write_event(
            config.trace_path, run_id, step, "model_call",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

        message = response.choices[0].message

        # No tool calls means the model is giving its answer.
        if not message.tool_calls:
            answer, stop_reason = message.content, "final"
            write_event(config.trace_path, run_id, step, "final")
            break

        messages.append(message)
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                arguments = {}
                result = {"error": f"Arguments were not valid JSON: {e}"}
            else:
                write_event(config.trace_path, run_id, step, "tool_call", tool=name, args=arguments)
                started = time.monotonic()
                result = tools.call_tool(name, arguments)

            write_event(
                config.trace_path, run_id, step, "tool_result",
                tool=name, args=arguments, result=result,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            messages.append(memory.to_tool_message(tool_call.id, result))

        # Check the budget after the step, so the run stops before the next call.
        if input_tokens + output_tokens >= config.max_tokens_total:
            stop_reason = "budget"
            break

        # The last call's input size is what the next call will start from.
        if usage.prompt_tokens > config.compact_at_tokens:
            started = time.monotonic()
            messages, summary_usage = memory.compact(messages, client, config.model, config.reasoning_effort)
            input_tokens += summary_usage["input_tokens"]
            output_tokens += summary_usage["output_tokens"]
            write_event(
                config.trace_path, run_id, step, "compaction",
                result={"messages_after": len(messages)},
                input_tokens=summary_usage["input_tokens"],
                output_tokens=summary_usage["output_tokens"],
                duration_ms=int((time.monotonic() - started) * 1000),
            )

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
