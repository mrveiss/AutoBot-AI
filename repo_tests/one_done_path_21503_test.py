# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A work item reaches done through ONE review-gated path (#21503).

``WorkItemService.transition_status`` sends every move to done to ``transition_to_done``, and a caller that
brings no review gate gets the real one, so a new caller of ``transition_status`` cannot bypass the gate.
What can still bypass it is code that skips ``transition_status``:

* a call to ``transition_to_done`` from outside the service module (it takes the gate as optional arguments); and
* a ``DoneGate(...)`` built outside the two homes that build one (the accessors, which fill it with the real
  services, and the service, which rebuilds it from ``transition_to_done``'s arguments), since a caller's own
  permissive gate is a way round the real one; and
* a write of ``WorkItemStatus.DONE`` to a work item outside the two homes that may stamp it: the service
  (``transition_to_done``'s stamp) and ``HandoffService.approve`` (a reviewer's decision, the review flow itself).

Boundary: a name is followed through ``import ... as`` and ``Alias = Name``; a write is an assignment (plain or
annotated) of the member to ``.status``, a stamp helper given it, ``.values(status=...)`` or ``LLCWorkItem(status=...)``
(see ``done_writes``). A status held in a variable (``item.status = new_status``) is not seen, and a read
(``filter_by(status=...)``, ``where(...)``) is not a write.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_SERVICE = "autobot-backend/llc/services/work_item_service.py"
_HANDOFF = "autobot-backend/llc/services/handoff.py"
#: Where a call to ``transition_to_done`` may be: the service itself (``transition_status`` delegates to it).
_CALL_HOMES = frozenset({_SERVICE})
#: Where ``WorkItemStatus.DONE`` may be written to a work item.
_WRITE_HOMES = frozenset({_SERVICE, _HANDOFF})
#: Where a ``DoneGate`` may be constructed.
_GATE_HOMES = frozenset({_SERVICE, "autobot-backend/llc/services/accessors.py"})
_STAMPS = frozenset({"stamp_status", "stamp_and_release"})


def _backend_python(root) -> list[str]:  # noqa: ANN001
    """Tracked Python under the backend; empty on an empty tree so the reach fraction can fire."""
    try:
        return tracked_paths(root, "autobot-backend/*.py")
    except EmptyEnumeration:
        return []


def _reference(root) -> int:  # noqa: ANN001
    """The same population from one plain spec, filtered here, so the sweep is measured against a second count."""
    try:
        return sum(1 for p in tracked_paths(root, "*.py") if p.startswith("autobot-backend/"))
    except EmptyEnumeration:
        return 0


REACH = declare(
    "one-done-path",
    discover=_backend_python,
    reference=_reference,
    min_fraction=1.0,  # discover and reference are the same population by construction: any gap is a real gap
    what="tracked backend python files",
    roots=("autobot-backend",),
)


def _bound(tree: ast.AST, symbol: str) -> set[str]:
    """The names *symbol* goes by in this file: itself, an ``import ... as`` alias, and ``Alias = symbol``."""
    names = {symbol}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(a.asname for a in node.names if a.name == symbol and a.asname)
    for node in ast.walk(tree):  # ``Gate = DoneGate`` makes ``Gate(...)`` a use too
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            value = node.value
            if (isinstance(value, ast.Name) and value.id in names) or (
                isinstance(value, ast.Attribute) and value.attr == symbol
            ):
                names.add(node.targets[0].id)
    return names


def _callee(call: ast.Call) -> tuple[str, bool]:
    """(name, qualified): ``f(...)`` is (f, False); ``mod.f(...)`` is (f, True)."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr, True
    return getattr(func, "id", ""), False


def _calls_of(tree: ast.AST, symbol: str) -> list[ast.Call]:
    """Calls of *symbol*: by a name it is bound to here, or as an attribute of any module (``mod.symbol(...)``)."""
    names = _bound(tree, symbol)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name, qualified = _callee(node)
            if (name == symbol and qualified) or (not qualified and name in names):
                found.append(node)
    return found


def _is_done(node: ast.AST, status_names: set[str]) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "DONE"
        and isinstance(node.value, (ast.Name, ast.Attribute))
        and (getattr(node.value, "id", None) in status_names or getattr(node.value, "attr", None) == "WorkItemStatus")
    )


def done_calls(source: str) -> list[int]:
    """Lines calling ``transition_to_done``, as a method or by name."""
    return sorted(c.lineno for c in _calls_of(parse_cache.parse(source), "transition_to_done"))


def gate_constructions(source: str) -> list[int]:
    """Lines constructing a ``DoneGate``, under any alias."""
    return sorted(c.lineno for c in _calls_of(parse_cache.parse(source), "DoneGate"))


def done_writes(source: str) -> list[int]:
    """Lines writing ``WorkItemStatus.DONE`` to a work item. The write shapes, and only these:

    * ``x.status = DONE`` and ``x.status: T = DONE``;
    * a stamp helper (``stamp_status`` / ``stamp_and_release``) given it as an argument;
    * ``.values(status=DONE)`` (an ``update(...)`` or ``insert(...)`` statement);
    * ``LLCWorkItem(..., status=DONE)`` (a new row).

    A read -- ``filter_by(status=DONE)``, ``where(...)``, a comparison -- is not a write.
    """
    tree = parse_cache.parse(source)
    status_names = _bound(tree, "WorkItemStatus")
    done = lambda n: _is_done(n, status_names)  # noqa: E731
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and done(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Attribute) and t.attr == "status" for t in targets):
                found.append(node.lineno)
    for symbol in _STAMPS:
        found += [c.lineno for c in _calls_of(tree, symbol) if any(done(a) for a in c.args)]
    for call in ast.walk(tree):
        if isinstance(call, ast.Call) and any(k.arg == "status" and done(k.value) for k in call.keywords):
            name, _qualified = _callee(call)
            if name == "values" or name in _bound(tree, "LLCWorkItem"):
                found.append(call.lineno)
    return sorted(set(found))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("await svc.transition_to_done(session, item_id)", [1]),
        ("await transition_to_done(session, item_id)", [1]),
        ("x = 1\nawait self.transition_to_done(s, i, review_gate_svc=None)", [2]),
        ("await svc.transition_status(session, item_id, WorkItemStatus.DONE)", []),
        ("def transition_to_done(self):\n    return 1", []),
        ("from m import transition_to_done as finish\nawait finish(session, item_id)", [2]),
    ],
    ids=["method", "bare-name", "second-line", "transition-status-is-gated", "a-definition-is-not-a-call", "aliased"],
)
def test_control_a_call_to_the_done_transition_is_seen(source: str, expected: list[int]) -> None:
    assert done_calls(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("item.status = WorkItemStatus.DONE", [1]),
        ("a = 1\nstamp_and_release(session, item, WorkItemStatus.DONE, now)", [2]),
        ("own_task.stamp_status(item, WorkItemStatus.DONE, now)", [1]),
        ("await s.execute(update(LLCWorkItem).values(status=WorkItemStatus.DONE))", [1]),
        ("item.status = WorkItemStatus.CANCELLED", []),
        ("item.status = new_status", []),
        ("if item.status == WorkItemStatus.DONE:\n    pass", []),
        ("stamp_status(item, new_status, now)", []),
        ("item.status: WorkItemStatus = WorkItemStatus.DONE", [1]),
        ("from m import WorkItemStatus as S\nitem.status = S.DONE", [2]),
        ("from m import stamp_status as ss\nss(item, WorkItemStatus.DONE, now)", [2]),
        ("row = LLCWorkItem(title=t, status=WorkItemStatus.DONE)", [1]),
        ("q = select(LLCWorkItem).filter_by(status=WorkItemStatus.DONE)", []),
        ("q = select(LLCWorkItem).where(LLCWorkItem.status == WorkItemStatus.DONE)", []),
        ("q = repo.list(status=WorkItemStatus.DONE)", []),
    ],
    ids=[
        "assign",
        "stamp-and-release",
        "stamp-status",
        "update-values",
        "other-status",
        "variable",
        "compare",
        "stamp-var",
        "annotated-assign",
        "aliased-enum",
        "aliased-stamp",
        "new-row",
        "filter-by-is-a-read",
        "where-is-a-read",
        "a-keyword-on-any-call-is-not-a-write",
    ],
)
def test_control_a_write_of_done_is_seen(source: str, expected: list[int]) -> None:
    assert done_writes(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("gate = DoneGate(permissive_svc)", [1]),
        ("x = 1\ng = gated_done.DoneGate(review_gate_svc=None)", [2]),
        ("class DoneGate:\n    pass", []),
        ("g = done_gate_for()", []),
        ("from m import DoneGate as Gate\ng = Gate(review_gate_svc=None)", [2]),
        ("import m.work_item_gated_done as g\nx = g.DoneGate(None)", [2]),
        ("from m import DoneGate\nGate = DoneGate\nx = Gate()", [3]),
    ],
    ids=[
        "bare",
        "qualified",
        "a-definition-is-not-a-construction",
        "the-accessor",
        "from-import-alias",
        "module-alias",
        "assigned-alias",
    ],
)
def test_control_a_built_gate_is_seen(source: str, expected: list[int]) -> None:
    assert gate_constructions(source) == expected


def _production() -> list[tuple[str, str]]:
    sources = []
    for rel in REACH.examined(_ROOT):
        base = rel.rsplit("/", 1)[-1]
        if is_test_filename(base, include_js=False) or "/tests/" in f"/{rel}" or "test_support" in base:
            continue
        text = (_ROOT / rel).read_text(encoding="utf-8")
        if "DONE" in text or "transition_to_done" in text or "DoneGate" in text:
            sources.append((rel, text))
    return sources


def test_nothing_outside_the_service_calls_the_done_transition() -> None:
    offenders = [f"{rel}:{n}" for rel, text in _production() if rel not in _CALL_HOMES for n in done_calls(text)]
    assert not offenders, "call transition_status (it delegates, with the gate) instead: " + ", ".join(offenders)


def test_nothing_outside_the_homes_writes_done_to_a_work_item() -> None:
    offenders = [f"{rel}:{n}" for rel, text in _production() if rel not in _WRITE_HOMES for n in done_writes(text)]
    assert not offenders, "a work item is finished by WorkItemService.transition_status: " + ", ".join(offenders)


def test_nothing_outside_the_homes_builds_a_done_gate() -> None:
    offenders = [
        f"{rel}:{n}" for rel, text in _production() if rel not in _GATE_HOMES for n in gate_constructions(text)
    ]
    assert not offenders, "get the gate from llc.services.accessors.done_gate_for: " + ", ".join(offenders)


def test_the_homes_are_real() -> None:
    """Control: each home is examined and does what it is excused for, so an excuse cannot outlive its code."""
    seen = {rel: text for rel, text in _production()}
    assert done_writes(seen[_SERVICE]) and done_writes(seen[_HANDOFF])
    assert all(gate_constructions(seen[home]) for home in _GATE_HOMES)
