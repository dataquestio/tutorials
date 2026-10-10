"""The outer loop: run the monitor once per simulated day.

Each day gets a brand-new agent conversation. What carries over between
days lives in files under state/:

    state.json     where the loop is: current day, completed days, tokens used,
                   and approvals waiting for a human
    progress.md    notes the agent leaves for its next run
    catalog.jsonl  the running event catalog (written by apply_day_to_catalog)

state.json is only updated after a day finishes, and always by writing a
new file and swapping it in. If the process is killed mid-day, the next
start repeats that day; nothing that was already committed is lost.

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
from agent import AgentConfig, AgentResult, run_agent
from run import prepare_workspace

RECENT_PROGRESS_LINES = 15


def load_state(state_dir: Path, start_day: str) -> dict:
    """Read state.json, or start fresh at start_day."""
    path = Path(state_dir) / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"current_day": start_day, "completed_days": [], "tokens_used_total": 0, "pending_approvals": []}


def save_state(state_dir: Path, state: dict) -> None:
    """Write state.json so that a crash never leaves a half-written file."""
    path = Path(state_dir) / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def recent_progress(state_dir: Path) -> str:
    path = Path(state_dir) / "progress.md"
    if not path.exists():
        return "(no earlier runs)"
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-RECENT_PROGRESS_LINES:])


def build_day_task(day: str, state: dict, state_dir: Path) -> str:
    """The task for one daily run. Everything the agent needs from earlier days is in here or in state/."""
    return (
        f"Process the feed for {day}.\n\n"
        f"Days already processed: {len(state['completed_days'])}. "
        f"Approvals waiting for a human: {len(state['pending_approvals'])}.\n\n"
        f"Most recent lines of state/progress.md:\n{recent_progress(state_dir)}"
    )


def queue_for_human(state: dict, day: str):
    """An approver for unattended runs: record the request and say no for now."""
    def approver(tool: str, args: dict) -> bool:
        state["pending_approvals"].append({"day": day, "tool": tool, "args": args})
        return False
    return approver


def run_day(day: str, state_dir: Path, config: AgentConfig, client=None) -> AgentResult:
    """Run the agent on one day with a fresh conversation, then commit the day."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(state_dir, day)
    permissions.APPROVER = queue_for_human(state, day)

    result = run_agent(build_day_task(day, state, state_dir), config, client)

    with open(state_dir / "progress.md", "a", encoding="utf-8") as f:
        f.write(f"[runner] {day}: stop={result.stop_reason} steps={result.steps} "
                f"tokens={result.input_tokens + result.output_tokens}\n")
    state["completed_days"].append(day)
    state["current_day"] = next_day(day)
    state["tokens_used_total"] += result.input_tokens + result.output_tokens
    save_state(state_dir, state)
    return result


def run_range(start: str, end: str, config: AgentConfig, max_total_tokens: int, client=None) -> str:
    """Run day after day until the end day, the total budget, or an error. Returns why it stopped."""
    state_dir = Path(config.workspace) / "state"
    state = load_state(state_dir, start)
    if state["completed_days"]:
        print(f"Resuming at {state['current_day']} ({len(state['completed_days'])} days already done)")

    while state["current_day"] <= end:
        if state["tokens_used_total"] >= max_total_tokens:
            return "total_budget"
        day = state["current_day"]
        result = run_day(day, state_dir, config, client)
        print(f"{day}: {result.stop_reason}, {result.steps} steps, "
              f"{result.input_tokens + result.output_tokens} tokens")
        if result.stop_reason == "error":
            return "error"
        state = load_state(state_dir, start)
    return "done"


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
    parser.add_argument("--max-tokens-per-day", type=int, default=100_000)
    parser.add_argument("--max-total-tokens", type=int, default=1_000_000)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    prepare_workspace(workspace, Path(args.data_dir))
    config = AgentConfig(
        model=args.model,
        workspace=workspace,
        trace_path=Path(args.trace_path),
        max_steps=args.max_steps,
        max_tokens_total=args.max_tokens_per_day,
    )
    print("Stopped:", run_range(args.start, args.end, config, args.max_total_tokens))
