"""A data analysis agent.

This is the tool loop from the Function Calling lesson with three changes:

1. General tools (files, Python, shell) instead of one function per question.
2. Explicit stopping conditions: a final answer, a step limit, or a token budget.
3. A system prompt that tells the model to check its results before answering.

This is the starter. You fill it in as the lesson walks through it:
  - the run_agent loop body (the scaffold is below)
  - a "How to work" section added to SYSTEM_PROMPT
  - the provided write_event tracing calls placed into run_agent
  - run_agent returning an AgentResult instead of a plain string

AgentConfig, AgentResult, and workspace_files are provided for you.
"""

import json
import os
import time
import uuid

from openai import OpenAI

import tools
from tracing import write_event

# You'll expand this prompt with a numbered "How to work" section: explore
# first, analyze by printing summaries, fix errors and retry, check results
# for plausibility, and answer with what was computed and checked.
SYSTEM_PROMPT = """You are a data analysis agent. You answer questions about the data in your workspace.

Your workspace is a folder. The data is under data/. You can list and read files, write files, and run Python or shell commands with the workspace as the working directory.
"""


# Provided. The agent's settings. `trace_path` is used once you add tracing,
# and `max_tokens_total` once you add the token budget.
class AgentConfig:
    def __init__(
        self,
        model,
        workspace,
        trace_path,
        max_steps=20,
        max_tokens_total=200_000,
        reasoning_effort="none",
    ):
        self.model = model
        self.workspace = workspace
        self.trace_path = trace_path
        self.max_steps = max_steps
        self.max_tokens_total = max_tokens_total
        # gpt-6-luna only accepts tools on Chat Completions with reasoning off.
        # Set to None for providers that don't accept this parameter.
        self.reasoning_effort = reasoning_effort


# Provided. What a run reports back. You return one of these once run_agent
# reports a full result instead of a plain string.
class AgentResult:
    def __init__(self, answer, stop_reason, steps, input_tokens, output_tokens, files_written):
        self.answer = answer
        self.stop_reason = stop_reason  # "final", "max_steps", "budget", or "error"
        self.steps = steps
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.files_written = files_written


# Provided. Lists every file in the workspace, without following the data/ link.
# run_agent uses it to report which files the agent wrote.
def workspace_files(workspace):
    found = set()
    for folder, _, names in os.walk(workspace):
        for name in names:
            found.add(os.path.relpath(os.path.join(folder, name), workspace))
    return found


def run_agent(task, config, client=None):
    """Work on a task until the model answers or a limit is reached."""
    client = client or OpenAI()
    tools.WORKSPACE = config.workspace
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    # Later you'll add a run_id = uuid.uuid4().hex[:12] here for the trace, plus
    # the result bookkeeping: files_before = workspace_files(config.workspace),
    # input_tokens = output_tokens = 0, and answer, stop_reason = None, "max_steps".

    step = 0
    while step < config.max_steps:
        step += 1
        # Fill in the loop body:
        #   - build the request (model, messages, tools.tool_schemas(), and add
        #     reasoning_effort only when config.reasoning_effort is not None),
        #     then call the model and take response.choices[0].message
        #   - if the reply has no tool_calls, return its content
        #   - otherwise append the reply, and for each tool call: read its name,
        #     parse its arguments with json.loads (return an error if the JSON is
        #     not valid), run it with tools.call_tool, and append the result as a
        #     tool message (tool_call_id + the result as a JSON string)
        #
        # Later you'll place the provided write_event tracing calls at the marked
        # points, track tokens from response.usage, set stop_reason at each exit
        # (final / error / budget), wrap the model call in try/except, and break
        # instead of returning.
        ...

    # Later, after the loop, write a "stop" trace event when stop_reason is not
    # "final", then return an AgentResult instead of the string below.
    return "Reached the step limit without a final answer."
