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

from enum import Enum, Flag
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
    pats = tuple(patterns)
    lowered = tool_name.lower()
    # An aliased spelling is also tried as its canonical tool (#18294).
    for name in dict.fromkeys((lowered, canonical_tool_name(lowered))):
        matched = _match_one(name, pats, word_boundary)
        if matched is not None:
            return matched
    return None


def _match_one(name: str, pats: "tuple[str, ...]", word_boundary: bool) -> Optional[str]:
    """Exact match wins, otherwise the first (word-boundary) prefix match."""
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
# #18294: create_file/rename_file joined the atom (they were mutating but gated by no plane).
FILE_WRITE_TOOLS = (
    "write_file",
    "edit_file",
    "move_file",
    "copy_file",
    "create_directory",
    "create_file",
    "rename_file",
    "multi_edit",
    "apply_patch",
)
FILE_DELETE_TOOLS = ("delete_file", "remove_directory")
GIT_PUSH_TOOLS = ("git_push", "git_commit", "git_merge", "git_rebase", "git_force_push")
GIT_RESET_TOOLS = ("git_reset",)
HTTP_WRITE_TOOLS = ("http_post", "http_put", "http_patch", "http_delete", "send_request")
CODE_EXEC_TOOLS = ("code_interpreter",)
# #18294: owner decision 2026-10-11 -- every mutating tool is gated by a category.
PROCESS_EXEC_TOOLS = ("run_shell", "start_process", "stop_process", "manage_service")
DATA_WRITE_TOOLS = ("set_redis_value", "insert_database")
BROWSER_ACTION_TOOLS = ("navigate", "click", "fill", "select", "evaluate")
#: #18430: browser tools that only observe the page (and hover), and the index-addressed form of the actions.
BROWSER_READ_TOOLS = ("hover", "screenshot", "get_text", "get_attribute", "wait_for_selector", "browser_state")
BROWSER_INDEXED_TOOLS = ("click_index", "fill_index", "select_index", "hover_index")
DELEGATION_TOOLS = ("compose", "delegate")

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
    + PROCESS_EXEC_TOOLS
    + DATA_WRITE_TOOLS
    + BROWSER_ACTION_TOOLS
    + DELEGATION_TOOLS
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
    "executing code": SYSTEM_EXEC_TOOLS + TERMINAL_TOOLS + CODE_EXEC_TOOLS + PROCESS_EXEC_TOOLS,
    # Overlaps "publishing" on the bare `deploy` atom, harmlessly: a tool
    # reachable through two categories is gateable by either, and the seam takes
    # the first declared match. ansible/helm were reachable through neither.
    "deploying infrastructure": DEPLOY_TOOLS,
    # Named for the risk, not the command: `git_reset` discards uncommitted work.
    # Deliberately its own category rather than an addition to "pushing commits",
    # which excludes it on purpose because a reset is not a push.
    "discarding local changes": GIT_RESET_TOOLS,
    # #18294: the three classes of mutating tool no category reached.
    "writing data": DATA_WRITE_TOOLS,
    "browser actions": BROWSER_ACTION_TOOLS,
    "delegating work": DELEGATION_TOOLS,
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
    WRITING_DATA = "writing data"
    BROWSER_ACTIONS = "browser actions"
    DELEGATING_WORK = "delegating work"


_VALID_APPROVAL_CATEGORIES = frozenset(c.value for c in ApprovalCategory)


def approval_category_for(tool_name: str, categories: Iterable[str]) -> Optional[str]:
    """Return the first of *categories* that gates *tool_name*, else ``None`` (GH#11160, #18430).

    The one matcher every approval surface uses (the chat seam, the plan-time interrupt and the
    AI-line enforcement point). Word-boundary matching (GH#11206): ``deploy`` gates
    ``deploy_service`` but not ``deployment_status``. A false positive only ever adds a hold.
    """
    for category in categories:
        if match_tool_name(tool_name, APPROVAL_CATEGORY_TOOLS.get(category, ()), word_boundary=True):
            return category
    return None


def valid_approval_categories() -> "frozenset[str]":
    """Return the set of valid ``requires_approval_before`` category strings."""
    return _VALID_APPROVAL_CATEGORIES


# --- per-tool effect facts (GH#18294) --------------------------------------
#
# "What does this tool do to the world?" is declared HERE, once. The parallel
# analyzer, the code-exec sandbox policy and the repetition guard derive their
# sets from this table; each keeps its own *policy* (exact names vs prefix
# patterns, sandbox default, halt exemption) but none holds a tool-name literal
# for effect. The approval plane above (SENSITIVE_TOOLS) is deliberately
# unchanged by this table -- see ``approval_gap_tools``.


class ToolEffect(Flag):
    """What a tool does. Flags combine: ``execute_command`` is WRITE|STATE|EXEC."""

    READ = 1  #: reads a resource, changes nothing
    WRITE = 2  #: mutates a named resource (file, row, key, remote endpoint)
    STATE = 4  #: changes ambient system/session state later calls may depend on
    EXEC = 8  #: runs arbitrary code or commands
    DELEGATE = 16  #: hands work to another agent / composes tool calls
    POLL = 32  #: effect-free and meant to be re-issued until something changes
    ISOLATED_READ = 64  #: READ that touches no local resource (sandbox-safe default)
    DESTRUCTIVE = 128  #: discards data that cannot be recovered by re-running
    FILE_TARGET = 256  #: operates on a file path named in its arguments
    IN_PLACE_EDIT = 512  #: edits or deletes the content of an existing file

    #: Any effect that is not a pure read: the class that must serialise and be vetted.
    MUTATING = WRITE | STATE | EXEC | DELEGATE


