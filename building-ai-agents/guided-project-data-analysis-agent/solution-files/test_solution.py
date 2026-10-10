"""Check your data analysis agent without calling a real model.

These tests replace the model with a fake client that returns scripted
responses, so they cost nothing and need no API key. They check that the
agent's machinery works: the loop, tools, permissions, skills, and trace.
They can't check whether your answers are right; that's what the question
set is for.

Usage:
    python test_solution.py --data-dir <path/to/dohmh>
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion import Choice

import agent
import memory
import permissions
import skills
import tools

DATA_DIR = None
TRACE_FIELDS = {
    "run_id": str, "step": int, "ts": str, "type": str, "tool": (str, type(None)), "args": (dict, type(None)),
    "result_preview": (str, type(None)), "is_error": bool, "input_tokens": (int, type(None)),
    "output_tokens": (int, type(None)), "duration_ms": int,
}


def response(content=None, calls=(), prompt_tokens=100, completion_tokens=10):
    """Build a response in the same shape the OpenAI SDK returns."""
    tool_calls = [
        ChatCompletionMessageFunctionToolCall(
            id=f"call_{i}", type="function", function={"name": name, "arguments": json.dumps(args)}
        )
        for i, (name, args) in enumerate(calls)
    ]
    message = ChatCompletionMessage(role="assistant", content=content, tool_calls=tool_calls or None)
    finish = "tool_calls" if tool_calls else "stop"
    return ChatCompletion(
        id="fake", object="chat.completion", created=0, model="fake-model",
        choices=[Choice(index=0, finish_reason=finish, message=message)],
        usage=CompletionUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                              total_tokens=prompt_tokens + completion_tokens),
    )


class FakeClient:
    """Stands in for openai.OpenAI(). Returns scripted responses in order."""

    def __init__(self, responses, repeat_last=False):
        self.responses, self.repeat_last, self.requests = list(responses), repeat_last, []
        self.chat = self
        self.completions = self

    def create(self, **request):
        self.requests.append(request)
        if len(self.responses) == 1 and self.repeat_last:
            return self.responses[0]
        return self.responses.pop(0)

    def tool_messages(self):
        """Tool results the agent sent back in its last request."""
        return [m for m in self.requests[-1]["messages"] if isinstance(m, dict) and m.get("role") == "tool"]


class AgentTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        (self.workspace / "data").symlink_to(Path(DATA_DIR).resolve(), target_is_directory=True)
        self.trace = self.tmp / "trace.jsonl"
        self.approvals = []
        self.old_approver = permissions.APPROVER

    def tearDown(self):
        permissions.APPROVER = self.old_approver
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, **overrides):
        settings = dict(model="fake-model", workspace=self.workspace, trace_path=self.trace)
        settings.update(overrides)
        return agent.AgentConfig(**settings)

    def events(self):
        return [json.loads(line) for line in self.trace.read_text().splitlines()]


class TestLoop(AgentTestCase):
    def test_final_answer_stops_the_loop(self):
        result = agent.run_agent("q", self.config(), client=FakeClient([response("42")]))
        self.assertEqual(result.stop_reason, "final", "A reply without tool calls must end the run with stop_reason 'final'")
        self.assertEqual(result.answer, "42", "The final reply must be returned as the answer")

    def test_max_steps_stops_the_loop(self):
        client = FakeClient([response(calls=[("list_files", {"path": "."})])], repeat_last=True)
        result = agent.run_agent("q", self.config(max_steps=3), client=client)
        self.assertEqual(result.stop_reason, "max_steps", "A run that never answers must stop with 'max_steps'")
        self.assertEqual(len(client.requests), 3, "max_steps must limit the number of model calls")

    def test_token_budget_stops_the_loop(self):
        client = FakeClient([response(calls=[("list_files", {"path": "."})], prompt_tokens=600)], repeat_last=True)
        result = agent.run_agent("q", self.config(max_tokens_total=1000), client=client)
        self.assertEqual(result.stop_reason, "budget", "Passing max_tokens_total must stop the run with 'budget'")
        self.assertEqual(result.input_tokens, 1200, "Input tokens must be summed from response.usage")

    def test_tool_results_reach_the_model(self):
        client = FakeClient([
            response(calls=[("read_file", {"path": "data/inspections.csv", "max_lines": 2})]),
            response("done"),
        ])
        agent.run_agent("q", self.config(), client=client)
        content = client.tool_messages()[0]["content"]
        self.assertIn("CAMIS", content, "read_file on data/inspections.csv must return the header row to the model")

    def test_tool_errors_go_back_to_the_model(self):
        client = FakeClient([
            response(calls=[("read_file", {"path": "missing.csv"}), ("no_such_tool", {})]),
            response("done"),
        ])
        result = agent.run_agent("q", self.config(), client=client)
        for message in client.tool_messages():
            self.assertIn("error", json.loads(message["content"].split("\n[truncated")[0]),
                          "Failed tool calls must come back as {'error': ...} instead of crashing")
        self.assertEqual(result.stop_reason, "final", "The run must continue after a tool error")


class TestTools(AgentTestCase):
    def setUp(self):
        super().setUp()
        tools.WORKSPACE = self.workspace

    def test_paths_outside_the_workspace_are_refused(self):
        self.assertIn("error", tools.read_file("../outside.txt"), "File tools must refuse paths outside the workspace")
        self.assertIn("error", tools.write_file("../outside.txt", "x"), "File tools must refuse paths outside the workspace")

    def test_data_link_is_readable(self):
        result = tools.read_file("data/inspections.csv", max_lines=1)
        self.assertNotIn("error", result, "The data/ link inside the workspace must be readable")

    def test_commands_dont_see_api_keys(self):
        os.environ["TEST_SECRET_API_KEY"] = "do-not-leak"
        try:
            result = tools.run_python("import os; print(os.environ.get('TEST_SECRET_API_KEY'))")
        finally:
            del os.environ["TEST_SECRET_API_KEY"]
        self.assertNotIn("do-not-leak", result["stdout"], "Variables ending in _API_KEY must be removed from the command environment")

    def test_long_output_is_truncated(self):
        text = memory.truncate("x" * 50_000)
        self.assertLess(len(text), 50_000, "Tool output longer than the limit must be cut")
        self.assertIn("truncated", text, "Cut output must say that it was cut")


class TestPermissions(AgentTestCase):
    def test_deny_blocks_the_tool(self):
        client = FakeClient([response(calls=[("run_shell", {"command": "echo hi"})]), response("done")])
        agent.run_agent("q", self.config(policy={"run_shell": "deny"}), client=client)
        result = json.loads(client.tool_messages()[0]["content"])
        self.assertIn("error", result, "A denied tool must not run and must return an error")
        decisions = [e for e in self.events() if e["type"] == "approval"]
        self.assertTrue(decisions, "Every permission decision must be written as an 'approval' trace event")

    def test_ask_calls_the_approver(self):
        permissions.APPROVER = lambda tool, args: self.approvals.append(tool) or True
        client = FakeClient([response(calls=[("run_shell", {"command": "echo hi"})]), response("done")])
        agent.run_agent("q", self.config(policy={"run_shell": "ask"}), client=client)
        self.assertEqual(self.approvals, ["run_shell"], "A tool set to 'ask' must call permissions.approve")
        self.assertIn("hi", client.tool_messages()[0]["content"], "An approved tool must run")

    def test_unlisted_tools_need_approval(self):
        permissions.APPROVER = lambda tool, args: self.approvals.append(tool) or False
        self.assertEqual(permissions.decide("write_file", {}, {}), "rejected", "Tools missing from the policy must default to 'ask'")


class TestSkills(unittest.TestCase):
    def test_there_is_at_least_one_skill(self):
        self.assertTrue(skills.discover_skills(), "The project needs at least one skill in skills/<name>/SKILL.md")

    def test_index_lists_only_names_and_descriptions(self):
        index = skills.skill_index()
        for name, info in skills.discover_skills().items():
            self.assertIn(name, index, "The skill index must list every skill's name")
            self.assertIn(info["description"], index, "The skill index must list every skill's description")
            body = skills.load_skill(name)["instructions"]
            self.assertNotIn(body[:80], index, "The skill index must not include skill bodies")

    def test_load_skill_returns_the_body(self):
        for name in skills.discover_skills():
            result = skills.load_skill(name)
            self.assertTrue(result.get("instructions"), "load_skill must return the skill's instructions")
        self.assertIn("error", skills.load_skill("no-such-skill"), "Unknown skills must return an error")


class TestTrace(AgentTestCase):
    def test_every_event_has_the_trace_fields(self):
        client = FakeClient([response(calls=[("list_files", {"path": "."})]), response("done")])
        agent.run_agent("q", self.config(), client=client)
        events = self.events()
        self.assertTrue(events, "run_agent must write trace events")
        for event in events:
            for field, kind in TRACE_FIELDS.items():
                self.assertIn(field, event, f"Every trace event needs the field '{field}'")
                self.assertIsInstance(event[field], kind, f"Trace field '{field}' has the wrong type")
        types = {e["type"] for e in events}
        for expected in ("model_call", "tool_call", "tool_result", "final"):
            self.assertIn(expected, types, f"A run with a tool call must trace a '{expected}' event")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Folder with inspections.csv")
    args, rest = parser.parse_known_args()
    DATA_DIR = args.data_dir
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
