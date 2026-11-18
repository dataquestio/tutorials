"""Quick checks for this lesson. Each screen tells you which one to run.

Run a check by name:
    python demo_checks.py setup

Run it with no name to see every check and what it does.
"""

import argparse
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv


STATE_DIR = Path("workspace/state")
TEST_STATE_DIR = "test_state"
TEST_TASK_DIR = "test_day_task"
TEST_DAY_DIR = "test_one_day"
TEST_EXITS_DIR = "test_exits"
MONITOR_STATE_DIR = Path("monitor/state")

# The exact line run_day writes, so lines in another format can be spotted.
RUNNER_LINE = re.compile(r"^\[runner\] \d{4}-\d{2}-\d{2}: stop=\w+ steps=\d+ tokens=\d+$")

# A progress log from six earlier days, using the feed's real numbers.
SAMPLE_PROGRESS = """2026-06-01: 385 rows.
Catalog: 385 new, 0 revised, 0 deleted.
Flagged large_event for us7000spxm (M6.2, reviewed).
2026-06-02: 341 rows.
Catalog: 313 new, 27 revised, 1 deleted.
No flags.
2026-06-03: 382 rows.
Catalog: 352 new, 25 revised, 5 deleted.
No flags.
2026-06-04: 486 rows.
Catalog: 434 new, 46 revised, 6 deleted.
No flags.
2026-06-05: 446 rows.
Catalog: 413 new, 23 revised, 10 deleted.
No flags.
2026-06-06: 392 rows.
Catalog: 360 new, 29 revised, 3 deleted.
No flags.
"""

# Each check imports the lesson files it needs inside the check, so a mistake
# you're still fixing in runner.py doesn't stop the other checks from running.


def check_setup():
    """Run the provided agent once on a tiny task to confirm your key works."""
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        print("No API key found. Create a .env file in the lesson folder with this line:")
        print("    OPENAI_API_KEY=your-key-here")
        return

    from agent import AgentConfig, run_agent

    config = AgentConfig(
        model=os.environ.get("AGENT_MODEL", "gpt-6-luna"),
        workspace=Path("workspace"),
        trace_path=Path("traces/setup.jsonl"),
    )
    result = run_agent("Reply with the single word: ready.", config)
    print(result.stop_reason, result.answer)


def check_confirm_state():
    """Summarize what the last run left in workspace/state/."""
    if not STATE_DIR.exists():
        print("No workspace/state/ folder yet. Run run.py first.")
        return

    catalog_path = STATE_DIR / "catalog.jsonl"
    if catalog_path.exists():
        catalog_lines = catalog_path.read_text(encoding="utf-8").splitlines()
        print(f"Catalog: {len(catalog_lines)} events")
    else:
        print("Catalog: no catalog.jsonl yet")

    flags_path = STATE_DIR / "flags.jsonl"
    if flags_path.exists():
        for line in flags_path.read_text(encoding="utf-8").splitlines():
            flag = json.loads(line)
            print(f"Flag ({flag['kind']}): {flag['details']}")
    else:
        print("Flags: none")

    progress_path = STATE_DIR / "progress.md"
    print("Progress notes:")
    if progress_path.exists():
        print(progress_path.read_text(encoding="utf-8"))
    else:
        print("(none yet)")


def check_save_load():
    """Test load_state and save_state in a test_state folder, cleared on every run."""
    from runner import load_state, save_state

    shutil.rmtree(TEST_STATE_DIR, ignore_errors=True)

    state = load_state(TEST_STATE_DIR, "2026-06-01")
    if state is None:
        print("load_state returned None. Fill in load_state in runner.py, and make sure each branch returns a dictionary.")
        return
    print("Fresh state:", state)

    state["completed_days"].append("2026-06-01")
    state["current_day"] = "2026-06-02"
    save_state(TEST_STATE_DIR, state)

    if not Path(TEST_STATE_DIR, "state.json").exists():
        print("save_state didn't write test_state/state.json. Fill in save_state in runner.py.")
        return
    print("Saved state:", load_state(TEST_STATE_DIR, "2026-06-01"))


def check_day_task():
    """Show the task build_day_task writes for June 7, from a sample state."""
    from runner import build_day_task, recent_progress

    shutil.rmtree(TEST_TASK_DIR, ignore_errors=True)
    Path(TEST_TASK_DIR).mkdir()
    Path(TEST_TASK_DIR, "progress.md").write_text(SAMPLE_PROGRESS, encoding="utf-8")
    state = {
        "current_day": "2026-06-07",
        "completed_days": [f"2026-06-0{n}" for n in range(1, 7)],
        "tokens_used_total": 0,
        "pending_approvals": [],
    }

    recent = recent_progress(TEST_TASK_DIR)
    if recent is None:
        print("recent_progress returned None. Fill in recent_progress in runner.py first.")
        return
    task = build_day_task("2026-06-07", state, TEST_TASK_DIR)
    if task is None:
        print("build_day_task returned None. Fill in build_day_task in runner.py first.")
        return

    print(task)
    total = len(SAMPLE_PROGRESS.splitlines())
    print(f"\n(The sample progress.md has {total} lines. The task included the last {len(recent.splitlines())}.)")


