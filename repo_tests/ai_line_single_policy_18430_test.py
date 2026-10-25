# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One approval policy decides whether an agent may act: the AI lines (#18430, #17463).

#17463 found three approval policies of which one was enforced: ``needs_approval()`` (role flags, no
caller), the ``minimal`` guard profile (approval switched off, in a dormant loop) and the live gate.
#18430 made the three AI lines THE policy, resolved in ``services/ai_line_enforcement.py``. This keeps
a fourth from landing the way the others did, with six checks:

1. **The inventory of approval-decision functions is closed.** Every ``def`` named ``needs_approval`` /
   ``requires_approval`` / ``_requires_approval`` / ``*_needs_approval`` in production source is listed
   below with the role it plays; an unlisted one is a second decision path, and a listed one that vanished
   is a stale claim.
2. **The surfaces call the point.** The chat seam and the agent terminal call ``enforce_line``; the
   plan-time interrupt calls ``resolve_action_line``; the role policy has its one caller there.
3. **One writer of the line store.** ``record_approved_line`` is called only by the post-approval handler,
   so no agent path can change a line.
4. **The retired work-item hold stays retired.** The dispatch seam asks ``_enforce_ai_line`` and nothing
   else for an approval hold.
5. **The entry points are a closed set** (chat seam, terminal, realtime/voice bridge). A2A is not one: its
   executor hands the request to the orchestrator and runs no tool itself (``a2a/task_executor.py``).
6. **The dormant loop stays dormant.** ``AgentLoop`` has no production caller, and ``minimal`` (approval
   off) is documented dev-only; wiring the loop in must first make that profile unable to disable approval.

What this cannot see, stated so an empty result is read correctly: an approval decision spelled with a
name outside the pattern (a ``can_run`` that gates execution), or reached by a call through ``getattr`` /
a string. Only non-test Python under the roots is read, and the scan fails below its reach floor.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend", "autobot_shared")
_DECISION_NAME = re.compile(r"^_?(needs_approval|requires_approval)$|_needs_approval$")

_ENFORCEMENT = "autobot-backend/services/ai_line_enforcement.py"
_TERMINAL = "autobot-backend/services/agent_terminal/ai_line_gate.py"
_GUARDS = "autobot-backend/chat_workflow/tool_dispatch_guards.py"
_GRAPH = "autobot-backend/chat_workflow/graph.py"
_HANDLER = "autobot-backend/services/ai_line_change_action.py"
_STORE = "autobot-backend/llc/services/ai_lines.py"
_DISPATCH = "autobot-backend/chat_workflow/tool_handler.py"
_BRIDGE = "autobot-backend/services/realtime_mcp_bridge.py"
_VOICE_ROUTES = ("autobot-backend/api/voice.py", "autobot-backend/api/realtime_session.py")
_TOOL_EXECUTING_ROUTES = ("autobot-backend/api/realtime_session.py",)

#: Every approval-decision function in production, and what it is. Adding one means saying which of these
#: it is; none of them may be a policy of its own.
DECISION_FUNCTIONS: dict[tuple[str, str], str] = {
    ("autobot-backend/services/command_approval_manager.py", "needs_approval"): (
        "input: the role policy (#17463); its only caller is the terminal's resolver, and it can only tighten"
    ),
    ("autobot-backend/services/agent_terminal/approval_handler.py", "needs_approval"): (
        "input: wrapper over the role policy, called by the terminal's AI-line resolver"
    ),
    (_GRAPH, "_tool_call_needs_approval"): "projection: delegates to call_needs_approval, the point's own resolver",
    (_ENFORCEMENT, "call_needs_approval"): "the point itself: plan-time projection of resolve_action_line",
    ("autobot-backend/agent_loop/loop.py", "_requires_approval"): (
        "dormant: AgentLoop has no production caller (#11221); see the dormancy check"
    ),
    ("autobot-backend/llc/services/approval.py", "requires_approval"): (
        "other plane: a board gate on company operations (hire, budget), not on an agent's tool action"
    ),
    ("autobot-backend/context_aware_decision/decision_engine.py", "_requires_approval"): (
        "other plane: the decision engine's recommendation to a person, not an enforcement"
    ),
}


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, *_ROOTS) if _is_source_python(rel)]
    except EmptyEnumeration:
        return []


def _all_python(root: Path) -> int:
    try:
        return sum(1 for rel in tracked_paths(root, *_ROOTS) if rel.endswith(".py"))
    except EmptyEnumeration:
        return 0


#: Measured 2026-10-12: ~58% of tracked ``.py`` under the two roots is non-test source; 0.45 leaves the
#: band a shift of source into tests could take before the sweep is meaningfully narrower.
REACH = declare(
    "ai-line-single-policy",
    discover=_source_population,
    reference=_all_python,
    min_fraction=0.45,
    what="non-test python source",
    roots=_ROOTS,
)


