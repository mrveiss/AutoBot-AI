# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``lazy_singleton(X)`` is a factory: build it once at module level (#20889).

Calling or attribute-accessing the result in the same expression
(``lazy_singleton(X)()``, ``lazy_singleton(X).attr``) either uses a function
as if it were the instance or builds a fresh factory, and so a fresh instance,
per call. Both are defects; this guard finds them in every tracked Python file.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

_FACTORIES = {"lazy_singleton", "async_lazy_singleton"}
_ROOT = Path(__file__).resolve().parent.parent


def _is_factory_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    return name in _FACTORIES


def inline_uses(source: str) -> list[int]:
    """Line numbers where a factory call is itself called or attribute-accessed."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _is_factory_call(node.func):
            hits.append(node.lineno)
        elif isinstance(node, ast.Attribute) and _is_factory_call(node.value):
            hits.append(node.lineno)
    return sorted(hits)


def _tracked_python_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=_ROOT,
        env=scrubbed_git_env(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    return [_ROOT / p for p in out if p]


def test_control_strings_are_detected():
    """The detector must flag the bad shapes and pass the good ones."""
    assert inline_uses("x = lazy_singleton(Svc)()") == [1]
    assert inline_uses("x = lazy_singleton(Svc).attr") == [1]
    assert inline_uses("x = await async_lazy_singleton(Svc)()") == [1]
    assert inline_uses("x = mod.lazy_singleton(Svc)()") == [1]
    assert inline_uses("get_svc = lazy_singleton(Svc)\nx = get_svc()") == []
    assert inline_uses("get_svc = lazy_singleton(lambda: Svc())") == []


def test_no_inline_lazy_singleton_use():
    offenders = []
    for path in _tracked_python_files():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "lazy_singleton" not in source:
            continue
        try:
            lines = inline_uses(source)
        except SyntaxError:
            continue
        offenders += [f"{path.relative_to(_ROOT)}:{n}" for n in lines]
    assert not offenders, "lazy_singleton(...) used inline; build the factory once at module level: " + ", ".join(
        offenders
    )