def check_approvals():
    """Send a sample alert request through the tool policy with your queue_for_human approver."""
    import permissions
    from agent import DEFAULT_POLICY
    from runner import queue_for_human

    state = {"current_day": "2026-06-07", "completed_days": [], "tokens_used_total": 0, "pending_approvals": []}
    approver = queue_for_human(state, "2026-06-07")
    if approver is None:
        print("queue_for_human returned None. It should return the inner approver function.")
        return

    permissions.APPROVER = approver
    args = {
        "message": "M7.58 automatic (may be revised): us7000srb1, 25 km SW of Kablalan, Philippines, 2026-06-07 23:37:41 UTC.",
        "event_ids": ["us7000srb1"],
    }
    decision = permissions.decide("send_alert", args, DEFAULT_POLICY)

    print("Policy decision for send_alert:", decision)
    if not state["pending_approvals"]:
        print("pending_approvals is still empty. The approver should add the request before it returns False.")
        return
    print("pending_approvals:")
    print(json.dumps(state["pending_approvals"], indent=2))


def check_one_day():
    """Run your run_day on June 7 in its own test workspace (live model calls)."""
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        print("No API key found. Create a .env file in the lesson folder with this line:")
        print("    OPENAI_API_KEY=your-key-here")
        return
    if not Path("data/usgs/days").exists():
        print("Couldn't find the feed in data/usgs/days. It should be in the lesson folder.")
        return

    from agent import AgentConfig
    from run import prepare_workspace
    from runner import run_day

    workspace = Path(TEST_DAY_DIR)
    shutil.rmtree(workspace, ignore_errors=True)
    prepare_workspace(workspace, Path("data/usgs"))
    config = AgentConfig(
        model=os.environ.get("AGENT_MODEL", "gpt-6-luna"),
        workspace=workspace,
        trace_path=workspace / "trace.jsonl",
    )

    result = run_day("2026-06-07", workspace / "state", config)
    if result is None:
        print("run_day returned None. It should return the result from run_agent.")
        return
    print(f"Stopped because: {result.stop_reason}")
    print(f"Steps: {result.steps}, tokens: {result.input_tokens + result.output_tokens}")

    state_path = workspace / "state" / "state.json"
    if not state_path.exists():
        print("run_day didn't save state.json. Save the state as its last step.")
        return
    state = json.loads(state_path.read_text(encoding="utf-8"))
    print("\nstate.json:")
    print(f"  current_day: {state['current_day']}")
    print(f"  completed_days: {state['completed_days']}")
    print(f"  tokens_used_total: {state['tokens_used_total']}")
    print(f"  pending_approvals: {[(p['tool'], p['args'].get('event_ids')) for p in state['pending_approvals']]}")

    progress_path = workspace / "state" / "progress.md"
    if progress_path.exists():
        print("\nLast line of progress.md:")
        print("  " + progress_path.read_text(encoding="utf-8").splitlines()[-1])


class ScriptedModel:
    """Stands in for the model. It answers every request right away with the same
    reply and token counts, or fails on purpose, so runner logic can be checked
    in seconds with no API calls."""

    def __init__(self, fail=False):
        self.fail = fail
        self.chat = self
        self.completions = self

    def create(self, **request):
        from openai.types import CompletionUsage
        from openai.types.chat import ChatCompletion, ChatCompletionMessage
        from openai.types.chat.chat_completion import Choice

        if self.fail:
            raise ConnectionError("The model API couldn't be reached.")
        return ChatCompletion(
            id="scripted", object="chat.completion", created=0, model="scripted",
            choices=[Choice(index=0, finish_reason="stop",
                            message=ChatCompletionMessage(role="assistant", content="Day processed."))],
            usage=CompletionUsage(prompt_tokens=1000, completion_tokens=50, total_tokens=1050),
        )


