"""The outer loop: run the monitor once per simulated day.

Each day gets a brand-new agent conversation. What carries over between
days lives in files under state/:

    state.json     where the loop is: current day, completed days, tokens used,
                   and approvals waiting for a human
    progress.md    notes the agent leaves for its next run
    catalog.jsonl  the running event catalog (written by apply_day_to_catalog)

The imports, RECENT_PROGRESS_LINES, and next_day are provided. Below the
"YOUR OUTER LOOP" divider, each function already has its signature in place
and you fill in the body as the lesson walks through it:
  - load_state and save_state, to read and safely write state.json
  - recent_progress and build_day_task, to give each day a fresh task
  - queue_for_human, to hold approvals when nobody is watching
  - run_day, to run the agent on one day and commit it
  - run_range, the loop over days and its exits
  - the budgets in the command-line block at the bottom (the rest of that
    block is provided)

Usage (once you've written it):
    python runner.py --data-dir <path/to/usgs> --start 2026-06-01 --end 2026-06-07
"""

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

import permissions
from agent import AgentConfig, run_agent
from run import prepare_workspace

RECENT_PROGRESS_LINES = 15


def next_day(day):
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


# ===========================================================================
# YOUR OUTER LOOP
# ===========================================================================


def load_state(state_dir, start_day):
    """Read state.json, or start fresh at start_day."""
    # Fill in the body. Return the state dictionary: current_day,
    # completed_days, tokens_used_total, and pending_approvals. Use what's
    # saved in state_dir if there is a state.json, otherwise a fresh state.
    ...


def save_state(state_dir, state):
    """Write state.json so that a crash never leaves a half-written file."""
    # Fill in the body. Save state as state.json in state_dir. A crash partway
    # through must leave either the old file or the new one, never half of one.
    ...


def recent_progress(state_dir):
    # Fill in the body. Return the most recent lines of progress.md in state_dir
    # as one string (at most RECENT_PROGRESS_LINES), or "(no earlier runs)" if
    # there's no progress.md yet.
    ...


def build_day_task(day, state, state_dir):
    """The task for one daily run. Everything the agent needs from earlier days is in here or in state/."""
    # Fill in the body. Return the task text for one day. It's all the agent
    # knows about earlier days, so it carries the day to process, a short
    # summary of the state, and the most recent progress notes.
    ...


def queue_for_human(state, day):
    """An approver for unattended runs: record the request and say no for now."""
    # Fill in the body. Return an approver function, approver(tool, args), that
    # records each request in state["pending_approvals"] and refuses it for now.
    ...


def run_day(day, state_dir, config, client=None):
    """Run the agent on one day with a fresh conversation, then commit the day."""
    # Fill in the body. Run the agent on this day with a fresh conversation and
    # unattended approvals, then record the day in state.json. A day that ends
    # in an error isn't marked done. Save the state last, so a crash mid-day
    # never marks the day as done. Return the result.
    ...


def run_range(start, end, config, max_total_tokens, client=None):
    """Run day after day until the end day, the total budget, or an error. Returns why it stopped."""
    # Fill in the body. Run days from where the saved state left off through
    # end, and return why the loop stopped: "done", "total_budget" (the total
    # token budget ran out), or "error" (a day stopped with an error).
    ...


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Folder with the days/ feed files")
    parser.add_argument("--start", required=True, help="First day, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Last day, YYYY-MM-DD")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--trace-path", default="traces/trace.jsonl")
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", "gpt-6-luna"))
    parser.add_argument("--max-steps", type=int, default=20, help="Model calls per day")
    # Fill in: add the two token budgets, one for each day's run and one for
    # the whole range.
    args = parser.parse_args()

    workspace = Path(args.workspace)
    prepare_workspace(workspace, Path(args.data_dir))
    # Fill in: build the AgentConfig, with the per-day budget as its token
    # limit, then run the range with the total budget and print why it stopped.
