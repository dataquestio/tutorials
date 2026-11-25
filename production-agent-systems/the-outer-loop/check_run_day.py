"""Check run_day with the fake model, so it makes no API calls.

It runs one normal day, then a day where the model can't be reached. That
second day should end the run with a ConnectionError traceback, and
state.json should still show what the first day saved.

Run it from the lesson folder, starting from an empty test folder each time:
    rm -rf test_run_day && python check_run_day.py
"""

from pathlib import Path

from agent import AgentConfig
from fake_model import FakeModel
from runner import load_state, run_day

workspace = Path("test_run_day")
config = AgentConfig(model="fake", workspace=workspace, trace_path=workspace / "trace.jsonl")

# run_day("2026-06-01", workspace / "state", config, FakeModel())
# print(load_state(workspace / "state", None))
# print((workspace / "state" / "progress.md").read_text())
# run_day("2026-06-02", workspace / "state", config, FakeModel(fail=True))
