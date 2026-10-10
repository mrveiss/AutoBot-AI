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

The detector reads the syntax tree: a call whose callee attribute is `check_access`. The
files below are the only ones allowed to make that call.
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


def _calls_check_access(source: str) -> bool:
    """True when `source` calls `<something>.check_access(...)`."""
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "check_access"
        for n in ast.walk(ast.parse(source))
    )


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
def _callers() -> tuple[tuple[str, ...], int]:
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "check_access" not in source:
            continue
        parsed += 1
        if _calls_check_access(source):
            found.append(rel)
    return tuple(sorted(found)), parsed


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("an attribute call", "await mgr.check_access(fact_id=f)\n", True),
        ("a chained call", "await kb.ownership_manager.check_access(f, u, m)\n", True),
        ("a comment naming it", "# mgr.check_access(f)\nx = 1\n", False),
        ("a string naming it", 's = "mgr.check_access(f)"\n', False),
        ("the helper call", "await can_read_fact(mgr, f, m, user)\n", False),
    ],
)
def test_the_matcher_tells_a_call_from_a_mention(label: str, source: str, expected: bool) -> None:
    assert _calls_check_access(source) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    _, parsed = _callers()
    assert parsed >= len(_ALLOWED), f"parsed {parsed} files mentioning check_access"


def test_only_the_allowed_files_call_check_access() -> None:
    callers, _ = _callers()
    assert set(callers) == set(_ALLOWED), (
        f"#18184: {sorted(set(callers) ^ set(_ALLOWED))} differ from the allowed check_access callers. "
        "Call knowledge.search_filters.can_read_fact / authorize_fact_read instead of a second inline "
        "check; drop an _ALLOWED entry that no longer calls it."
    )
