"""The same monitor agent, as a LangGraph graph with checkpoints.

The file-based runner commits progress once per day: if the process dies
mid-day, the whole day runs again. Here, LangGraph saves the graph state to
SQLite after every node. A restart continues from the last saved node, so
only the step that was interrupted is repeated.

The graph has three nodes:

    model     calls the model with the conversation so far
    approval  pauses the graph with interrupt() when a tool call needs a human
    tools     runs the tool calls the policy (or the human) allowed

    START -> model -> approval -> tools -> model -> ... -> END

Each day is its own thread (thread_id "day-YYYY-MM-DD") in the checkpoint
database. A day that waits for approval stays paused in the database until
someone runs the approve command; the other days carry on.

Usage:
    python graph_agent.py run --data-dir <path/to/usgs> --start 2026-06-01 --end 2026-06-07
    python graph_agent.py approve --data-dir <path/to/usgs> --day 2026-06-07 --decision yes
"""

import argparse
import json
import operator
import os
import sqlite3
import time
from pathlib import Path
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from openai import OpenAI

import skills
import tools
from agent import SYSTEM_PROMPT, AgentConfig
from run import prepare_workspace
from runner import build_day_task, load_state, next_day, save_state
from tracing import write_event


# LangGraph reads the graph's state from a class like this one. The ": type"
# after each key is LangGraph's syntax, not optional decoration: it tells
# LangGraph which keys the state has, and Annotated[..., operator.add] tells it
# to add a node's update to the old value instead of replacing it.
class DayState(TypedDict):
    day: str
    # operator.add means each node's returned messages are appended, not replaced.
    messages: Annotated[list, operator.add]
    decisions: dict  # tool_call_id -> "allow" or "deny"
    steps: Annotated[int, operator.add]
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]


def assistant_dict(message):
    """Store the model's message as a plain dict so the checkpointer can save it."""
    data = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        data["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in message.tool_calls
        ]
    return data


def build_graph(config, client, checkpointer):
    """Compile the monitor graph for one configuration."""
    extra = {"tools": tools.tool_schemas()}
    if config.reasoning_effort is not None:
        extra["reasoning_effort"] = config.reasoning_effort

    def model_node(state):
        started = time.monotonic()
        response = client.chat.completions.create(model=config.model, messages=state["messages"], **extra)
        usage = response.usage
        write_event(config.trace_path, f"day-{state['day']}", state["steps"] + 1, "model_call",
                    input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens,
                    duration_ms=int((time.monotonic() - started) * 1000))
        return {
            "messages": [assistant_dict(response.choices[0].message)],
            "steps": 1,
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
        }

    def approval_node(state):
        # interrupt() stops the graph here and saves it. When the graph is
        # resumed, this node runs again from the top and interrupt() returns
        # the human's answer. Nothing before interrupt() may have side
        # effects, which is why tools run in a separate node.
        calls = state["messages"][-1]["tool_calls"]
        decisions = {}
        for call in calls:
            name = call["function"]["name"]
            rule = config.policy.get(name, "ask")
            if rule == "ask":
                args = json.loads(call["function"]["arguments"] or "{}")
                answer = interrupt({"day": state["day"], "tool": name, "args": args})
                decisions[call["id"]] = "allow" if answer else "deny"
            else:
                decisions[call["id"]] = rule
            write_event(config.trace_path, f"day-{state['day']}", state["steps"], "approval",
                        tool=name, result={"decision": decisions[call["id"]]})
        return {"decisions": decisions}

    def tools_node(state):
        results = []
        for call in state["messages"][-1]["tool_calls"]:
            name = call["function"]["name"]
            started = time.monotonic()
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError as e:
                args, result = {}, {"error": f"Arguments were not valid JSON: {e}"}
            else:
                if state["decisions"].get(call["id"]) == "deny":
                    result = {"error": f"Permission denied for {name}. Do not retry."}
                else:
                    result = tools.call_tool(name, args)
            write_event(config.trace_path, f"day-{state['day']}", state["steps"], "tool_result",
                        tool=name, args=args, result=result,
                        duration_ms=int((time.monotonic() - started) * 1000))
            results.append({"role": "tool", "tool_call_id": call["id"], "content": tools.format_result(result)})
        return {"messages": results}

    def after_model(state):
        if not state["messages"][-1].get("tool_calls"):
            return END
        if state["steps"] >= config.max_steps:
            return END
        if state["input_tokens"] + state["output_tokens"] >= config.max_tokens_total:
            return END
        return "approval"

    graph = StateGraph(DayState)
    graph.add_node("model", model_node)
    graph.add_node("approval", approval_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", after_model, ["approval", END])
    graph.add_edge("approval", "tools")
    graph.add_edge("tools", "model")
    return graph.compile(checkpointer=checkpointer)


def thread(day):
    return {"configurable": {"thread_id": f"day-{day}"}}


def run_or_resume_day(graph, day, state_dir, run_state, resume=None):
    """Run one day's thread to the end or to an approval pause. Returns "done" or "paused"."""
    saved = graph.get_state(thread(day))
    if resume is not None:
        graph.invoke(Command(resume=resume), thread(day))
    elif saved.next:
        print(f"{day}: resuming from checkpoint before node {saved.next}")
        graph.invoke(None, thread(day))
    elif not saved.values:
        first = {
            "day": day,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(skill_index=skills.skill_index())},
                {"role": "user", "content": build_day_task(day, run_state, state_dir)},
            ],
            "decisions": {}, "steps": 0, "input_tokens": 0, "output_tokens": 0,
        }
        graph.invoke(first, thread(day))

    saved = graph.get_state(thread(day))
    if saved.interrupts:
        return "paused"
    return "done"


