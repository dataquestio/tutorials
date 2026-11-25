"""Check run_range's exits with the fake model, so it makes no API calls.

Four calls on the same folder, at 1,050 tokens per day:
1. June 1 to 3, which should stop with "done".
2. Through June 5, which should resume at June 4 and stop with "done".
3. Through June 9 with a total budget of 7,000 tokens, which should stop
   with "total_budget" after June 7.
4. Through June 9 with a model that can't be reached, which should end with
   a ConnectionError traceback and leave June 8 as the day to resume.

Run it from the lesson folder, starting from an empty test folder each time:
    rm -rf test_exits && python check_exits.py
"""

from pathlib import Path

from agent import AgentConfig
from fake_model import FakeModel
from runner import run_range

workspace = Path("test_exits")
config = AgentConfig(model="fake", workspace=workspace, trace_path=workspace / "trace.jsonl")

# print("Stopped:", run_range("2026-06-01", "2026-06-03", config, 100_000, FakeModel()))
# print("Stopped:", run_range("2026-06-01", "2026-06-05", config, 100_000, FakeModel()))
# print("Stopped:", run_range("2026-06-01", "2026-06-09", config, 7_000, FakeModel()))
# run_range("2026-06-01", "2026-06-09", config, 100_000, FakeModel(fail=True))