_E = ToolEffect
_ROW = _E.WRITE | _E.STATE


def _entries(tools: Iterable[str], effect: ToolEffect) -> "dict[str, ToolEffect]":
    return {tool: effect for tool in tools}


#: Canonical tool name -> effect. One spelling per tool; see TOOL_ALIASES.
TOOL_EFFECTS: "dict[str, ToolEffect]" = {
    **_entries(SHELL_EXEC_TOOLS + TERMINAL_TOOLS + SYSTEM_EXEC_TOOLS, _E.EXEC | _ROW),
    **_entries(CONTAINER_ORCH_TOOLS + DEPLOY_TOOLS, _E.EXEC | _E.STATE),
    **_entries(FILE_WRITE_TOOLS, _E.WRITE),
    **_entries(FILE_DELETE_TOOLS, _E.WRITE | _E.DESTRUCTIVE),
    # A directory create/remove is a write AND ambient state later calls depend on
    # (the analyzer previously held these as STATE only; the catalogue as WRITE only).
    "create_directory": _ROW,
    "remove_directory": _ROW | _E.DESTRUCTIVE,
    **_entries(GIT_PUSH_TOOLS, _ROW),
    **_entries(GIT_RESET_TOOLS, _E.WRITE | _E.DESTRUCTIVE),
    **_entries(HTTP_WRITE_TOOLS, _E.WRITE),
    **_entries(CODE_EXEC_TOOLS, _E.EXEC | _E.STATE),
    **_entries(DATA_WRITE_TOOLS, _E.WRITE),
    **_entries(PROCESS_EXEC_TOOLS, _E.EXEC | _E.STATE),
    **_entries(BROWSER_ACTION_TOOLS, _E.STATE),
    "evaluate": _E.EXEC | _E.STATE,
    **_entries(DELEGATION_TOOLS, _E.DELEGATE),
    **_entries(
        ("read_file", "grep_search", "file_search", "list_directory", "query_database", "get_redis_value"),
        _E.READ,
    ),
    **_entries(("semantic_search", "search_knowledge"), _E.READ),
    **_entries(("web_search", "scrape_url", "map_site", "extract_structured_data"), _E.READ | _E.ISOLATED_READ),
    **_entries(("sleep", "wait", "poll", "check_status"), _E.POLL),
    # #18430: tools the live seam dispatches that were declared nowhere. The AI lines treat an unknown tool as
    # mutating (fail closed), so every builtin that only observes must be KNOWN to be a read.
    **_entries(BROWSER_READ_TOOLS + ("extract_content", "crawl_site", "read_spilled_output"), _E.READ),
}

#: Tools whose arguments name a file path (artifact capture, config guard, fact-forcing).
_FILE_PATH_TOOLS = tuple(t for t in FILE_WRITE_TOOLS if not t.endswith("_directory")) + ("delete_file", "read_file")
#: Tools that edit or delete the content of an EXISTING file in place (pure creators excluded).
_IN_PLACE_EDIT_TOOLS = ("edit_file", "write_file", "multi_edit", "apply_patch", "delete_file")
for _tool in _FILE_PATH_TOOLS:
    TOOL_EFFECTS[_tool] |= _E.FILE_TARGET
for _tool in _IN_PLACE_EDIT_TOOLS:
    TOOL_EFFECTS[_tool] |= _E.IN_PLACE_EDIT

#: Alternative spellings -> canonical name (so a tool named either way is
#: classified identically; before #18294 each site knew only one spelling).
TOOL_ALIASES: "dict[str, str]" = {
    "delete_directory": "remove_directory",
    "list_dir": "list_directory",
    # #18430: the index-addressed browser variants are the same action as their selector form.
    "click_index": "click",
    "fill_index": "fill",
    "select_index": "select",
    "hover_index": "hover",
}


def canonical_tool_name(tool_name: str) -> str:
    """Resolve an aliased spelling to the catalogue's canonical tool name."""
    return TOOL_ALIASES.get(tool_name, tool_name)


def tool_effect(tool_name: str) -> Optional[ToolEffect]:
    """Return the declared effect of *tool_name* (alias-aware), or ``None`` if unknown."""
    return TOOL_EFFECTS.get(canonical_tool_name(tool_name))


def has_effect(tool_name: str, effect: ToolEffect) -> bool:
    """True when *tool_name* is catalogued and carries any flag in *effect*."""
    declared = tool_effect(tool_name)
    return declared is not None and bool(declared & effect)


def tools_with(effect: ToolEffect, *, include_aliases: bool = True) -> "frozenset[str]":
    """Every tool name (aliases included by default) carrying any flag in *effect*."""
    names = {t for t, e in TOOL_EFFECTS.items() if e & effect}
    if include_aliases:
        names |= {a for a, c in TOOL_ALIASES.items() if c in names}
    return frozenset(names)


def tools_with_all(effect: ToolEffect) -> "frozenset[str]":
    """Every tool name carrying ALL the flags in *effect* (``tools_with`` is any-of)."""
    return frozenset(t for t, e in TOOL_EFFECTS.items() if e & effect == effect)


def approval_gap_tools() -> "frozenset[str]":
    """Mutating tools that ``SENSITIVE_TOOLS`` does not gate (exact or prefix match).

    Reported, not silently widened: ``SENSITIVE_TOOLS`` is parity-pinned and feeds
    ``DEFAULT_FORBIDDEN_TOOLS``, so closing the gap is an approval-policy decision.
    """
    return frozenset(t for t in tools_with(ToolEffect.MUTATING) if match_tool_name(t, SENSITIVE_TOOLS) is None)
