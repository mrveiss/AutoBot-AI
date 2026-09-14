# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Only explicit read APIs may pass the admin bypass to the access checks (#16662).

Owner decision on #16654: an admin can read any fact through the explicit search and
read APIs, but an admin's chat gets NO bypass. So the ``is_admin`` input of
``check_access`` and ``filter_search_results_by_permission`` may be passed only from
:data:`EXPLICIT_READ_APIS`, plus the helper that forwards it
(:data:`PASS_THROUGH`). Any other production call that passes it fails here, and that
includes every chat, agent, RAG and grounding path.

**Scope.** Git-tracked production Python under ``autobot-backend/`` and
``autobot_shared/``, tests excluded. A call counts when it is ``<x>.check_access(...)``,
``check_access(...)``, or the same for ``filter_search_results_by_permission``, and it
passes an ``is_admin=`` keyword. It cannot see the flag passed positionally, through
``**kwargs``, or through a renamed alias. Those are the declared blind spots, and the
known-positive test below shows that the keyword form is detected.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()
SCAN_ROOTS = ("autobot-backend/", "autobot_shared/")
GATED_HELPERS = frozenset({"check_access", "filter_search_results_by_permission"})

#: Explicit, admin-aware read APIs (owner decision on #16654). Adding a file here needs
#: that decision, not convenience: a chat or grounding path must never appear.
EXPLICIT_READ_APIS = frozenset(
    {
        "autobot-backend/api/knowledge_ownership.py",
        "autobot-backend/api/knowledge_collaboration.py",
        "autobot-backend/api/knowledge_search_scoped.py",
    }
)
#: The helper that forwards its own ``is_admin`` parameter to ``check_access``.
PASS_THROUGH = frozenset({"autobot-backend/knowledge/search_filters.py"})


def _is_production(rel: str) -> bool:
    name = Path(rel).name
    return (
        rel.startswith(SCAN_ROOTS)
        and rel.endswith(".py")
        and not name.startswith("test_")
        and not name.endswith("_test.py")
        and name != "conftest.py"
        and "/tests/" not in rel
    )


def admin_bypass_calls(source: str) -> list[int]:
    """Line numbers of gated-helper calls in *source* that pass ``is_admin=``."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in GATED_HELPERS and any(kw.arg == "is_admin" for kw in node.keywords):
            lines.append(node.lineno)
    return lines


@lru_cache(maxsize=1)
def _scan() -> tuple[dict[str, list[int]], int]:
    found: dict[str, list[int]] = {}
    scanned = 0
    for rel in tracked_paths(REPO_ROOT, "*.py"):
        if not _is_production(rel):
            continue
        scanned += 1
        lines = admin_bypass_calls((REPO_ROOT / rel).read_text(encoding="utf-8"))
        if lines:
            found[rel] = lines
    return found, scanned


def test_only_explicit_read_apis_pass_the_admin_bypass():
    found, _ = _scan()
    offenders = {rel: lines for rel, lines in found.items() if rel not in EXPLICIT_READ_APIS | PASS_THROUGH}
    assert not offenders, (
        "is_admin passed to an access check outside the explicit read APIs (#16662; owner decision on "
        f"#16654: an admin's chat gets no bypass): {offenders}"
    )


def test_the_scan_reached_the_admin_aware_call_sites():
    """Not vacuous: the scan found at least one admin-aware call site it exists to bound."""
    found, scanned = _scan()
    assert scanned > 1000, f"only {scanned} production files scanned"
    assert set(found) & (EXPLICIT_READ_APIS | PASS_THROUGH), f"no admin-aware call site found: {sorted(found)}"


def test_a_chat_path_passing_the_bypass_is_detected():
    """Known positive: the detector fires on the keyword form it claims to see."""
    src = "async def ground(kb, u, m):\n    return await kb.ownership_manager.check_access('f', u, m, is_admin=True)\n"
    assert admin_bypass_calls(src) == [2]
    assert admin_bypass_calls("async def ok(kb, u, m):\n    return await kb.check_access('f', u, m)\n") == []
