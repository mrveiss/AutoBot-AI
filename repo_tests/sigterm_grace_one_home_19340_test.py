# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLC SIGTERM grace has ONE home: ``llc/adapters/subprocess_base.SIGTERM_GRACE_SECONDS`` (#19340).

``process_adapter.py`` killed a cancelled child after 5 s while every subprocess-lifecycle
adapter waited 10 s, so a process needing 7 s to shut down died under one adapter and
survived under the other. Both now pass the one constant to ``terminate_pid``.

A copy comes back in two shapes, and both are flagged anywhere under ``autobot-backend/llc``:
a numeric literal bound to a ``*SIGTERM_GRACE*`` name outside the home, and a literal grace
passed straight to ``terminate_pid``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_LLC = "autobot-backend/llc"
_HOME = "autobot-backend/llc/adapters/subprocess_base.py"
_SUPPORT = "autobot-backend/llc/adapters/subprocess_support.py"


def _modules(root: Path) -> list[Path]:
    return sorted(p for p in (root / _LLC).rglob("*.py") if "tests" not in p.parts and not p.name.endswith("_test.py"))


#: 216 non-test LLC modules measured at #19340; repinned by scripts/repin_reach_floors.py.
REACH = declare(
    "llc-sigterm-grace-copies",
    discover=_modules,
    floor=227,  # mid-window: population 237, window (217, 237)
    growth=20,  # ~9%: ordinary LLC growth between repins must not turn an unrelated PR red
    what="non-test LLC modules",
    roots=(_LLC,),
)


def _is_number(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _grace_param() -> str:
    """The real name of ``terminate_pid``'s grace parameter, read from its definition, not assumed."""
    tree = ast.parse((repo_root() / _SUPPORT).read_text(encoding="utf-8"))
    func = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == "terminate_pid"
    )
    return func.args.args[1].arg


def _target_names(target: ast.AST) -> list[str]:
    """Every name a binding target writes: plain, attribute (``self.x``) or each element of a tuple/list."""
    if isinstance(target, ast.Tuple | ast.List):
        return [name for element in target.elts for name in _target_names(element)]
    if isinstance(target, ast.Name):
        return [target.id]
    return [target.attr] if isinstance(target, ast.Attribute) else []


def _bound_pairs(target: ast.AST, value: ast.AST | None) -> list[tuple[str, ast.AST | None]]:
    """``(name, value)`` for each name *target* writes; an unpacked tuple pairs element by element.

    When the lengths differ (a starred target), every name keeps the whole value, so any literal in it
    counts: an unpairable binding errs towards a report.
    """
    sequences = isinstance(target, ast.Tuple | ast.List) and isinstance(value, ast.Tuple | ast.List)
    if sequences and len(value.elts) == len(target.elts):
        return [pair for t, v in zip(target.elts, value.elts) for pair in _bound_pairs(t, v)]
    return [(name, value) for name in _target_names(target)]


def _binding_hits(node: ast.AST, rel: str) -> list[str]:
    """A numeric literal bound to a ``*SIGTERM_GRACE*`` name outside the home (incl. ``+=`` and unpacking)."""
    if rel == _HOME or not isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
        return []
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    pairs = [pair for t in targets for pair in _bound_pairs(t, node.value)]
    hit = [n for n, v in pairs if "SIGTERM_GRACE" in n.upper() and _bound_literal(v)]
    return [f"{rel}:{node.lineno}: {hit[0]} bound to a literal"] if hit else []


def _bound_literal(value: ast.AST | None) -> bool:
    """A number, or a tuple that still carries one (the target could not be paired element by element)."""
    if isinstance(value, ast.Tuple | ast.List):
        return any(_is_number(v) for v in value.elts)
    return _is_number(value)


def _call_hits(node: ast.AST, rel: str, param: str) -> list[str]:
    """A literal grace passed to ``terminate_pid``, positionally or by its real keyword."""
    if not isinstance(node, ast.Call) or getattr(node.func, "id", getattr(node.func, "attr", "")) != "terminate_pid":
        return []
    grace = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == param), None)
    return [f"{rel}:{node.lineno}: terminate_pid(..., {grace.value}, ...)"] if _is_number(grace) else []


def copies(source: str, rel: str, param: str = "grace_seconds") -> list[str]:
    """Each literal grace in *source*."""
    return [
        hit for node in ast.walk(ast.parse(source)) for hit in _binding_hits(node, rel) + _call_hits(node, rel, param)
    ]


def test_the_grace_has_one_home_on_the_live_tree() -> None:
    root = repo_root()
    files = REACH.examined(root)
    found = [
        hit
        for path in files
        for hit in copies(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix(), _grace_param())
    ]
    REACH.completed(files)
    assert not found, f"import SIGTERM_GRACE_SECONDS from {_HOME} instead: {found}"


def test_process_adapter_passes_the_home_constant_to_terminate_pid() -> None:
    """Imported AND used: the grace argument of its ``terminate_pid`` call is the name it imported from the home."""
    tree = ast.parse((repo_root() / "autobot-backend/llc/adapters/process_adapter.py").read_text(encoding="utf-8"))
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess_base"
        for alias in node.names
        if alias.name == "SIGTERM_GRACE_SECONDS"
    }
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "terminate_pid"]
    assert imported and calls, "process_adapter no longer imports the home constant or calls terminate_pid"
    assert all(isinstance(c.args[1], ast.Name) and c.args[1].id in imported for c in calls)


def test_the_keyword_this_guard_reads_is_terminate_pids_real_parameter() -> None:
    assert _grace_param() == "grace_seconds"


@pytest.mark.parametrize(
    "source",
    [
        "_SIGTERM_GRACE_SECONDS = 5\n",
        "_SIGTERM_GRACE_SECONDS += 5\n",
        "A_SIGTERM_GRACE, B = 5, 10\n",
        "B, A_SIGTERM_GRACE = SIGTERM_GRACE_SECONDS, 5\n",
        "A_SIGTERM_GRACE, B = pair = 5, 10\n",
        "A_SIGTERM_GRACE, *rest = 5, 6, 7\n",
        "self.sigterm_grace_seconds = 5\n",
        "LOCAL_SIGTERM_GRACE: int = 5\n",
    ],
)
def test_each_restated_literal_shape_is_flagged(source: str) -> None:
    assert copies(source, "autobot-backend/llc/adapters/process_adapter.py")


def test_a_literal_grace_passed_to_terminate_pid_is_flagged() -> None:
    assert copies("async def f():\n    await terminate_pid(pid, 5, 'X', t)\n", "autobot-backend/llc/x.py")
    assert copies(
        "async def f():\n    await s.terminate_pid(pid, grace_seconds=7, log_name='X', expected_create_time=t)\n", "x"
    )


def test_the_home_may_define_it_and_an_import_is_not_a_copy() -> None:
    assert not copies("SIGTERM_GRACE_SECONDS = 10\n", _HOME)
    assert not copies(
        "from .subprocess_base import SIGTERM_GRACE_SECONDS\nawait terminate_pid(p, SIGTERM_GRACE_SECONDS, 'X', t)\n",
        "autobot-backend/llc/adapters/process_adapter.py",
    )
    # Unpacking pairs each name with its own value: the grace name gets the constant, OTHER the literal (#19660).
    assert not copies("OTHER, LOCAL_SIGTERM_GRACE = 5, SIGTERM_GRACE_SECONDS\n", "autobot-backend/llc/x.py")
