"""A data analysis agent.

This is the tool loop from the Function Calling lesson with three changes:

1. General tools (files, Python, shell) instead of one function per question.
2. Explicit stopping conditions: a final answer, a step limit, or a token budget.
3. A system prompt that tells the model to check its results before answering.

This is starter code. Complete each TODO as the lesson walks through it.
"""

import json
import os
import time
import uuid

from openai import OpenAI

import tools
from tracing import write_event

# TODO:
# - Add a numbered "How to work" section
SYSTEM_PROMPT = """You are a data analysis agent. You answer questions about the data in your workspace.

Your workspace is a folder. The data is under data/. You can list and read files, write files, and run Python or shell commands with the workspace as the working directory.
"""


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
    """Work on a task until the model answers or a limit is reached.

    TODO:
    - Fill in the loop body at the TODO inside the while loop
    - Add tracing and bookkeeping at the other TODOs below
    """
    client = client or OpenAI()
    tools.WORKSPACE = config.workspace
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    # TODO:
    # - Add run_id for the trace
    # - Record files_before with workspace_files
    # - Set input_tokens and output_tokens to 0
    # - Set answer to None and stop_reason to "max_steps"

    step = 0
    while step < config.max_steps:
        step += 1
        # TODO:
        # - Build the request and call the model
        # - Return the reply's content if it has no tool_calls
        # - Append the reply and run each tool call
        # - Append each result as a tool message
        #
        # TODO:
        # - Place the provided write_event calls
        # - Add response.usage tokens to the totals
        # - Set stop_reason and break at each exit
        # - Wrap the model call in try/except
        ...

    # TODO:
    # - Write a "stop" trace event unless stop_reason is "final"
    # - Return an AgentResult instead of this string
    return "Reached the step limit without a final answer."