def check_exits():
    """Run run_range with a scripted model to see each way it stops (no model calls)."""
    from agent import AgentConfig
    from runner import run_range

    def fresh_config(name):
        shutil.rmtree(name, ignore_errors=True)
        Path(name).mkdir()
        return AgentConfig(model="scripted", workspace=Path(name), trace_path=Path(name) / "trace.jsonl")

    print("1. June 1 to 3, total budget 100,000 tokens:")
    config = fresh_config(TEST_EXITS_DIR)
    stopped = run_range("2026-06-01", "2026-06-03", config, 100_000, ScriptedModel())
    if stopped is None:
        print("run_range returned None. It should return why it stopped: done, total_budget, or error.")
        return
    print("Stopped:", stopped)

    print("\n2. The same folder again, now through June 5:")
    print("Stopped:", run_range("2026-06-01", "2026-06-05", config, 100_000, ScriptedModel()))

    print("\n3. A fresh start, June 1 to 5, total budget 2,000 tokens:")
    config = fresh_config(TEST_EXITS_DIR)
    print("Stopped:", run_range("2026-06-01", "2026-06-05", config, 2_000, ScriptedModel()))

    print("\n4. A fresh start, June 1 to 3, and the model can't be reached:")
    config = fresh_config(TEST_EXITS_DIR)
    print("Stopped:", run_range("2026-06-01", "2026-06-03", config, 100_000, ScriptedModel(fail=True)))
    state = json.loads(Path(TEST_EXITS_DIR, "state", "state.json").read_text(encoding="utf-8"))
    print(f"state.json: current_day {state['current_day']}, completed_days {state['completed_days']}")

    print("\n5. The same folder again, now that the model is back:")
    print("Stopped:", run_range("2026-06-01", "2026-06-03", config, 100_000, ScriptedModel()))


def check_repeated_day():
    """Look through monitor/state/ for signs that a day ran twice (no model calls)."""
    if not MONITOR_STATE_DIR.exists():
        print("No monitor/state/ folder yet. Run the monitor with --workspace monitor first.")
        return
    print("Checking monitor/state/ for signs of a repeated day.")

    flags_path = MONITOR_STATE_DIR / "flags.jsonl"
    flags = []
    if flags_path.exists():
        flags = [json.loads(line) for line in flags_path.read_text(encoding="utf-8").splitlines()]
    # The same day, kind, and events counts as the same flag; the wording can differ.
    counts = Counter((flag["day"], flag["kind"], tuple(flag.get("event_ids") or [])) for flag in flags)
    print("\nFlags written more than once (same day, kind, and events):")
    repeated = [(day, kind, ids, n) for (day, kind, ids), n in counts.items() if n > 1]
    for day, kind, ids, n in repeated:
        events = f" {', '.join(ids)}" if ids else ""
        print(f"  {day} {kind}{events} ({n} times)")
    if not repeated:
        print("  none")

    progress_path = MONITOR_STATE_DIR / "progress.md"
    lines = []
    if progress_path.exists():
        lines = progress_path.read_text(encoding="utf-8").splitlines()

    print('\nProgress notes that say "0 new":')
    zero_new = [line for line in lines if re.search(r"\b0 new\b", line)]
    for line in zero_new:
        print(f"  {line[:100]}")
    if not zero_new:
        print("  none")

    print("\n[runner] lines the runner didn't write:")
    imitations = [line for line in lines if line.startswith("[runner]") and not RUNNER_LINE.match(line)]
    for line in imitations:
        print(f"  {line[:100]}")
    if not imitations:
        print("  none")


CHECKS = {
    "setup": (check_setup, "Screen 1: run the provided agent once (one model call, about 700 tokens)"),
    "confirm_state": (check_confirm_state, "Screen 2: summarize what a run left in workspace/state/"),
    "save_load": (check_save_load, "Screen 3: test load_state and save_state (no model calls)"),
    "day_task": (check_day_task, "Screen 4: show the task the runner would send for June 7 (no model calls)"),
    "approvals": (check_approvals, "Screen 5: run a sample alert through the policy with your approver (no model calls)"),
    "one_day": (check_one_day, "Screen 6: run your run_day on June 7 (live model calls, about 10,000 to 16,000 tokens)"),
    "exits": (check_exits, "Screen 7: run run_range with a scripted model to see each exit (no model calls)"),
    "repeated_day": (check_repeated_day, "Screen 10: look for signs of a repeated day in monitor/state/ (no model calls)"),
}


if __name__ == "__main__":
    # Work from the lesson folder, wherever the script is run from, so the
    # relative paths above always point at the right files.
    os.chdir(Path(__file__).resolve().parent)

    menu = "\n".join(f"  {name:<14} {description}" for name, (_, description) in CHECKS.items())
    parser = argparse.ArgumentParser(
        description="Quick checks for this lesson.",
        epilog="Checks:\n" + menu,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("check", nargs="?", choices=CHECKS, help="the check to run")
    args = parser.parse_args()

    if args.check is None:
        print("Pick a check to run, for example: python demo_checks.py setup\n")
        print("Checks:\n" + menu)
    else:
        CHECKS[args.check][0]()
