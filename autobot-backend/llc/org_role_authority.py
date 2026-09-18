# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a Company OS agent may do, by its org role, and how each adapter holds it to that (#16950).

Owner decision 2 (#16946): an autonomous Company OS run's originator is the org agent
itself, bounded by its own org role. ``org_role`` had no permission meaning anywhere,
so the owner approved the table below (#16950): per role, the tools it may never use
and the categories held for a human, in the two vocabularies the platform enforces.

Enforcement differs by adapter, and the owner decided each case:

- ``claude_code`` and its subscription variant take ``--disallowedTools``. The role
  is mapped through the same fixed translation delegation uses. A role that keeps
  ``Bash`` (specialist, worker) cannot have its shell-reachable limits enforced there.
  The owner accepted that gap to keep engineering work running, and
  :func:`describe_role_bound` states exactly which limits are unenforced, so nobody
  believes they are protected.
- An adapter that takes no tool-permission flags cannot enforce any bound, so it
  refuses a bounded role (owner decision for ``copilot_local``, which
  ``copilot_subscription`` subclasses). Every role in the table is bounded.
- The in-process ``autobot_agent`` adapter runs a configured agent that has no
  tool-dispatch seam. The run is attributed to the org agent as originator, and
  there is nothing to enforce against until those agents have a seam.
"""

from __future__ import annotations

from typing import Any, Dict, List

from autobot_shared import tool_catalogue as tc
from llc.exceptions import HeartbeatDispatchSkipped
from security.authority import Authority

_ROTATE = ("rotate_credentials", "rotate_key", "vault_rotate")
_HANDS_OFF = frozenset(
    tc.INFRA_AND_SHELL_TOOLS
    + tc.TERMINAL_TOOLS
    + tc.CODE_EXEC_TOOLS
    + tc.FILE_DELETE_TOOLS
    + tc.GIT_PUSH_TOOLS
    + tc.GIT_RESET_TOOLS
)
_HANDS_ON_FORBIDDEN = frozenset(tc.DEPLOY_TOOLS + tc.CONTAINER_ORCH_TOOLS)
_HANDS_ON_GATES = frozenset(
    {
        "destructive operations",
        "pushing commits",
        "discarding local changes",
        "sending externally",
        "publishing",
        "rotating credentials",
    }
)

#: The owner-approved table (#16950), as proposed on the issue.
ORG_ROLE_AUTHORITY: Dict[str, Authority] = {
    "manager": Authority(
        forbidden_tools=_HANDS_OFF,
        approval_gates=frozenset({"writing files", "sending externally", "publishing", "rotating credentials"}),
    ),
    "coordinator": Authority(
        forbidden_tools=_HANDS_OFF | frozenset(tc.FILE_WRITE_TOOLS),
        approval_gates=frozenset({"sending externally", "publishing", "rotating credentials"}),
    ),
    "specialist": Authority(forbidden_tools=_HANDS_ON_FORBIDDEN, approval_gates=_HANDS_ON_GATES),
    "worker": Authority(
        forbidden_tools=_HANDS_ON_FORBIDDEN | frozenset(_ROTATE),
        approval_gates=_HANDS_ON_GATES | {"executing code"},
    ),
}

#: Adapters that enforce a bound through claude_code's ``--disallowedTools``.
CLAUDE_CODE_ADAPTERS = frozenset({"claude_code", "claude_code_subscription"})
#: Adapters that take no tool-permission flags, so they refuse a bounded role (owner
#: decision for copilot_local; copilot_subscription subclasses it; codex_subscription
#: takes none either).
NO_TOOL_FLAG_ADAPTERS = frozenset({"copilot_local", "copilot_subscription", "codex_subscription"})
#: The in-process adapter: attributed, with no seam to enforce against.
IN_PROCESS_ADAPTER = "autobot_agent"
#: Every adapter this module has a decision for. A *registered* adapter outside it fails
#: test_org_role_authority, so a new one cannot run bounded roles unbounded unnoticed.
#: An unregistered type falls through to the scheduler's own "no adapter" skip.
CLASSIFIED_ADAPTERS = CLAUDE_CODE_ADAPTERS | NO_TOOL_FLAG_ADAPTERS | {IN_PROCESS_ADAPTER}


def org_role_authority(role: str | None) -> Authority:
    """The approved bound for *role*. An unknown or missing role is refused, never run unbounded."""
    if role not in ORG_ROLE_AUTHORITY:
        raise ValueError(f"org role {role!r} has no approved permission bound (#16950)")
    return ORG_ROLE_AUTHORITY[role]


def _keeps_shell(authority: Authority) -> bool:
    return not authority.forbidden_tools & frozenset(tc.SHELL_EXEC_TOOLS)


def claude_code_bound(authority: Authority) -> tuple[List[str], List[str]]:
    """``(--disallowedTools, tokens this adapter cannot enforce)`` for a role.

    claude_code cannot ask for approval, so a held category is refused, never held.
    For a role that keeps ``Bash``, anything reachable only through ``Bash`` cannot be
    refused without taking ``Bash`` away, which the owner declined for org roles. Those
    tokens are reported as unenforced instead of silently dropped.
    """
    # Deferred: the scheduler imports this module, and chat_workflow's package init is heavy.
    from chat_workflow.delegation import _claude_tool_for, claude_tools_refusing, forbidden_to_claude_tools
    from chat_workflow.run_authority import gated_tools

    held = authority.forbidden_tools | gated_tools(authority.approval_gates)
    if not _keeps_shell(authority):
        return claude_tools_refusing(frozenset(), held), []
    disallowed = [tool for tool in forbidden_to_claude_tools(held) if tool != "Bash"]
    unenforced = sorted(token for token in held if _claude_tool_for(token) in (None, "Bash"))
    return disallowed, unenforced


def describe_role_bound(role: str | None, adapter_type: str | None) -> Dict[str, Any]:
    """The bound an agent runs under, and what its adapter cannot hold it to (#16950).

    Derived, never stored: the agent's config view shows it so nobody believes a limit
    is enforced when its adapter cannot enforce it.
    """
    adapter = adapter_type or IN_PROCESS_ADAPTER
    try:
        authority = org_role_authority(role)
    except ValueError as exc:
        return {"role": role, "adapter": adapter, "runs": False, "reason": str(exc)}
    view: Dict[str, Any] = {
        "role": role,
        "adapter": adapter,
        "forbidden_tools": sorted(authority.forbidden_tools),
        "approval_gates": sorted(authority.approval_gates),
    }
    if adapter in CLAUDE_CODE_ADAPTERS:
        _, unenforced = claude_code_bound(authority)
        return {**view, "runs": True, "unenforced_on_adapter": unenforced}
    if adapter == IN_PROCESS_ADAPTER:
        return {**view, "runs": True, "unenforced_on_adapter": ["all: the configured agent has no tool seam"]}
    if adapter in NO_TOOL_FLAG_ADAPTERS:
        return {
            **view,
            "runs": False,
            "reason": f"{adapter} takes no tool-permission flags, so it refuses bounded roles",
        }
    return {**view, "runs": True, "unenforced_on_adapter": [f"unknown: {adapter} is not a registered adapter"]}


def apply_org_role_bound(agent: Dict[str, Any]) -> Dict[str, Any]:
    """The dispatch-ready agent for a Company OS run, bounded by its org role, or a refusal.

    Called at the one point every heartbeat and comment-wake run passes. Refusal is a
    ``HeartbeatDispatchSkipped``: recorded with its reason, never a phantom success.
    """
    view = describe_role_bound(agent.get("org_role"), agent.get("adapter_type"))
    if not view["runs"]:
        raise HeartbeatDispatchSkipped(agent["agent_id"], f"{view['reason']} (#16950)")
    if view["adapter"] not in CLAUDE_CODE_ADAPTERS:
        return agent
    disallowed, unenforced = claude_code_bound(org_role_authority(agent["org_role"]))
    config = dict(agent.get("adapter_config") or {})
    config["disallowed_tools"] = sorted({*(config.get("disallowed_tools") or []), *disallowed})
    config["unenforced_role_bound"] = unenforced
    return {**agent, "adapter_config": config}
