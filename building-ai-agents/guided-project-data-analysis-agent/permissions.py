"""Permissions: which tools the agent may use on its own.

Each tool gets one of three decisions:

- allow: run it without asking.
- ask: show the call to a person and run it only if they approve.
- deny: never run it.

Tools that aren't in the policy default to ask, so a newly added tool
can't run unchecked by accident.

Permissions limit what the agent can do even if something persuades it to
try, such as instructions hidden inside a data file.
"""

import json
import sys

DEFAULT_POLICY = {
    "list_files": "allow",
    "read_file": "allow",
    "load_skill": "allow",
    "write_file": "allow",
    "run_python": "allow",
    "run_shell": "ask",
}


def terminal_approver(tool, args):
    """Ask the person at the terminal. Anything but 'y' is a no."""
    if not sys.stdin.isatty():
        print(f"[approval needed for {tool}, but no one is at the terminal: denied]")
        return False
    print(f"\nThe agent wants to run {tool} with:\n{json.dumps(args, indent=2)}")
    return input("Allow? [y/N] ").strip().lower() == "y"


# Swap this for another function to approve in a web app, a chat, or a test.
APPROVER = terminal_approver


def approve(tool, args):
    """Ask for approval of one tool call."""
    return APPROVER(tool, args)


def decide(tool, args, policy):
    """Return the outcome for one tool call: allowed, approved, rejected, or denied."""
    rule = policy.get(tool, "ask")
    if rule == "allow":
        return "allowed"
    if rule == "deny":
        return "denied"
    return "approved" if approve(tool, args) else "rejected"
