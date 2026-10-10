"""Watch the agent loop recover from a failed tool call.

Current models rarely fail on a small, clean dataset like this one: they
explore first and usually get the code right. In production, with bigger
codebases, messier data, and longer runs, failures are routine, and the loop
has to turn them into the next step instead of a crash.

To show that reliably, this demo replaces the model with a script. The
model's turns are fixed, but the tools run for real against your data, so
the error and the corrected result are genuine:

1. The "model" assumes the column names are complaint_type and created_at.
2. run_python fails, and the traceback goes back into the conversation.
3. The "model" reads the header to see the real column names.
4. It runs corrected code, and the loop ends with the real result.

No API key needed.

Usage:
    python demo_recovery.py --data-dir <path/to/nyc311>
"""

import argparse
import json
import tempfile
from pathlib import Path

from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion import Choice

from agent import AgentConfig, run_agent
from run import prepare_workspace

WRONG_CODE = """import pandas as pd
df = pd.read_csv("data/service_requests.csv", usecols=["complaint_type", "created_at"])
noise = df[df.complaint_type.str.startswith("Noise")]
print(noise.groupby(noise.created_at.str[:7]).size())
"""

FIXED_CODE = """import pandas as pd
df = pd.read_csv("data/service_requests.csv", usecols=["problem", "created_date"])
noise = df[df.problem.str.startswith("Noise")]
month = pd.to_datetime(noise.created_date, format="%m/%d/%Y %I:%M:%S %p").dt.strftime("%Y-%m")
print(month.value_counts().sort_index().to_string())
"""


def reply(content=None, call=None):
    """One model turn in the same shape the OpenAI SDK returns."""
    tool_calls = None
    if call:
        name, args = call
        tool_calls = [ChatCompletionMessageFunctionToolCall(
            id=f"call_{name}", type="function", function={"name": name, "arguments": json.dumps(args)})]
    return ChatCompletion(
        id="scripted", object="chat.completion", created=0, model="scripted",
        choices=[Choice(index=0, finish_reason="tool_calls" if tool_calls else "stop",
                        message=ChatCompletionMessage(role="assistant", content=content, tool_calls=tool_calls))],
        usage=CompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


class ScriptedModel:
    """Plays the model's side. It prints each tool result it receives."""

    def __init__(self):
        self.chat = self.completions = self
        self.turn = 0

    def create(self, **request):
        last = request["messages"][-1]
        if isinstance(last, dict) and last.get("role") == "tool":
            result = json.loads(last["content"])
            shown = result.get("stderr") or result.get("stdout") or result
            print(f"   tool result:\n{indent(shown if isinstance(shown, str) else json.dumps(shown)[:400])}")
        self.turn += 1
        if self.turn == 1:
            print("1. Model assumes columns complaint_type and created_at and runs code.")
            return reply(call=("run_python", {"code": WRONG_CODE}))
        if self.turn == 2:
            print("2. Model sees the error and reads the header to check the real columns.")
            return reply(call=("read_file", {"path": "data/service_requests.csv", "max_lines": 1}))
        if self.turn == 3:
            print("3. Model fixes the code with the real column names and date format.")
            return reply(call=("run_python", {"code": FIXED_CODE}))
        print("4. Model answers with the result.")
        return reply(content="Noise complaints per month, summer 2026:\n" + result["stdout"])


def indent(text: str) -> str:
    lines = text.strip().splitlines()[-6:]
    return "\n".join("      " + line for line in lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()

    workspace = Path(tempfile.mkdtemp()) / "workspace"
    prepare_workspace(workspace, Path(args.data_dir))
    config = AgentConfig(model="scripted", workspace=workspace, trace_path=workspace.parent / "trace.jsonl")

    result = run_agent("Count noise complaints per month in summer 2026.", config, client=ScriptedModel())
    print(f"\nStopped because: {result.stop_reason} after {result.steps} steps")
    print(result.answer)
    print(f"Trace: {config.trace_path}")
