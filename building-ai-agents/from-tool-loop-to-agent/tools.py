"""General-purpose tools for the data analysis agent.

Instead of one hand-written function per question, the agent gets a small
set of general tools: look around the workspace, read files, write files,
and run code. The model decides how to combine them.

Every tool returns a dict. When something goes wrong, the tool returns
{"error": "..."} instead of raising, so the model can read the problem and
try something else.

The functions above the "YOUR TOOLS" divider are provided. Below it, each tool
already has its signature in place and you fill in the body as the lesson walks
through it:
  - read_file, to read a slice of a file
  - run_python and run_shell, to run the model's code
  - call_tool, to run the tool the model asked for
"""

import os
import subprocess
import sys
from pathlib import Path

RUN_TIMEOUT_SECONDS = 120

# Set by run_agent before the first tool call.
WORKSPACE = None


# ===========================================================================
# PROVIDED HELPERS AND TOOLS
# Read these; the tools you write follow the same pattern (take a path or
# some input, do the work, return a dict or {"error": ...}).
# ===========================================================================


def resolve_in_workspace(path):
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


def list_files(path="."):
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


def write_file(path, content):
    """Create or overwrite a text file in the workspace."""
    try:
        target = resolve_in_workspace(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}


def run_command(command, shell):
    """Run a command in the workspace and capture what it prints.

    You use this to build run_python and run_shell.
    """
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


# ===========================================================================
# YOUR TOOLS
# ===========================================================================


def read_file(path, start_line=1, max_lines=50):
    # Fill in the body. Resolve the path inside the workspace, read a slice of at
    # most max_lines lines starting at start_line, and return a dictionary with the
    # path, start_line, lines, and next_line (or {"error": ...}).
    ...


def run_python(code):
    # Fill in the body. Run code as a Python script through run_command (shell=False)
    # and return its result.
    ...


def run_shell(command):
    # Fill in the body. Run command through run_command (shell=True) and return its
    # result.
    ...
# ===========================================================================
# THE REGISTRY (provided) + call_tool (you write)
# The registry is active: it refers to the tool functions above, which now all
# exist as stubs, so it resolves when this file is imported.
# ===========================================================================


def tool(fn, description, properties, required):
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
}


def tool_schemas():
    """The tool definitions to send with every model call."""
    return [t["schema"] for t in TOOLS.values()]


def call_tool(name, arguments):
    # Fill in the body. Look up the tool by name in TOOLS and call its function with
    # the arguments; return {"error": ...} for an unknown tool or for arguments the
    # function does not accept.
    ...