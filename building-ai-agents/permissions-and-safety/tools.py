"""General-purpose tools for the data analysis agent.

Instead of one hand-written function per question, the agent gets a small
set of general tools: look around the workspace, read files, write files,
and run code. The model decides how to combine them.

Every tool returns a dict. When something goes wrong, the tool returns
{"error": "..."} instead of raising, so the model can read the problem and
try something else.
"""

import os
import subprocess
import sys
from pathlib import Path

from skills import load_skill

RUN_TIMEOUT_SECONDS = 120

# Set by run_agent before the first tool call.
WORKSPACE = None


def resolve_in_workspace(path: str) -> Path:
    """Turn a path from the model into a path inside the workspace.

    The path is normalized (so "a/../.." collapses) but symlinks are not
    followed. That keeps the data/ link usable while refusing anything that
    climbs out of the workspace.
    """
    workspace = os.path.abspath(WORKSPACE)
    full = os.path.abspath(os.path.join(workspace, path))
    if os.path.commonpath([workspace, full]) != workspace:
        raise ValueError(f"Path is outside the workspace: {path}")
    return Path(full)


def list_files(path: str = ".") -> dict:
    """List the files and folders in a workspace directory."""
    try:
        folder = resolve_in_workspace(path)
        entries = []
        for entry in sorted(folder.iterdir()):
            if entry.is_dir():
                entries.append({"name": entry.name + "/", "type": "dir"})
            else:
                entries.append({"name": entry.name, "type": "file", "bytes": entry.stat().st_size})
        return {"path": path, "entries": entries}
    except Exception as e:
        return {"error": str(e)}


def read_file(path: str, start_line: int = 1, max_lines: int = 50) -> dict:
    """Read a slice of lines from a text file.

    Data files can be hundreds of megabytes, so this never reads a whole
    file into the conversation. Use run_python to analyze full files.
    """
    try:
        lines = []
        with open(resolve_in_workspace(path), encoding="utf-8", errors="replace") as f:
            for number, line in enumerate(f, start=1):
                if number < start_line:
                    continue
                if len(lines) == max_lines:
                    return {"path": path, "start_line": start_line, "lines": lines, "next_line": number}
                lines.append(line.rstrip("\n"))
        return {"path": path, "start_line": start_line, "lines": lines, "next_line": None}
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> dict:
    """Create or overwrite a text file in the workspace."""
    try:
        target = resolve_in_workspace(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}


def run_command(command: list[str] | str, shell: bool) -> dict:
    """Run a command in the workspace and capture what it prints."""
    try:
        completed = subprocess.run(
            command,
            shell=shell,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
        return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired:
        return {"error": f"Timed out after {RUN_TIMEOUT_SECONDS} seconds"}
    except Exception as e:
        return {"error": str(e)}


def run_python(code: str) -> dict:
    """Run a Python script in the workspace. Only printed output comes back."""
    # sys.executable is the same Python that runs the agent, so pandas and
    # the other installed libraries are available to the script.
    return run_command([sys.executable, "-c", code], shell=False)


def run_shell(command: str) -> dict:
    """Run a shell command in the workspace."""
    return run_command(command, shell=True)


def tool(fn, description: str, properties: dict, required: list[str]) -> dict:
    """Pair a function with the schema the model sees."""
    return {
        "schema": {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        },
        "fn": fn,
    }


TOOLS = {
    "list_files": tool(
        list_files,
        "List files and folders in a workspace directory. Paths are relative to the workspace.",
        {"path": {"type": "string", "description": "Directory to list, default '.'"}},
        [],
    ),
    "read_file": tool(
        read_file,
        "Read up to max_lines lines of a text file, starting at start_line. Use it to peek at files, not to analyze them.",
        {
            "path": {"type": "string"},
            "start_line": {"type": "integer", "description": "First line to read, starting at 1"},
            "max_lines": {"type": "integer", "description": "Maximum lines to return, default 50"},
        },
        ["path"],
    ),
    "write_file": tool(
        write_file,
        "Create or overwrite a text file in the workspace, such as a report.",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    "run_python": tool(
        run_python,
        "Run a Python script with the workspace as the working directory. pandas, numpy, and matplotlib are installed. "
        "Only what the script prints comes back, so print results and summaries, not whole tables.",
        {"code": {"type": "string", "description": "Complete Python source code"}},
        ["code"],
    ),
    "run_shell": tool(
        run_shell,
        "Run a shell command with the workspace as the working directory, e.g. 'wc -l data/service_requests.csv'.",
        {"command": {"type": "string"}},
        ["command"],
    ),
    "load_skill": tool(
        load_skill,
        "Load the full instructions of a skill listed in the system prompt.",
        {"name": {"type": "string", "description": "Skill name, exactly as listed"}},
        ["name"],
    ),
}


def tool_schemas() -> list[dict]:
    """The tool definitions to send with every model call."""
    return [t["schema"] for t in TOOLS.values()]


def call_tool(name: str, arguments: dict) -> dict:
    """Run a tool by name. Unknown tools and bad arguments come back as errors."""
    if name not in TOOLS:
        return {"error": f"Unknown tool: {name}"}
    try:
        return TOOLS[name]["fn"](**arguments)
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
