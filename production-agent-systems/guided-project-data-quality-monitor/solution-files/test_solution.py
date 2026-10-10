"""Check your data quality monitor without calling a real model.

Every test uses a fake model client that plays back scripted responses, so
running this file costs nothing and needs no API key. The tests check the
machinery around the model: the loop, tools, permissions, skills, trace
log, outer loop, and scoring. They cannot tell you whether your agent's
judgment is good; your monitor's report does that.

Usage:
    python test_solution.py --data-dir <path/to/usgs_gp>
"""

import argparse
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_function_tool_call import Function

import permissions
import runner
import tools
from agent import AgentConfig, run_agent

DATA_DIR = None
TRACE_FIELDS = {
    "run_id": str, "step": int, "ts": str, "type": str, "tool": (str, type(None)),
    "args": (dict, type(None)), "result_preview": (str, type(None)), "is_error": bool,
    "input_tokens": (int, type(None)), "output_tokens": (int, type(None)), "duration_ms": int,
}
ALLOW_ALL = {name: "allow" for name in tools.TOOLS}


# ---------------------------------------------------------------------------
# The fake model
# ---------------------------------------------------------------------------

def completion(content=None, calls=(), prompt_tokens=100, completion_tokens=10):
    """A model response built from the same types the openai SDK returns."""
    tool_calls = [
        ChatCompletionMessageToolCall(
            id=f"call_{i}_{time.monotonic_ns()}", type="function",
            function=Function(name=name, arguments=json.dumps(args)),
        )
        for i, (name, args) in enumerate(calls)
    ] or None
    return ChatCompletion(
        id="fake", object="chat.completion", created=0, model="fake-model",
        choices=[Choice(index=0, finish_reason="tool_calls" if tool_calls else "stop",
                        message=ChatCompletionMessage(role="assistant", content=content, tool_calls=tool_calls))],
        usage=CompletionUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                              total_tokens=prompt_tokens + completion_tokens),
    )


