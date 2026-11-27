"""Checks for the runner's parts: the clock, state, the day's task, and the approver.

Each screen asks you to uncomment its own block. Earlier blocks keep running,
so a later change that breaks an earlier function shows up right away.

Run it from the lesson folder, starting from an empty test folder each time:
    rm -rf test_state && python check_parts.py
"""

from pathlib import Path

import permissions
from agent import DEFAULT_POLICY
from runner import build_day_task, load_state, next_day, queue_for_human, save_state


# Simulated Clocks: the clock's tick, and comparing days
# print(next_day("2026-06-30"))
# print("2026-06-09" < "2026-06-10")

# Persistent State: load a fresh state
# state = load_state("test_state", "2026-06-01")
# print(state)

# Atomic Writes: save a change and load it back
# state["completed_days"].append("2026-06-01")
# state["current_day"] = "2026-06-02"
# save_state("test_state", state)
# assert load_state("test_state", "2026-06-01") == state
# print("Saved and loaded the same state.")

# Fresh Context per Run: the task for June 7, from an 18-line sample log
# folder = Path("test_day_task")
# folder.mkdir(exist_ok=True)
# lines = [f"note {n}" for n in range(1, 19)]
# (folder / "progress.md").write_text("\n".join(lines), encoding="utf-8")
# done = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05", "2026-06-06"]
# sample = {"current_day": "2026-06-07", "completed_days": done, "tokens_used_total": 0, "pending_approvals": []}
# print(build_day_task("2026-06-07", sample, folder))

# Approval Queues: an alert request with nobody watching
# queued = {"current_day": "2026-06-07", "completed_days": [], "tokens_used_total": 0, "pending_approvals": []}
# permissions.APPROVER = queue_for_human(queued, "2026-06-07")
# print(permissions.decide("send_alert", {"event_ids": ["us7000srb1"]}, DEFAULT_POLICY))
# print(queued["pending_approvals"])
