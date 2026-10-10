# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One LLC ``actor_id`` helper (#15754).

``_actor_id`` was written three times (roles, contacts, workflows) and the security
rationale -- the acting user comes from the session, never the body -- drifted between the
copies. It now lives once in ``autobot-backend/llc/api/_common.py``.

A copy is either a function named ``actor_id``/``_actor_id`` or an inline
``uuid.UUID(str(<x>.get("id") or <x>.get("user_id")))``. The detector reads the syntax tree,
so a docstring or comment naming either is not a definition.
"""

from __future__ import annotations

import ast
import functools

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-backend/llc/api/_common.py"
_NAMES = {"actor_id", "_actor_id"}


def _is_session_id_pick(node: ast.AST) -> bool:
    """`<x>.get("id") or <x>.get("user_id")`."""
    if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
        return False
    keys = set()
    for v in node.values:
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "get" and v.args:
            if isinstance(v.args[0], ast.Constant):
                keys.add(v.args[0].value)
    return {"id", "user_id"} <= keys


def _is_uuid_call(node: ast.AST) -> bool:
    f = getattr(node, "func", None)
    return isinstance(f, ast.Attribute) and f.attr == "UUID" and isinstance(f.value, ast.Name) and f.value.id == "uuid"


def _copies_actor_id(source: str) -> bool:
    """True when `source` defines an actor-id helper or inlines the session-id-to-UUID pick."""
    tree = ast.parse(source)
    if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in _NAMES for n in ast.walk(tree)):
        return True
    for node in ast.walk(tree):
        if _is_uuid_call(node) and any(_is_session_id_pick(s) for s in ast.walk(node)):
            return True
        # the two-step form: raw = <pick>; ... uuid.UUID(str(raw))
    picked = {
        t.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and _is_session_id_pick(n.value)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    return any(
        _is_uuid_call(n) and any(isinstance(s, ast.Name) and s.id in picked for s in ast.walk(n))
        for n in ast.walk(tree)
    )


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        (
            "a local helper",
            'def _actor_id(u):\n    raw = u.get("id") or u.get("user_id")\n    return uuid.UUID(str(raw))\n',
            True,
        ),
        ("an inline pick", 'a = uuid.UUID(str(u.get("id") or u.get("user_id")))\n', True),
        ("a renamed two-step copy", 'r = u.get("id") or u.get("user_id")\nreturn uuid.UUID(str(r))\n', True),
        ("a caller of the shared helper", "from ._common import actor_id\nx = actor_id(u)\n", False),
        ("a pick that is not made a UUID", 'uid = u.get("id") or u.get("user_id")\nif not uid:\n    pass\n', False),
        ("a docstring naming it", 'def f():\n    """_actor_id: uuid.UUID(str(x))"""\n', False),
    ],
)
def test_the_matcher_tells_a_copy_from_a_use(label: str, source: str, expected: bool) -> None:
    assert _copies_actor_id(source) is expected, label


def _population(root) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend/llc")
    except EmptyEnumeration:
        return []
    return [
        r for r in tracked if r.endswith(".py") and "/tests/" not in r and not r.rsplit("/", 1)[-1].startswith("test_")
    ]


REACH = declare(
    "llc-actor-id-scan",
    discover=_population,
    # Mid-window, from REACH.window() = (106, 206, 156) against 206 files, growth=100.
    floor=156,
    what="non-test python source",
    roots=("autobot-backend/llc",),
    growth=100,
)


@functools.lru_cache(maxsize=1)
def _copies() -> tuple[str, ...]:
    root = repo_root()
    return tuple(
        r for r in REACH.examined(root) if r != _CANONICAL and _copies_actor_id((root / r).read_text(encoding="utf-8"))
    )


def test_the_canonical_helper_is_the_only_actor_id() -> None:
    assert (repo_root() / _CANONICAL).is_file()
    assert _copies_actor_id((repo_root() / _CANONICAL).read_text(encoding="utf-8")), "canonical lost its helper"
    assert not _copies(), f"#15754: {list(_copies())} copy actor_id; import it from llc.api._common instead."