class FakeClient:
    """Plays back scripted responses and remembers every request."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.chat = self
        self.completions = self

    def create(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        if not self.script:
            return completion("Done.")
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def message_field(message, field):
    return message[field] if isinstance(message, dict) else getattr(message, field)


def tool_messages(client):
    """Contents of every tool message the agent sent back to the model."""
    seen = []
    for request in client.requests:
        for message in request["messages"]:
            if message_field(message, "role") == "tool":
                content = message_field(message, "content")
                if content not in seen:
                    seen.append(content)
    return seen


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class MonitorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()
        (self.workspace / "data").symlink_to(Path(DATA_DIR).resolve(), target_is_directory=True)
        self.trace_path = Path(self.tmp.name) / "trace.jsonl"
        self.saved_approver = permissions.APPROVER

    def tearDown(self):
        permissions.APPROVER = self.saved_approver
        self.tmp.cleanup()

    def config(self, **overrides):
        settings = {"model": "fake-model", "workspace": self.workspace, "trace_path": self.trace_path,
                    "policy": dict(ALLOW_ALL)}
        settings.update(overrides)
        return AgentConfig(**settings)

    def trace(self):
        with open(self.trace_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]


class TestLoop(MonitorTestCase):
    def test_final_answer(self):
        client = FakeClient([completion(calls=[("list_files", {"path": "."})]), completion("All good.")])
        result = runner.run_day("2026-06-01", self.workspace / "state", self.config(), client)
        self.assertEqual(result.stop_reason, "final", "Loop: a reply without tool calls must stop with stop_reason 'final'")
        self.assertEqual(result.answer, "All good.", "Loop: the final reply must be returned as the answer")
        self.assertEqual(result.steps, 2, "Loop: steps must count model calls")

    def test_max_steps(self):
        client = FakeClient([completion(calls=[("list_files", {"path": "."})])] * 5)
        result = runner.run_day("2026-06-01", self.workspace / "state", self.config(max_steps=3), client)
        self.assertEqual(result.stop_reason, "max_steps", "Loop: hitting max_steps must stop with stop_reason 'max_steps'")
        self.assertEqual(len(client.requests), 3, "Loop: no model call may happen after max_steps")

    def test_token_budget(self):
        client = FakeClient([completion(calls=[("list_files", {"path": "."})], prompt_tokens=100, completion_tokens=10)] * 5)
        result = runner.run_day("2026-06-01", self.workspace / "state", self.config(max_tokens_total=150), client)
        self.assertEqual(result.stop_reason, "budget", "Loop: going over max_tokens_total must stop with stop_reason 'budget'")
        self.assertEqual(result.input_tokens + result.output_tokens, 220, "Loop: token counts must come from response.usage")

    def test_dispatches_tool_calls(self):
        client = FakeClient([completion(calls=[("day_summary", {"day": "2026-06-01"})]), completion("Done.")])
        runner.run_day("2026-06-01", self.workspace / "state", self.config(), client)
        self.assertTrue(any('"rows"' in m for m in tool_messages(client)),
                        "Loop: the scripted day_summary call must run and its result must go back to the model")

    def test_tool_errors_go_back_to_model(self):
        client = FakeClient([completion(calls=[("read_file", {"path": "no_such_file.txt"})]), completion("Done.")])
        result = runner.run_day("2026-06-01", self.workspace / "state", self.config(), client)
        self.assertEqual(result.stop_reason, "final", "Loop: a failing tool must not crash the run")
        self.assertTrue(any('"error"' in m for m in tool_messages(client)),
                        "Loop: tool errors must be returned to the model as {\"error\": ...}")


class TestTools(MonitorTestCase):
    def test_refuses_paths_outside_workspace(self):
        client = FakeClient([completion(calls=[("read_file", {"path": "../../../etc/passwd"})]), completion("Done.")])
        run_agent("Read a file.", self.config(), client)
        messages = tool_messages(client)
        self.assertTrue(messages and '"error"' in messages[0] and "root:" not in messages[0],
                        "Tools: file tools must refuse paths outside the workspace")

    def test_data_link_is_allowed(self):
        client = FakeClient([completion(calls=[("list_files", {"path": "data/days"})]), completion("Done.")])
        run_agent("List the feed.", self.config(), client)
        self.assertIn("2026-06-01.csv", tool_messages(client)[0], "Tools: the data/ link inside the workspace must be readable")

    def test_subprocess_has_no_secrets(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-not-a-real-key"
        os.environ["EXAMPLE_TOKEN"] = "token-test-value"
        try:
            code = "import os; print(sorted(k for k in os.environ if k.endswith(('_API_KEY', '_TOKEN'))))"
            client = FakeClient([completion(calls=[("run_python", {"code": code})]), completion("Done.")])
            run_agent("Check the environment.", self.config(), client)
            output = tool_messages(client)[0]
            self.assertIn("[]", output, "Tools: commands must run without any *_API_KEY or *_TOKEN variables")
            self.assertNotIn("sk-test-not-a-real-key", output, "Tools: the API key must never reach a subprocess")
        finally:
            del os.environ["OPENAI_API_KEY"]
            del os.environ["EXAMPLE_TOKEN"]

    def test_long_output_is_truncated(self):
        client = FakeClient([completion(calls=[("run_python", {"code": "print('x' * 50000)"})]), completion("Done.")])
        run_agent("Print a lot.", self.config(), client)
        output = tool_messages(client)[0]
        self.assertLess(len(output), 50000, "Tools: long tool output must be truncated before it goes back to the model")
        self.assertIn("truncat", output.lower(), "Tools: truncated output must say that it was truncated")


class TestPermissions(MonitorTestCase):
    def test_deny_blocks(self):
        client = FakeClient([completion(calls=[("write_file", {"path": "x.txt", "content": "hi"})]), completion("Done.")])
        run_agent("Write a file.", self.config(policy={**ALLOW_ALL, "write_file": "deny"}), client)
        self.assertFalse((self.workspace / "x.txt").exists(), "Permissions: a 'deny' tool must not run")
        self.assertIn('"error"', tool_messages(client)[0], "Permissions: a denied call must return an error to the model")

    def test_ask_calls_approve(self):
        asked = []
        permissions.APPROVER = lambda tool, args: asked.append((tool, args)) or True
        client = FakeClient([completion(calls=[("list_files", {"path": "."})]), completion("Done.")])
        run_agent("List files.", self.config(policy={**ALLOW_ALL, "list_files": "ask"}), client)
        self.assertEqual(asked, [("list_files", {"path": "."})], "Permissions: an 'ask' tool must call approve(tool, args)")

    def test_unlisted_tool_asks(self):
        asked = []
        permissions.APPROVER = lambda tool, args: asked.append(tool) or False
        policy = {k: v for k, v in ALLOW_ALL.items() if k != "list_files"}
        client = FakeClient([completion(calls=[("list_files", {"path": "."})]), completion("Done.")])
        run_agent("List files.", self.config(policy=policy), client)
        self.assertEqual(asked, ["list_files"], "Permissions: a tool missing from the policy must be treated as 'ask'")

    def test_decisions_are_traced(self):
        client = FakeClient([completion(calls=[("write_file", {"path": "x.txt", "content": "hi"})]), completion("Done.")])
        run_agent("Write a file.", self.config(policy={**ALLOW_ALL, "write_file": "deny"}), client)
        approvals = [e for e in self.trace() if e["type"] == "approval" and e["tool"] == "write_file"]
        self.assertTrue(approvals, "Permissions: every decision must be written as an 'approval' trace event")

    def test_unattended_approvals_are_queued(self):
        args = {"message": "test alert", "event_ids": ["abc"]}
        client = FakeClient([completion(calls=[("send_alert", args)]), completion("Done.")])
        runner.run_day("2026-06-01", self.workspace / "state", self.config(policy={**ALLOW_ALL, "send_alert": "ask"}), client)
        state = json.loads((self.workspace / "state" / "state.json").read_text())
        self.assertEqual(len(state["pending_approvals"]), 1, "Permissions: an 'ask' call in run_day must land in pending_approvals")
        self.assertFalse((self.workspace / "state" / "alerts.jsonl").exists(),
                         "Permissions: a queued alert must not be sent before a human approves it")


def read_skill_files():
    found = {}
    for path in sorted((Path(__file__).resolve().parent / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        _, frontmatter, body = text.split("---", 2)
        meta = {}
        for line in frontmatter.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        found[meta["name"]] = {"description": meta["description"], "body": body.strip()}
    return found


class TestSkills(MonitorTestCase):
    def test_index_has_name_and_description_only(self):
        skills_found = read_skill_files()
        self.assertTrue(skills_found, "Skills: there must be at least one skills/<name>/SKILL.md")
        client = FakeClient([completion("Done.")])
        run_agent("Hello.", self.config(), client)
        system = message_field(client.requests[0]["messages"][0], "content")
        for name, skill in skills_found.items():
            self.assertIn(name, system, f"Skills: the system prompt must list the skill name '{name}'")
            self.assertIn(skill["description"], system, f"Skills: the system prompt must include the description of '{name}'")
            body_line = next(line for line in skill["body"].splitlines() if len(line) > 40)
            self.assertNotIn(body_line, system, f"Skills: the body of '{name}' must not be in the system prompt")

    def test_load_skill_returns_body(self):
        name, skill = next(iter(read_skill_files().items()))
        client = FakeClient([completion(calls=[("load_skill", {"name": name})]), completion("Done.")])
        run_agent("Load a skill.", self.config(), client)
        body_line = next(line for line in skill["body"].splitlines() if len(line) > 40)
        self.assertIn(json.dumps(body_line)[1:-1][:60], tool_messages(client)[0], "Skills: load_skill must return the skill body")


class TestTrace(MonitorTestCase):
    def test_trace_fields(self):
        client = FakeClient([completion(calls=[("list_files", {"path": "."})]), completion("Done.")])
        run_agent("List files.", self.config(), client)
        events = self.trace()
        self.assertTrue(events, "Trace: run_agent must write trace events")
        for event in events:
            for field, kind in TRACE_FIELDS.items():
                self.assertIn(field, event, f"Trace: every event needs the field '{field}'")
                self.assertIsInstance(event[field], kind, f"Trace: '{field}' has the wrong type in {event['type']} event")
        types = {e["type"] for e in events}
        for needed in ("model_call", "tool_call", "tool_result", "final"):
            self.assertIn(needed, types, f"Trace: expected a '{needed}' event")


class TestOuterLoop(MonitorTestCase):
    def test_resume_after_interruption(self):
        state_dir = self.workspace / "state"
        runner.run_day("2026-06-01", state_dir, self.config(),
                       FakeClient([completion(calls=[("apply_day_to_catalog", {"day": "2026-06-01"})]), completion("Done.")]))
        crash = FakeClient([completion(calls=[("apply_day_to_catalog", {"day": "2026-06-02"})]), KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            runner.run_day("2026-06-02", state_dir, self.config(), crash)

        state = json.loads((state_dir / "state.json").read_text())
        self.assertEqual(set(state), {"current_day", "completed_days", "tokens_used_total", "pending_approvals"} | set(state),
                         "Outer loop: state.json must be a JSON object")
        for key in ("current_day", "completed_days", "tokens_used_total", "pending_approvals"):
            self.assertIn(key, state, f"Outer loop: state.json needs '{key}'")
        self.assertEqual(state["completed_days"], ["2026-06-01"], "Outer loop: an interrupted day must not be marked complete")
        self.assertEqual(state["current_day"], "2026-06-02", "Outer loop: after day N completes, the run must resume at day N+1")

        with open(state_dir / "catalog.jsonl", encoding="utf-8") as f:
            catalog = [json.loads(line) for line in f]
        self.assertTrue(catalog and all("id" in e for e in catalog), "Outer loop: catalog.jsonl must hold one event with an 'id' per line")

        runner.run_day("2026-06-02", state_dir, self.config(), FakeClient([completion("Done.")]))
        state = json.loads((state_dir / "state.json").read_text())
        self.assertEqual(state["completed_days"], ["2026-06-01", "2026-06-02"], "Outer loop: the repeated day must complete normally")


class TestAnswerKey(MonitorTestCase):
    def test_score_against_planted_issues(self):
        try:
            import dq_monitor
        except ImportError:
            self.fail("Answer key: dq_monitor.py with a score(flags, planted, days) function is missing")

        with open(Path(DATA_DIR) / "planted_issues.jsonl", encoding="utf-8") as f:
            planted = [json.loads(line) for line in f]
        days = ["2026-06-10", "2026-06-19", "2026-07-03"]
        state_dir = self.workspace / "state"
        for day in days:
            calls = [("flag_anomaly", {"day": issue["day"], "kind": issue["type"], "details": "scripted",
                                       "event_ids": [issue["details"]["event_id"]] if "event_id" in issue["details"] else []})
                     for issue in planted if issue["day"] == day]
            if day == "2026-07-03":
                calls.append(("flag_anomaly", {"day": day, "kind": "volume_drop", "details": "wrong on purpose"}))
            runner.run_day(day, state_dir, self.config(), FakeClient([completion(calls=calls), completion("Done.")]))

        with open(state_dir / "flags.jsonl", encoding="utf-8") as f:
            flags = [json.loads(line) for line in f]
        result = dq_monitor.score(flags, planted, days)
        expected_issues = sum(1 for issue in planted if issue["day"] in days)
        self.assertEqual(result["planted_issues"], expected_issues, "Answer key: score() must count the issues on the given days")
        self.assertEqual(result["issues_found"], expected_issues, "Answer key: every scripted flag for a planted issue must count as found")
        self.assertEqual(result["recall"], 1.0, "Answer key: recall must be 1.0 when every issue is flagged")
        self.assertAlmostEqual(result["precision"], round(expected_issues / (expected_issues + 1), 3), places=3,
                               msg="Answer key: one wrong flag must lower precision to found / (found + 1)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Folder with days/ and planted_issues.jsonl")
    args, rest = parser.parse_known_args()
    DATA_DIR = args.data_dir
    unittest.main(argv=[sys.argv[0], *rest])
