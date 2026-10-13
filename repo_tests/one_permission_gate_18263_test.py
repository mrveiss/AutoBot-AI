# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One permission evaluator, one ``require_permission`` / ``require_any_permission`` (#18263).

Owner ruling 2026-10-11 (strict union): both services apply ONE decision,
``autobot_shared/auth/permission_evaluator.py``, through ONE gate,
``autobot_shared/auth/permission_gate.py``; each service only re-exports the gate's
factories. Two rules, read from the syntax tree of every non-test python source:

1. Each decision function and each factory is DEFINED in exactly one file. A second
   ``def`` is how the three forks this replaced came about.
2. No call to a permission factory passes a string. The gate raises on one at import
   time; this catches it before then, and in code paths no import reaches.

``_PENDING`` lists definitions that still exist and must go. It only shrinks: an
entry whose file no longer defines the name fails, so it is removed when retired.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_EVALUATOR = "autobot_shared/auth/permission_evaluator.py"
_GATE = "autobot_shared/auth/permission_gate.py"

#: Each name, and the one file allowed to define it.
_HOMES = {
    "role_grant": _EVALUATOR,
    "db_grant": _EVALUATOR,
    "permission_allowed": _EVALUATOR,
    "evaluate_any": _EVALUATOR,
    "evaluate_permission": _EVALUATOR,
    "key_scope_allows": "autobot_shared/auth/key_scopes.py",
    "require_permission": _GATE,
    "require_any_permission": _GATE,
}

#: Still-defined second copies, each to be retired (#18263 remainder). Only shrinks.
_PENDING = {
    ("autobot_shared/user_management/middleware/rbac_decorators.py", "require_permission"),
    ("autobot_shared/user_management/middleware/rbac_decorators.py", "require_any_permission"),
}

#: Factories whose permission argument must be a ``Permission`` member, never a string.
_FACTORIES = frozenset({"require_permission", "require_any_permission", "require_key_permission"})


def _definitions(tree: ast.AST) -> set[str]:
    """Names defined by ``def`` / ``async def`` anywhere in *tree*, methods included."""
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _string_factory_calls(tree: ast.AST) -> list[int]:
    """Line numbers of factory calls with a string (or f-string) argument."""
    lines = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
        if name not in _FACTORIES:
            continue
        args = [*n.args, *(k.value for k in n.keywords)]
        if any(
            isinstance(a, ast.JoinedStr) or (isinstance(a, ast.Constant) and isinstance(a.value, str)) for a in args
        ):
            lines.append(n.lineno)
    return lines


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "one-permission-gate-scan",
    discover=_source_population,
    # Same population as fact-read-authorization-scan (#18184): 2997 at its measurement, growth 300.
    floor=2997,
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)

_NEEDLES = (*_HOMES, *_FACTORIES)


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[dict[str, tuple[str, ...]], tuple[str, ...], int]:
    """(name -> files defining it, string-call sites, files read)."""
    defined: dict[str, list[str]] = {name: [] for name in _HOMES}
    string_calls: list[str] = []
    read = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        read += 1
        if not any(needle in source for needle in _NEEDLES):
            continue
        tree = ast.parse(source)
        for name in _definitions(tree) & defined.keys():
            defined[name].append(rel)
        string_calls.extend(f"{rel}:{line}" for line in _string_factory_calls(tree))
    REACH.completed(read)
    return {k: tuple(sorted(v)) for k, v in defined.items()}, tuple(sorted(string_calls)), read


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("dep = require_permission(Permission.ADMIN_SYSTEM)\n", []),
        ("dep = require_permission('admin.system')\n", [1]),
        ("dep = gate.require_any_permission(Permission.API_READ, f'{x}.read')\n", [1]),
        ("dep = require_key_permission(permission='knowledge.read')\n", [1]),
        ("dep = check_permission('admin.system')\n", []),
        ("# require_permission('admin.system')\nx = 1\n", []),
    ],
)
def test_the_string_call_detector_has_contrast(source: str, expected: list[int]) -> None:
    assert _string_factory_calls(ast.parse(source)) == expected


def test_the_definition_detector_sees_methods_and_async_defs() -> None:
    tree = ast.parse("class G:\n    def require_permission(self, p): ...\nasync def evaluate_any(c, p): ...\n")
    assert _definitions(tree) == {"require_permission", "evaluate_any"}
    assert _definitions(ast.parse("require_permission = gate.require_permission\n")) == set()


def test_the_scan_is_not_vacuous() -> None:
    _, _, read = _scan()
    assert read >= REACH.floor, f"read {read} files, below the declared floor {REACH.floor}"


@pytest.mark.parametrize("name", sorted(_HOMES))
def test_each_name_is_defined_once_in_its_home(name: str) -> None:
    defined, _, _ = _scan()
    pending = {rel for rel, n in _PENDING if n == name}
    assert _HOMES[name] in defined[name], f"{name} is no longer defined in {_HOMES[name]}; re-derive this guard"
    extra = sorted(set(defined[name]) - {_HOMES[name]} - pending)
    assert extra == [], f"{name} is defined again in {extra}; re-export the shared one instead (#18263)"


@pytest.mark.parametrize(("rel", "name"), sorted(_PENDING))
def test_a_pending_entry_still_exists(rel: str, name: str) -> None:
    """The allow-list shrinks: a retired definition must take its entry with it."""
    defined, _, _ = _scan()
    assert rel in defined[name], f"{rel} no longer defines {name}; delete its _PENDING entry"


def test_no_permission_factory_is_called_with_a_string() -> None:
    _, string_calls, _ = _scan()
    assert string_calls == (), f"string permission arguments (use a Permission member): {list(string_calls)}"
