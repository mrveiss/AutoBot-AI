#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18122 S1 — the structural shape of the single KB creator in ``knowledge_factory.py``.

Sibling of ``one_knowledge_base_store_18122_test.py`` (which is at the file-size cap).
Each check is a matcher over source TEXT, with a positive and a negative fixture, then
applied to the real module -- a matcher run only on the real file would report a clean
tree if it were broken.

  (a) ``_create_new_knowledge_base`` hands its instance to ``_accept_new_kb``
  (b) ``_accept_new_kb`` calls the publisher and ``_adopt_legacy_facts``
  (c) only the publisher assigns ``_knowledge_base_instance`` (global or attribute)
  (d) the in-place ``initialize()`` path runs inside ``async with _knowledge_base_lock``
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root

_PUBLISHER = "_publish_knowledge_base"
_LOCK = "_knowledge_base_lock"

_GOOD = f"""
def {_PUBLISHER}(kb, app=None):
    global _knowledge_base_instance
    _knowledge_base_instance = kb

def _accept_new_kb(kb, app):
    {_PUBLISHER}(kb, app)
    _adopt_legacy_facts(kb)
    return kb

async def _create_new_knowledge_base(app):
    kb = KnowledgeBase()
    if await kb.initialize():
        return _accept_new_kb(kb, app)

async def _ready_app_state_kb(app):
    return await _try_initialize_existing_kb(app.state.knowledge_base, app)

async def _try_initialize_existing_kb(kb, app):
    async with {_LOCK}:
        if await kb.initialize():
            return _accept_new_kb(kb, app)

async def get_or_create_knowledge_base(app):
    return await _create_under_lock(app)

async def get_knowledge_base_async():
    return await _create_under_lock(None)
"""

_NO_ACCEPT = _GOOD.replace("return _accept_new_kb(kb, app)\n\nasync def _ready", "return kb\n\nasync def _ready")
_NO_ADOPT = _GOOD.replace("    _adopt_legacy_facts(kb)\n", "")
_NO_PUBLISH = _GOOD.replace(f"    {_PUBLISHER}(kb, app)\n    _adopt", "    _adopt")
_GLOBAL_REWRITE = _GOOD.replace(
    "    return await _create_under_lock(None)",
    "    global _knowledge_base_instance\n    _knowledge_base_instance = KnowledgeBase()\n    return _knowledge_base_instance",
)
_ATTR_REWRITE = _GOOD.replace(
    "    return await _create_under_lock(app)",
    "    factory_module._knowledge_base_instance = KnowledgeBase()\n    return await _create_under_lock(app)",
)
_HELPER_REWRITE = _GOOD + "\ndef _stash(kb):\n    global _knowledge_base_instance\n    _knowledge_base_instance = kb\n"
_UNLOCKED_INIT = _GOOD.replace(
    f"    async with {_LOCK}:\n        if await kb.initialize():\n            return _accept_new_kb(kb, app)",
    "    if await kb.initialize():\n        return _accept_new_kb(kb, app)",
)


def test_every_negative_fixture_actually_differs_from_the_good_one() -> None:
    """A `str.replace` that matched nothing leaves the good source and a vacuous negative."""
    negatives = (_NO_ACCEPT, _NO_ADOPT, _NO_PUBLISH, _GLOBAL_REWRITE, _ATTR_REWRITE, _HELPER_REWRITE, _UNLOCKED_INIT)
    assert all(n != _GOOD for n in negatives)


