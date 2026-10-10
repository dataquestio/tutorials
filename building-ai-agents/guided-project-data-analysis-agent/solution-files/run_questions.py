"""Answer every question in a questions file and write the answers to Markdown.

All questions share one workspace, so notes from earlier questions help
later ones.

Usage:
    python run_questions.py --data-dir <path/to/dohmh> --questions questions.txt --output answers.md
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from agent import AgentConfig, run_agent
from run import prepare_workspace


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--questions", default="questions.txt")
    parser.add_argument("--output", default="answers.md")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--trace-path", default="traces/trace.jsonl")
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", "gpt-6-luna"))
    args = parser.parse_args()

    workspace = Path(args.workspace)
    prepare_workspace(workspace, Path(args.data_dir))
    config = AgentConfig(model=args.model, workspace=workspace, trace_path=Path(args.trace_path))

    questions = [q.strip() for q in Path(args.questions).read_text(encoding="utf-8").splitlines() if q.strip()]
    sections, total_in, total_out = [], 0, 0
    for number, question in enumerate(questions, start=1):
        print(f"[{number}/{len(questions)}] {question}")
        result = run_agent(question, config)
        total_in += result.input_tokens
        total_out += result.output_tokens
        sections.append(
            f"## {number}. {question}\n\n{result.answer or '(no answer)'}\n\n"
            f"_Stopped because: {result.stop_reason}. Steps: {result.steps}. "
            f"Tokens: {result.input_tokens} in, {result.output_tokens} out._\n"
        )
        print(f"    {result.stop_reason}, {result.steps} steps")

    Path(args.output).write_text("# Answers\n\n" + "\n".join(sections), encoding="utf-8")
    print(f"Wrote {args.output}. Tokens: {total_in} in, {total_out} out")
