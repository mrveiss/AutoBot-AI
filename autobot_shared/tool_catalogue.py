# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical catalogue of risky tool groups (GH#11206).

Governance enumerates dangerous tools in several places — the non-executor
``forbidden_work`` default, the agent-loop sensitive-tool approval set, and the
chat seam's work-item approval categories. They overlapped heavily and drifted
independently (a tool added to one but not the others is governed inconsistently).

This module is the single source: small named atoms below, and the composed
catalogues each consumer derives from them. Adding a tool to an atom propagates
to every catalogue that includes it. The composed sets reproduce the pre-existing
catalogues exactly (asserted by parity tests) — this is a consolidation, not a
behaviour change.
"""

from enum import Enum
from typing import Iterable, Optional


def match_tool_name(tool_name: str, patterns: Iterable[str], *, word_boundary: bool = False) -> Optional[str]:
    """Return the pattern in *patterns* that matches *tool_name*, else ``None`` (GH#11206).

    The single canonical tool-name matcher for every governance plane (forbidden_work,
    sensitive-tool approval, work-item approval categories). Case-insensitive; an exact
    match anywhere wins, otherwise the first prefix match is returned. *word_boundary*
    requires a ``<pattern>_`` boundary (``deploy`` matches ``deploy_x`` but not
    ``deployment``); the default plain prefix keeps the broader, fail-safe denylist
    behaviour (``deploy`` also matches ``deployment``).
    """
    name = tool_name.lower()
    pats = tuple(patterns)
    if name in pats:
        return name
    suffix = "_" if word_boundary else ""
    for pattern in pats:
        if name.startswith(pattern + suffix):
            return pattern
    return None


# --- atoms -----------------------------------------------------------------

SHELL_EXEC_TOOLS = ("bash", "shell", "execute_command", "run_command")
SYSTEM_EXEC_TOOLS = ("system_exec",)
TERMINAL_TOOLS = ("terminal",)
CONTAINER_ORCH_TOOLS = ("docker", "kubectl", "terraform")
DEPLOY_TOOLS = ("deploy", "ansible", "helm")
FILE_WRITE_TOOLS = ("write_file", "edit_file", "move_file", "copy_file", "create_directory")
FILE_DELETE_TOOLS = ("delete_file", "remove_directory")
GIT_PUSH_TOOLS = ("git_push", "git_commit", "git_merge", "git_rebase", "git_force_push")
GIT_RESET_TOOLS = ("git_reset",)
HTTP_WRITE_TOOLS = ("http_post", "http_put", "http_patch", "http_delete", "send_request")
CODE_EXEC_TOOLS = ("code_interpreter",)

# --- composed catalogues (each reproduces its former literal exactly) ------

#: Infra/shell tools a non-executor agent may not invoke (forbidden_work default).
INFRA_AND_SHELL_TOOLS = SHELL_EXEC_TOOLS + SYSTEM_EXEC_TOOLS + DEPLOY_TOOLS + CONTAINER_ORCH_TOOLS

#: Tools that require explicit user approval before execution (agent-loop gate).
SENSITIVE_TOOLS = frozenset(
    FILE_WRITE_TOOLS
    + FILE_DELETE_TOOLS
    + SHELL_EXEC_TOOLS
    + TERMINAL_TOOLS
    + SYSTEM_EXEC_TOOLS
    + DEPLOY_TOOLS
    + CONTAINER_ORCH_TOOLS
    + GIT_PUSH_TOOLS
    + GIT_RESET_TOOLS
    + HTTP_WRITE_TOOLS
    + CODE_EXEC_TOOLS
)

#: Work-item approval categories → the tools that constitute each action (seam gate).
#: Note: "destructive operations" intentionally excludes SYSTEM_EXEC/DEPLOY, and
#: "pushing commits" excludes git_reset — preserved from the prior literals; making
#: those atoms explicit surfaces the boundary rather than hiding it in a flat list.
APPROVAL_CATEGORY_TOOLS = {
    "pushing commits": GIT_PUSH_TOOLS,
    "publishing": ("deploy", "publish", "content_reach"),
    "destructive operations": FILE_DELETE_TOOLS + SHELL_EXEC_TOOLS + CONTAINER_ORCH_TOOLS,
    "rotating credentials": ("rotate_credentials", "rotate_key", "vault_rotate"),
    # #14067: HTTP_WRITE_TOOLS was in SENSITIVE_TOOLS (the agent-loop plane) but
    # reachable through no category at all, so a work item could not gate the one
    # action class that leaves the machine. The Gateway's own outbound path is
    # governed separately at its seam (services/gateway/egress_governor.py) —
    # a gateway send is not a tool call, so it cannot be covered by a tool name.
    "sending externally": HTTP_WRITE_TOOLS,
    # #14903: eleven SENSITIVE_TOOLS members were reachable through no category
    # at all -- every file write among them. A work item could declare
    # "destructive operations", be told the gate was in force, and still have
    # write_file run unapproved, because that category covers FILE_DELETE_TOOLS
    # and not FILE_WRITE_TOOLS. Two of the eleven (SYSTEM_EXEC/DEPLOY out of
    # "destructive operations", git_reset out of "pushing commits") were
    # documented exclusions; the file-write gap was documented nowhere, which is
    # the difference between an asserted decision and drift.
    #
    # These are NEW categories rather than widenings of the four above, and that
    # is deliberate: test_approval_categories_parity treats the extraction
    # snapshot as "a floor, not a ceiling" -- every pre-existing category must
    # still carry exactly its original tools, so a consolidation edit cannot
    # quietly change what an already-declared work item gates. #14067 set the
    # same precedent when it added "sending externally". Widening "destructive
    # operations" to reach write_file would silently change the meaning of every
    # work item that already declared it.
    "writing files": FILE_WRITE_TOOLS,
    "executing code": SYSTEM_EXEC_TOOLS + TERMINAL_TOOLS + CODE_EXEC_TOOLS,
    # Overlaps "publishing" on the bare `deploy` atom, harmlessly: a tool
    # reachable through two categories is gateable by either, and the seam takes
    # the first declared match. ansible/helm were reachable through neither.
    "deploying infrastructure": DEPLOY_TOOLS,
    # Named for the risk, not the command: `git_reset` discards uncommitted work.
    # Deliberately its own category rather than an addition to "pushing commits",
    # which excludes it on purpose because a reset is not a push.
    "discarding local changes": GIT_RESET_TOOLS,
}


class ApprovalCategory(str, Enum):
    """Controlled vocabulary for a work item's ``requires_approval_before`` (GH#11206).

    Values match ``APPROVAL_CATEGORY_TOOLS`` keys exactly (enforced by test). A
    declared category outside this set matches no tools at the seam and silently
    disables the gate, so callers should validate against these values at set time.
    """

    PUSHING_COMMITS = "pushing commits"
    PUBLISHING = "publishing"
    DESTRUCTIVE_OPERATIONS = "destructive operations"
    ROTATING_CREDENTIALS = "rotating credentials"
    SENDING_EXTERNALLY = "sending externally"
    WRITING_FILES = "writing files"
    EXECUTING_CODE = "executing code"
    DEPLOYING_INFRASTRUCTURE = "deploying infrastructure"
    DISCARDING_LOCAL_CHANGES = "discarding local changes"


_VALID_APPROVAL_CATEGORIES = frozenset(c.value for c in ApprovalCategory)


def valid_approval_categories() -> "frozenset[str]":
    """Return the set of valid ``requires_approval_before`` category strings."""
    return _VALID_APPROVAL_CATEGORIES