def day_tokens(graph, day):
    values = graph.get_state(thread(day)).values
    return values.get("input_tokens", 0) + values.get("output_tokens", 0)


def make_graph(workspace, args, client=None):
    config = AgentConfig(
        model=args.model, workspace=workspace, trace_path=Path(args.trace_path),
        max_steps=args.max_steps, max_tokens_total=args.max_tokens_per_day,
    )
    tools.WORKSPACE = workspace
    connection = sqlite3.connect(workspace / "state" / "checkpoints.sqlite", check_same_thread=False)
    return build_graph(config, client or OpenAI(), SqliteSaver(connection))


def run_command(args):
    workspace = Path(args.workspace)
    prepare_workspace(workspace, Path(args.data_dir))
    state_dir = workspace / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    graph = make_graph(workspace, args)

    run_state = load_state(state_dir, args.start)
    while run_state["current_day"] <= args.end:
        day = run_state["current_day"]
        outcome = run_or_resume_day(graph, day, state_dir, run_state)
        if outcome == "paused":
            request = graph.get_state(thread(day)).interrupts[0].value
            run_state["pending_approvals"].append({**request, "thread_id": f"day-{day}"})
        else:
            run_state["completed_days"].append(day)
        run_state["tokens_used_total"] += day_tokens(graph, day)
        run_state["current_day"] = next_day(day)
        save_state(state_dir, run_state)
        print(f"{day}: {outcome}, {day_tokens(graph, day)} tokens")


def approve_command(args):
    workspace = Path(args.workspace)
    state_dir = workspace / "state"
    graph = make_graph(workspace, args)
    run_state = load_state(state_dir, args.day)
    before = day_tokens(graph, args.day)
    outcome = run_or_resume_day(graph, args.day, state_dir, run_state, resume=args.decision == "yes")
    run_state["pending_approvals"] = [p for p in run_state["pending_approvals"] if p["day"] != args.day]
    if outcome == "done":
        run_state["completed_days"].append(args.day)
    else:
        # The same model turn asked for another approval, so the day paused again.
        request = graph.get_state(thread(args.day)).interrupts[0].value
        run_state["pending_approvals"].append({**request, "thread_id": f"day-{args.day}"})
    run_state["tokens_used_total"] += day_tokens(graph, args.day) - before
    save_state(state_dir, run_state)
    print(f"{args.day}: {outcome} after decision '{args.decision}'")


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "approve"):
        p = sub.add_parser(name)
        p.add_argument("--data-dir", required=True)
        p.add_argument("--workspace", default="workspace")
        p.add_argument("--trace-path", default="traces/graph_trace.jsonl")
        p.add_argument("--model", default=os.environ.get("AGENT_MODEL", "gpt-6-luna"))
        p.add_argument("--max-steps", type=int, default=20)
        p.add_argument("--max-tokens-per-day", type=int, default=100_000)
    sub.choices["run"].add_argument("--start", required=True)
    sub.choices["run"].add_argument("--end", required=True)
    sub.choices["approve"].add_argument("--day", required=True)
    sub.choices["approve"].add_argument("--decision", choices=["yes", "no"], required=True)
    args = parser.parse_args()

    if args.command == "run":
        run_command(args)
    else:
        approve_command(args)
