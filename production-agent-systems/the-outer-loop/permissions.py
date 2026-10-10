"""Tool permissions.

A policy maps each tool name to "allow", "deny", or "ask". Tools that are
not in the policy are treated as "ask", so a newly added tool can never run
without someone deciding it should.

For "ask", approve() hands the decision to APPROVER. By default that is a
person at the terminal. An unattended system swaps in an approver that
queues the request for a human instead.
"""


def terminal_approver(tool: str, args: dict) -> bool:
    """Ask the person at the terminal."""
    answer = input(f"\nAllow {tool} with {args}? [y/N] ")
    return answer.strip().lower() == "y"


APPROVER = terminal_approver


def approve(tool: str, args: dict) -> bool:
    """Decide an "ask" tool call with the current approver."""
    return APPROVER(tool, args)


def decide(tool: str, args: dict, policy: dict[str, str]) -> str:
    """Return "allow" or "deny" for one tool call under a policy."""
    rule = policy.get(tool, "ask")
    if rule == "allow":
        return "allow"
    if rule == "deny":
        return "deny"
    return "allow" if approve(tool, args) else "deny"
