"""The outer loop: run the monitor once per simulated day.

Each day gets a brand-new agent conversation. What carries over between
days lives in files under state/:

    state.json     where the loop is: current day, completed days, tokens used,
                   and approvals waiting for a human
    progress.md    notes the agent leaves for its next run
    catalog.jsonl  the running event catalog (written by apply_day_to_catalog)

state.json is only updated after a day finishes, and always by writing a
new file and swapping it in. If the process is killed mid-day, or a model
call fails and raises, the next start repeats that day; nothing that was
already committed is lost.

Usage:
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


def load_state(state_dir, start_day):
    """Read state.json, or start fresh at start_day.

    The state holds current_day, completed_days, tokens_used_total, and
    pending_approvals.
    """
    # TODO: Return the saved state, or a fresh one if there's no state.json
    ...


def save_state(state_dir, state):
    """Write state.json so that a crash never leaves a half-written file.

    A crash partway through leaves either the old file or the new one.
    """
    # TODO: Write a temporary file, then swap it in for state.json
    ...


def recent_progress(state_dir):
    """The most recent lines of progress.md as one string.

    Returns at most RECENT_PROGRESS_LINES lines, or "(no earlier runs)" if
    there's no progress.md yet.
    """
    # TODO: Return the last lines of progress.md, or "(no earlier runs)"
    ...


def build_day_task(day, state, state_dir):
    """The task for one daily run. Everything the agent needs from earlier days is in here or in state/.

    The task carries the day to process, a short summary of the state, and
    the most recent progress notes.
    """
    # TODO: Return the day, a state summary, and recent progress as one string
    ...


def queue_for_human(state, day):
    """An approver for unattended runs: record the request and say no for now.

    Returns approver(tool, args), which adds each request to
    state["pending_approvals"] and returns False.
    """
    # TODO: Return an approver that records each request and refuses it
    ...


def run_day(day, state_dir, config, client=None):
    """Run the agent on one day with a fresh conversation, then commit the day.

    state.json is saved last, so a crash mid-day never marks the day as done.
    Returns the agent's result.
    """
    # TODO: Load the state and point permissions.APPROVER at this day's approver
    # TODO: Run the agent on the day's task
    # TODO: Add the runner's line to progress.md
    # TODO: Record the day and its tokens, save the state, and return the result
    ...


def run_range(start, end, config, max_total_tokens, client=None):
    """Run day after day until the end day or the total budget. Returns why it stopped.

    The loop starts from where the saved state left off and returns "done" or
    "total_budget".
    """
    # TODO: Load the state and print where it's resuming, if days are done
    # TODO: Loop through the days, checking the total budget before each one
    # TODO: Return "done" when the range is finished
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
    # TODO: Add --max-tokens-per-day and --max-total-tokens
    args = parser.parse_args()

    workspace = Path(args.workspace)
    prepare_workspace(workspace, Path(args.data_dir))
    # TODO: Build the AgentConfig, run the range, and print why it stopped