def decision_functions(source: str) -> list[str]:
    """Names of approval-decision ``def``s in *source*."""
    return [
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _DECISION_NAME.search(node.name)
    ]


def calls_of(source: str, name: str) -> list[int]:
    """Lines calling ``name(...)`` or ``<obj>.name(...)``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == name) or (
                isinstance(func, ast.Attribute) and func.attr == name
            ):
                found.append(node.lineno)
    return found


@functools.lru_cache(maxsize=1)
def _population() -> tuple[tuple[str, str], ...]:
    root = repo_root()
    texts = []
    for rel in REACH.examined(root):
        try:
            ast.parse(text := (root / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        texts.append((rel, text))
    REACH.completed(len(texts), root)
    return tuple(texts)


def _sources() -> dict[str, str]:
    return dict(_population())


def _callers(name: str, *, skip: frozenset[str] = frozenset()) -> set[str]:
    return {rel for rel, src in _sources().items() if rel not in skip and name in src and calls_of(src, name)}


# -- 1. the inventory is closed ----------------------------------------------------------------------------


def test_the_scan_is_not_vacuous() -> None:
    sources = _sources()
    for rel in (_ENFORCEMENT, _TERMINAL, _GUARDS, _GRAPH, _HANDLER, _STORE, _DISPATCH, _BRIDGE, *_VOICE_ROUTES):
        assert rel in sources, f"the scan never read {rel}"


def test_every_approval_decision_function_is_listed_and_every_listed_one_exists() -> None:
    found = {(rel, name) for rel, src in _sources().items() for name in decision_functions(src)}
    unlisted = sorted(found - set(DECISION_FUNCTIONS))
    stale = sorted(set(DECISION_FUNCTIONS) - found)
    assert not unlisted, (
        f"#18430: approval-decision function(s) outside the lines policy: {unlisted}. Resolve the action's line "
        "through services.ai_line_enforcement (enforce_line / resolve_action_line), or list it in "
        "DECISION_FUNCTIONS with the plane it belongs to."
    )
    assert not stale, f"#18430: DECISION_FUNCTIONS names function(s) that no longer exist: {stale}"


def test_the_detector_sees_a_decision_function_and_not_prose() -> None:
    assert decision_functions("def needs_approval(x): ...\nasync def _requires_approval(): ...\n") == [
        "needs_approval",
        "_requires_approval",
    ]
    assert decision_functions("def _tool_call_needs_approval(): ...\n") == ["_tool_call_needs_approval"]
    assert decision_functions("# needs_approval\nx = 'requires_approval'\ndef approve(): ...\n") == []


# -- 2. the surfaces call the point --------------------------------------------------------------------------


def test_the_chat_seam_and_the_terminal_call_the_enforcement_point() -> None:
    sources = _sources()
    assert calls_of(sources[_GUARDS], "enforce_line"), "the chat seam no longer resolves a tool's line"
    assert calls_of(sources[_TERMINAL], "enforce_line"), "the agent terminal no longer resolves a command's line"
    assert calls_of(sources[_GRAPH], "call_needs_approval"), "the plan-time interrupt decides without the point"


def test_exactly_the_known_entry_points_enforce_a_line() -> None:
    """The set of places that decide a line is closed: chat seam, terminal, realtime/voice bridge (#18430)."""
    callers = _callers("enforce_line", skip=frozenset({_ENFORCEMENT}))
    assert callers == {_GUARDS, _TERMINAL, _BRIDGE}, (
        f"#18430: enforce_line is called from {sorted(callers)}. A new entry point that executes an agent's "
        "tool must resolve its line there; list it here once it does."
    )


def test_the_realtime_bridge_is_reached_only_by_routes_that_pass_the_authenticated_company() -> None:
    users = _callers("get_realtime_bridge", skip=frozenset({_BRIDGE}))
    assert users == set(
        _VOICE_ROUTES
    ), f"#18430: a new caller of the realtime bridge: {sorted(users - set(_VOICE_ROUTES))}"
    # #18721 removed voice.py's duplicate realtime call route; the tool-executing call lives only
    # in realtime_session.py, while voice.py only lists tools. Both still reach the bridge above.
    for rel in _TOOL_EXECUTING_ROUTES:
        sites = [
            node
            for node in ast.walk(ast.parse(_sources()[rel]))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "call_tool"
        ]
        assert sites, f"{rel} no longer calls the bridge"
        for site in sites:
            company = next((kw.value for kw in site.keywords if kw.arg == "company_id"), None)
            assert company is not None and "org_id" in ast.unparse(
                company
            ), f"#18430: {rel}:{site.lineno} calls the bridge without the authenticated org_id as company_id"


def test_the_role_policy_is_consulted_by_the_terminal_and_only_there() -> None:
    callers = _callers("needs_approval", skip=frozenset({"autobot-backend/services/command_approval_manager.py"}))
    assert callers == {_TERMINAL, "autobot-backend/services/agent_terminal/approval_handler.py"}, (
        f"#17463: the role policy needs_approval() is consulted by {sorted(callers)}; it is an input to the "
        "AI-line resolver in the terminal, and a second consumer would be a second policy"
    )


# -- 3. one writer of the line store -------------------------------------------------------------------------


def test_only_the_post_approval_handler_writes_a_line() -> None:
    assert _callers("record_approved_line", skip=frozenset({_STORE})) == {
        _HANDLER
    }, "#18430: agents never change a line; record_approved_line may be called only by the post-approval handler"
    constructors = {rel for rel, src in _sources().items() if calls_of(src, "LLCAiLine")}
    assert constructors == {
        _STORE
    }, f"#18430: LLCAiLine rows are built outside the store module: {sorted(constructors)}"


def test_no_route_or_tool_handler_imports_the_writer() -> None:
    offenders = {
        rel
        for rel, src in _sources().items()
        if rel not in {_HANDLER, _STORE} and re.search(r"import[^\n]*\brecord_approved_line\b", src)
    }
    assert not offenders, f"#18430: {sorted(offenders)} import the line writer"


def test_the_line_change_cannot_be_forged_through_a_create_route_or_decided_by_a_parsed_username() -> None:
    """Four eyes needs a requester the caller did not write and a decider that is a verified id (#18430)."""
    sources = _sources()
    for rel in ("autobot-backend/api/approval_gates.py", "autobot-backend/llc/api/approvals.py"):
        assert calls_of(sources[rel], "is_server_only_action"), f"{rel} creates approvals without the server-only check"
    gates = sources["autobot-backend/api/approval_gates.py"]
    assert calls_of(
        gates, "_guard_resubmit"
    ), "resubmit can rewrite a reviewed proposal and bypass the create-route check"
    handler = sources[_HANDLER]
    assert "server_only=True" in handler, "ai_line.set_line must be registered as server-only"
    assert calls_of(handler, "verified_decider"), "the handler must compare the verified decider id"
    assert (
        not calls_of(handler, "_decider_id") and "User.username" not in handler
    ), "a username must never be parsed or looked up as the decider id (it can spell another user's UUID)"


# -- 4. the retired hold stays retired -----------------------------------------------------------------------


def test_the_dispatch_seam_asks_the_lines_and_nothing_else_for_an_approval_hold() -> None:
    dispatch = _sources()[_DISPATCH]
    assert "_enforce_ai_line(" in dispatch
    assert "enforce_work_item_approval" not in dispatch and "_enforce_work_item_approval" not in dispatch, (
        "#18430: the work-item hold was folded into the AI-line point; a second approval hold at the seam "
        "would be a second policy"
    )
    revived = {
        rel
        for name in ("enforce_work_item_approval", "_enforce_work_item_approval")
        for rel, src in _sources().items()
        if calls_of(src, name)
    }
    assert not revived, f"#18430: the retired work-item hold is called again from {sorted(revived)}"


# -- 5. the dormant loop stays dormant ------------------------------------------------------------------------

_LOOP_CALLERS_ALLOWED = frozenset({"autobot-backend/benchmarks/benchmark_belief_state.py"})


def test_the_agent_loop_has_no_production_caller_while_the_minimal_profile_can_switch_approval_off() -> None:
    profile = _sources()["autobot-backend/agent_loop/guard_profile.py"]
    assert '"require_approval_for_sensitive": False' in profile, "the minimal profile changed: re-read this guard"
    assert "DEV-ONLY" in profile, "the minimal profile must say it is dev-only (#17463)"
    callers = {
        rel
        for rel, src in _sources().items()
        if not rel.startswith("autobot-backend/agent_loop/") and calls_of(src, "AgentLoop")
    }
    assert callers <= _LOOP_CALLERS_ALLOWED, (
        f"#17463: AgentLoop is instantiated by {sorted(callers - _LOOP_CALLERS_ALLOWED)} while "
        "AUTOBOT_GUARD_PROFILE=minimal can turn approval off. Before wiring the loop in, make "
        "_requires_approval resolve through services.ai_line_enforcement."
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("loop = AgentLoop(cfg)\n", [1]),
        ("x = agent_loop.AgentLoop(cfg)\n", [1]),
        ("from agent_loop import AgentLoop\n", []),
        ('"""AgentLoop(…) is dormant."""\n', []),
    ],
)
def test_the_caller_matcher_sees_a_call_not_a_mention(source: str, expected: list[int]) -> None:
    assert calls_of(source, "AgentLoop") == expected
