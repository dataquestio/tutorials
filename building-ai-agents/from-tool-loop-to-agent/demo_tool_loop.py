"""The tool loop from the Function Calling lesson, pointed at a data file.

It has one hand-written tool that answers one kind of question. Run it,
then ask something the tool can't answer, like which borough's noise
complaints take longest to close. The loop has no way to get there.

Usage:
    python demo_tool_loop.py --data-dir <path/to/nyc311>
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()
DATA_DIR = None


def count_requests_by_borough(problem):
    """Count summer 2026 service requests of one problem type, per borough."""
    counts = Counter()
    with open(DATA_DIR / "service_requests.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["problem"].lower() == problem.lower():
                counts[row["borough"]] += 1
    return dict(counts)


TOOL_FUNCTIONS = {"count_requests_by_borough": count_requests_by_borough}

tools = [
    {
        "type": "function",
        "function": {
            "name": "count_requests_by_borough",
            "description": "Count NYC 311 service requests from June to August 2026 for one problem type, per borough.",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem type, e.g. 'Noise - Residential'"}
                },
                "required": ["problem"],
            },
        },
    }
]


def run_agent(user_message, max_iterations=10):
    """Run the tool loop until the model answers without calling a tool."""
    messages = [
        {"role": "system", "content": "You answer questions about NYC 311 service requests using the available tools."},
        {"role": "user", "content": user_message},
    ]

    for i in range(max_iterations):
        response = client.chat.completions.create(
            model="gpt-6-luna",
            messages=messages,
            tools=tools,
            reasoning_effort="none",
        )
        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            return assistant_message.content

        messages.append(assistant_message)
        for tool_call in assistant_message.tool_calls:
            arguments = json.loads(tool_call.function.arguments)
            print(f"  Tool call: {tool_call.function.name}({arguments})")
            result = TOOL_FUNCTIONS[tool_call.function.name](**arguments)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)})

    return "Max iterations reached"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--question", default="How many residential noise complaints did each borough get?")
    args = parser.parse_args()
    DATA_DIR = Path(args.data_dir)

    print("User:", args.question)
    print("\nAssistant:", run_agent(args.question))
