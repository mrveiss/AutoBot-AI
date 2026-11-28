# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19582 AC 5 — ONE wake dispatcher: the write points call it, and nothing copies it.

AST checks over the backend's non-test source:

* every event write point calls its ``wake_events`` function, and every
  ``wake_events`` path reaches ``event_wake.wake_agent``;
* the four event sources are named only by the dispatcher and its callers;
* a heartbeat run row is constructed only by the scheduler (and replay, which is
  not an event), and ``dispatch_run`` is called only by the dispatcher, the manual
  trigger and replay.

Each check has a control (``test_the_walker_sees_*``) so an empty result cannot
pass by the walker having read nothing.
"""

import ast
from functools import lru_cache
from pathlib import Path
from typing import Dict, Set, Tuple

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_EVENT_SOURCES = {"WORK_ITEM_COMMENTED", "WORK_ITEM_ASSIGNED", "AGENT_MENTIONED", "APPROVAL_DECIDED"}

#: (file, class or None, function) -> the wake function it must call.
_WRITE_POINTS: Dict[Tuple[str, str, str], str] = {
    ("llc/services/work_item_service.py", "WorkItemService", "create"): "wake_for_item_changes",
    ("llc/services/work_item_service.py", "WorkItemService", "update"): "wake_for_item_changes",
    ("llc/services/work_item_service.py", "WorkItemService", "add_comment"): "wake_for_comment",
    ("llc/services/handoff.py", "HandoffService", "human_to_agent"): "wake_for_item_changes",
    ("llc/services/handoff.py", "HandoffService", "request_changes"): "wake_for_item_changes",
    ("llc/services/approval.py", "ApprovalService", "decide"): "wake_for_decided_approval",
}

#: The functions that hand an event to the dispatcher itself.
_DISPATCHER_CALLERS = {
    ("llc/services/wake_events.py", None, "_wake"),
    ("llc/services/comment_wake_service.py", "CommentWakeService", "wake_for_comment"),
}

_SOURCE_NAMERS = {
    "llc/scheduler/event_wake.py",
    "llc/services/wake_events.py",
    "llc/services/comment_wake_service.py",
}
_RUN_CONSTRUCTORS = {"llc/scheduler/heartbeat_scheduler.py", "llc/services/replay_service.py"}
_DISPATCH_RUN_CALLERS = {"llc/scheduler/event_wake.py", "llc/api/agents.py", "llc/api/replay.py"}


@lru_cache(maxsize=1)
def _sources() -> Tuple[Tuple[str, Tuple[ast.AST, ...]], ...]:
    """Every non-test backend module as ``(path, its AST nodes)``, parsed once."""
    parsed = []
    for path in sorted(_BACKEND.rglob("*.py")):
        rel = path.relative_to(_BACKEND).as_posix()
        if "/tests/" in f"/{rel}" or rel.endswith("_test.py") or "/node_modules/" in rel:
            continue
        parsed.append((rel, tuple(ast.walk(ast.parse(path.read_text(encoding="utf-8"))))))
    return tuple(parsed)


def _function(rel: str, cls: str, name: str) -> ast.AST:
    tree = ast.parse((_BACKEND / rel).read_text(encoding="utf-8"))
    scope = tree.body if cls is None else next(n for n in tree.body if getattr(n, "name", None) == cls).body
    return next(n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def _called_names(node: ast.AST) -> Set[str]:
    names = set()
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        func = call.func
        names.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
    return names


@pytest.mark.parametrize("site", sorted(_WRITE_POINTS), ids=lambda s: f"{s[1]}.{s[2]}")
def test_each_write_point_calls_its_wake(site: Tuple[str, str, str]) -> None:
    assert _WRITE_POINTS[site] in _called_names(_function(*site)), f"{site} no longer wakes (#19582)"


@pytest.mark.parametrize("site", sorted(_DISPATCHER_CALLERS, key=str), ids=lambda s: s[2])
def test_each_wake_path_reaches_the_one_dispatcher(site: Tuple[str, str, str]) -> None:
    assert "wake_agent" in _called_names(_function(*site))


def _files_where(predicate) -> Set[str]:  # noqa: ANN001
    return {rel for rel, nodes in _sources() if any(predicate(n) for n in nodes)}


def _names_event_source(node: ast.AST) -> bool:
    """``HeartbeatInvocationSource.<event>`` (``ActivityEventType`` shares some member names)."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr in _EVENT_SOURCES
        and getattr(node.value, "id", None) == "HeartbeatInvocationSource"
    )


def _constructs_run(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "id", None) == "LLCHeartbeatRun"


def _calls_dispatch_run(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "dispatch_run"


def test_only_the_dispatcher_and_its_callers_name_an_event_source() -> None:
    assert _files_where(_names_event_source) == _SOURCE_NAMERS


def test_only_the_scheduler_and_replay_construct_a_run() -> None:
    assert _files_where(_constructs_run) == _RUN_CONSTRUCTORS


def test_only_the_dispatcher_manual_trigger_and_replay_dispatch_a_run() -> None:
    assert _files_where(_calls_dispatch_run) == _DISPATCH_RUN_CALLERS


def test_the_walker_sees_a_planted_second_dispatcher() -> None:
    """Control: the predicates fire on the shapes a second copy would have."""
    planted = ast.parse("LLCHeartbeatRun(a=1)\ns.dispatch_run(a, r)\nHeartbeatInvocationSource.WORK_ITEM_ASSIGNED\n")
    nodes = list(ast.walk(planted))
    assert any(map(_constructs_run, nodes)) and any(map(_calls_dispatch_run, nodes))
    assert any(map(_names_event_source, nodes))
    assert len(_sources()) > 500  # the walk read the backend, not an empty tree
