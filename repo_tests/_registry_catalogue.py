# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the ``RouterConfig`` catalogue lives, resolved rather than named (#16375).

Two guards parsed ``autobot-backend/api/registry.py`` by hardcoded path. #16375
split the catalogue out to ``api/registry_catalog.py`` -- that module had grown
to 607 lines against a frozen 604 ceiling, and gating its router needed the
room -- and both guards went from parsing 31 entries to parsing **zero**.

Neither reported a problem with the registry. They reported their own
non-vacuity floors:

    only 0 RouterConfig entries parsed out of registry.py; the agreement
    assertions below would range over almost nothing

That floor is the only reason the move did not merge with two guards silently
checking an empty set. Pointing them at the new filename would restore the
checks and keep the brittleness, one move later. So the catalogue is found by
**what it declares**, and a guard asks this module instead of naming a file.

One parser, shared: a second AST reader of the same entries would drift from
this one exactly as the two ``include_router`` regexes drifted before #12985
consolidated them.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path


def _declares_router_config(source: str) -> bool:
    """True when *source* CALLS ``RouterConfig(...)``.

    Parsed, not searched: ``api/registry.py`` still imports the name and still
    annotates with it after the split, and a substring test would therefore keep
    finding the old file and reporting zero entries from it.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.Call) and getattr(node.func, "id", None) == "RouterConfig" for node in ast.walk(tree)
    )


@lru_cache(maxsize=None)
def catalogue_files(backend_dir: Path) -> tuple[Path, ...]:
    """Every non-test module under ``api/`` that declares ``RouterConfig`` entries."""
    api_dir = backend_dir / "api"
    return tuple(
        path
        for path in sorted(api_dir.rglob("*.py"))
        if not path.name.endswith("_test.py") and _declares_router_config(path.read_text(encoding="utf-8"))
    )


def _string_literal(node: ast.AST | None) -> str | None:
    """The value of a string-literal argument, or ``None`` if it is computed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def entries_in_source(source: str, *, origin: str = "<source>") -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """``((module_path, prefix), ...)`` and a description of every entry that could not be read.

    The two are returned together on purpose (review). An earlier version
    ``continue``d past an entry whose ``module_path`` or ``prefix`` was computed
    rather than literal, which meant the agreement guard could clear its 20-entry
    floor **while omitting that router from the comparison**. A floor defends
    against *zero*; it says nothing about a silently dropped subset, and a
    catalogue entry a guard cannot compare is a hole, not an absence -- the same
    shape this guard exists to catch, one level in.

    Callers assert the second element is empty. If a computed entry is ever
    legitimate it needs an explicit allowlist carrying a reason, not a skip.

    Prefixes are right-stripped of ``/`` so both sides of an agreement check are
    compared in the same coordinates.
    """
    found: list[tuple[str, str]] = []
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "RouterConfig"):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        module = _string_literal(kwargs.get("module_path"))
        prefix = _string_literal(kwargs.get("prefix"))
        if module is None or prefix is None:
            missing = [name for name, value in (("module_path", module), ("prefix", prefix)) if value is None]
            problems.append(f"{origin}:{node.lineno} RouterConfig with non-literal {' and '.join(missing)}")
            continue
        found.append((module, prefix.rstrip("/")))
    return tuple(found), tuple(problems)


@lru_cache(maxsize=None)
def _read_catalogue(backend_dir: Path) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    found: list[tuple[str, str]] = []
    problems: list[str] = []
    for path in catalogue_files(backend_dir):
        entries, bad = entries_in_source(path.read_text(encoding="utf-8"), origin=path.name)
        found.extend(entries)
        problems.extend(bad)
    return tuple(found), tuple(problems)


def catalogue_entries(backend_dir: Path) -> tuple[tuple[str, str], ...]:
    """Every ``(module_path, prefix)`` the catalogue declares as literals."""
    return _read_catalogue(backend_dir)[0]


def unreadable_catalogue_entries(backend_dir: Path) -> tuple[str, ...]:
    """Catalogue entries a guard cannot compare. Callers must fail when non-empty."""
    return _read_catalogue(backend_dir)[1]