def _funcs(tree: ast.AST) -> dict[str, ast.AST]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _called(func: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _calls_helper(source: str, caller: str, *callees: str) -> bool:
    func = _funcs(ast.parse(source)).get(caller)
    return func is not None and set(callees) <= _called(func)


def _instance_assigners(source: str) -> set[str]:
    """Functions assigning ``_knowledge_base_instance`` as a global name or as an attribute."""
    found = set()
    for name, func in _funcs(ast.parse(source)).items():
        declared = {g for n in ast.walk(func) if isinstance(n, ast.Global) for g in n.names}
        for n in ast.walk(func):
            targets = (
                n.targets
                if isinstance(n, ast.Assign)
                else [n.target] if isinstance(n, (ast.AugAssign, ast.AnnAssign)) else []
            )
            for t in targets:
                is_global = isinstance(t, ast.Name) and t.id == "_knowledge_base_instance" and t.id in declared
                if is_global or (isinstance(t, ast.Attribute) and t.attr == "_knowledge_base_instance"):
                    found.add(name)
    return found


def _is_lock_block(node: ast.AST) -> bool:
    return isinstance(node, ast.AsyncWith) and any(
        isinstance(i.context_expr, ast.Name) and i.context_expr.id == _LOCK for i in node.items
    )


def _unlocked_initializes(source: str) -> tuple[int, int]:
    """(initialize() calls on the in-place path, how many sit outside the lock block).

    The in-place path is ``_ready_app_state_kb`` plus every module function it calls.
    """
    funcs = _funcs(ast.parse(source))
    root = funcs.get("_ready_app_state_kb")
    if root is None:
        return 0, 0
    total = outside = 0
    for func in [root] + [funcs[n] for n in _called(root) if n in funcs]:
        locked = {id(s) for b in ast.walk(func) if _is_lock_block(b) for s in ast.walk(b)}
        for n in ast.walk(func):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "initialize":
                total += 1
                outside += id(n) not in locked
    return total, outside


@pytest.fixture(scope="module")
def real_source() -> str:
    return (repo_root() / "autobot-backend" / "knowledge_factory.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(("source", "ok"), [(_GOOD, True), (_NO_ACCEPT, False)])
def test_a_creator_hands_off_to_accept(source: str, ok: bool) -> None:
    assert _calls_helper(source, "_create_new_knowledge_base", "_accept_new_kb") is ok


@pytest.mark.parametrize(("source", "ok"), [(_GOOD, True), (_NO_ADOPT, False), (_NO_PUBLISH, False)])
def test_b_accept_publishes_and_adopts(source: str, ok: bool) -> None:
    assert _calls_helper(source, "_accept_new_kb", _PUBLISHER, "_adopt_legacy_facts") is ok


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_GOOD, {_PUBLISHER}),
        (_GLOBAL_REWRITE, {_PUBLISHER, "get_knowledge_base_async"}),
        (_ATTR_REWRITE, {_PUBLISHER, "get_or_create_knowledge_base"}),
        (_HELPER_REWRITE, {_PUBLISHER, "_stash"}),
    ],
)
def test_c_only_the_publisher_assigns_the_instance(source: str, expected: set[str]) -> None:
    assert _instance_assigners(source) == expected


@pytest.mark.parametrize(("source", "outside"), [(_GOOD, 0), (_UNLOCKED_INIT, 1)])
def test_d_in_place_initialize_runs_under_the_lock(source: str, outside: int) -> None:
    total, got_outside = _unlocked_initializes(source)
    assert total == 1 and got_outside == outside


def test_real_creator_hands_off_and_accept_publishes_and_adopts(real_source: str) -> None:
    assert _calls_helper(real_source, "_create_new_knowledge_base", "_accept_new_kb"), "(a) #18122"
    assert _calls_helper(real_source, "_accept_new_kb", _PUBLISHER, "_adopt_legacy_facts"), "(b) #18122"


def test_real_only_the_publisher_assigns_the_instance(real_source: str) -> None:
    got = _instance_assigners(real_source)
    assert got == {_PUBLISHER}, f"(c) #18122: {sorted(got)} assign _knowledge_base_instance; only the publisher may"


def test_real_in_place_initialize_runs_under_the_lock(real_source: str) -> None:
    total, outside = _unlocked_initializes(real_source)
    assert total >= 1, "(d) the in-place initialize path is gone -- re-point this guard"
    assert outside == 0, f"(d) #18122: {outside} initialize() call(s) on the in-place path run outside {_LOCK}"
