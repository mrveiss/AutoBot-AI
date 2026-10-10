# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One per-fact read authorization (#18184).

The decision "may this caller read this fact" -- resolve the caller's user, org, groups and
admin role, then ask the ownership manager -- lives once, in `knowledge/search_filters.py`
(`can_read_fact`, `authorize_fact_read`). `knowledge_collaboration` and `run_pipeline` both
call it. A second inline `<x>.check_access(...)` sequence is a security-path fork: it can
drift on the admin rule, on the group list, or on the 403/404 split.

The detector reads the syntax tree: any code reference to the attribute `check_access` (called,
aliased, passed to `partial`, or fetched with `getattr`). The files below are the only ones
allowed to reference it.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ALLOWED = {
    "autobot-backend/knowledge/search_filters.py": "the canonical helper, and the bulk search-result filter",
    "autobot-backend/knowledge/ownership.py": "defines check_access; its own bulk reader calls it",
}


def _references_check_access(source: str) -> bool:
    """True when `source` references `check_access` as code, called or not.

    Flags any Load-context `<x>.check_access` attribute (a call, an alias, a `partial` argument)
    and any `getattr(<x>, "check_access")` with a constant name. Strings and comments are not code.
    """
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.Attribute) and n.attr == "check_access" and isinstance(n.ctx, ast.Load):
            return True
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "getattr"
            and len(n.args) >= 2
            and isinstance(n.args[1], ast.Constant)
            and n.args[1].value == "check_access"
        ):
            return True
    return False


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
    "fact-read-authorization-scan",
    discover=_source_population,
    # Mid-window from REACH.window(): population 2997, skips 0, growth 300 -> (2697, 2997, 2847).
    floor=2847,
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _callers() -> tuple[tuple[str, ...], int, int]:
    found: list[str] = []
    parsed = 0
    read = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        read += 1
        if "check_access" not in source:
            continue
        parsed += 1
        if _references_check_access(source):
            found.append(rel)
    REACH.completed(read)
    return tuple(sorted(found)), parsed, read


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("an attribute call", "await mgr.check_access(fact_id=f)\n", True),
        ("a chained call", "await kb.ownership_manager.check_access(f, u, m)\n", True),
        ("a bare attribute alias", "ca = mgr.check_access\nawait ca(f)\n", True),
        ("a getattr fetch", 'await getattr(mgr, "check_access")(f)\n', True),
        ("a partial argument", "p = functools.partial(mgr.check_access, f)\n", True),
        ("a store to the attribute", "mgr.check_access = None\n", False),
        ("a getattr of another name", 'getattr(mgr, "other")\n', False),
        ("a comment naming it", "# mgr.check_access(f)\nx = 1\n", False),
        ("a string naming it", 's = "mgr.check_access(f)"\n', False),
        ("the helper call", "await can_read_fact(mgr, f, m, user)\n", False),
    ],
)
def test_the_matcher_tells_a_reference_from_a_mention(label: str, source: str, expected: bool) -> None:
    assert _references_check_access(source) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    _, parsed, read = _callers()
    assert read >= REACH.floor, f"read {read} files, below the declared floor {REACH.floor}"
    assert parsed >= len(_ALLOWED), f"parsed {parsed} files mentioning check_access"


def test_only_the_allowed_files_call_check_access() -> None:
    callers, _, _ = _callers()
    assert set(callers) == set(_ALLOWED), (
        f"#18184: {sorted(set(callers) ^ set(_ALLOWED))} differ from the allowed check_access callers. "
        "Call knowledge.search_filters.can_read_fact / authorize_fact_read instead of a second inline "
        "check; drop an _ALLOWED entry that no longer calls it."
    )
