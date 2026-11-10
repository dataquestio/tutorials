"""Ask the data analysis agent a question from the command line.

Usage:
    python run.py --data-dir <path/to/nyc311> --question "Which borough had the most noise complaints in July?"

This is provided for you; you do not edit it. Later in the lesson it is replaced
with a version that prints the full AgentResult (answer, stop_reason, steps, token
counts, and any files the agent wrote).
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from agent import AgentConfig, run_agent


def prepare_workspace(workspace, data_dir):
    """Create the workspace and link the data into it as data/."""
    workspace.mkdir(parents=True, exist_ok=True)
    link = workspace / "data"
    if not link.exists():
        link.symlink_to(data_dir.resolve(), target_is_directory=True)


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Folder with the data snapshot")
    parser.add_argument("--question", required=True)
    parser.add_argument("--workspace", default="workspace", help="Folder the agent works in")
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", "gpt-6-luna"))
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--trace-path", default="traces/trace.jsonl")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    prepare_workspace(workspace, Path(args.data_dir))

    config = AgentConfig(
        model=args.model,
        workspace=workspace,
        trace_path=Path(args.trace_path),
        max_steps=args.max_steps,
    )
    answer = run_agent(args.question, config)
    print(answer)
