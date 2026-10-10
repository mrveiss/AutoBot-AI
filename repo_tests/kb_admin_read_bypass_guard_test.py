# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Only explicit read APIs may pass the admin bypass to the access checks (#16662).

Owner decision on #16654: an admin can read any fact through the explicit search and
read APIs, but an admin's chat gets NO bypass. So the ``is_admin`` input of
``check_access``, ``filter_search_results_by_permission`` and
``augment_search_request_with_permissions`` may be passed only from
:data:`EXPLICIT_READ_APIS`, plus the helper that forwards it
(:data:`PASS_THROUGH`). Any other production call that passes it fails here, and that
includes every chat, agent, RAG and grounding path.

**Scope.** Git-tracked production Python under ``autobot-backend/`` and
``autobot_shared/``, tests excluded. :data:`REACH` floors what the sweep read, so an empty
enumeration fails instead of passing. A call counts when it is ``<x>.check_access(...)``,
``check_access(...)``, or the same for the other :data:`GATED_HELPERS`, and it
passes an ``is_admin=`` keyword. It cannot see the flag passed positionally, through
``**kwargs``, or through a renamed alias; and it is file-granular, so a chat-like path that
reaches an explicit API's function indirectly is invisible to it. ``/rag/scoped`` once did
exactly that (it called the ``/scoped`` route), and is now pinned by a behavioural test instead
(``api/kb_explicit_admin_reads_16662_test.py``). Those are the declared blind spots, and the
known-positive test below shows that the keyword form is detected.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()
SCAN_ROOTS = ("autobot-backend/", "autobot_shared/")
GATED_HELPERS = frozenset(
    {"check_access", "filter_search_results_by_permission", "augment_search_request_with_permissions"}
)

#: Explicit, admin-aware read APIs (owner decision on #16654). Adding a file here needs
#: that decision, not convenience: a chat or grounding path must never appear.
#: knowledge_search.py and knowledge_search_aggregator.py added 2026-09-14 (#16745): the
#: owner ruled the canonical search and multi-source aggregation routes are themselves
#: explicit, caller-driven read APIs -- not a chat/agent/RAG hop -- so #16691's is_admin
#: bypass there is the intended #16654 behaviour, same category as the three files below.
EXPLICIT_READ_APIS = frozenset(
    {
        "autobot-backend/api/knowledge_ownership.py",
        "autobot-backend/api/knowledge_collaboration.py",
        "autobot-backend/api/knowledge_search_scoped.py",
        "autobot-backend/api/knowledge_search.py",
        "autobot-backend/api/knowledge_search_aggregator.py",
    }
)
#: The helper that forwards its own ``is_admin`` parameter to ``check_access``.
PASS_THROUGH = frozenset({"autobot-backend/knowledge/search_filters.py"})
#: The canonical per-fact read entries (#18184). They derive ``is_admin`` from ``current_user``
#: (or take it explicitly) and forward it to ``check_access``, so calling one is an admin-aware read.
#: Accepted only while the helper's own body in :data:`HELPER_HOME` passes ``is_admin`` (asserted).
CANONICAL_READ_HELPERS = frozenset({"can_read_fact", "authorize_fact_read"})
HELPER_HOME = "autobot-backend/knowledge/search_filters.py"
#: Explicit read APIs plus the caller-driven pipeline route that reads one document by id (#18184).
#: Adding a file needs the same owner decision as :data:`EXPLICIT_READ_APIS`.
HELPER_CALLERS = EXPLICIT_READ_APIS | {"autobot-backend/api/knowledge_graph_routes.py"}


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


def _production_files(root: Path) -> list[str]:
    """The production Python files under *root* this guard reads; ``[]`` for an empty tree."""
    try:
        tracked = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []  # the floor then refuses the empty sweep with ReachFloorError, as it should
    return [rel for rel in tracked if _is_production(rel)]


#: Bound at the 2567 files measured when the floor was added.
REACH = declare(
    "kb-admin-read-bypass",
    discover=_production_files,
    floor=2567,
    growth=200,
    skips=0,
    # The scope moves from prose to data (#17844): `declare` renders the same sentence from
    # `roots`, so the string cannot drift from the tuple `verify_scope` reads.
    what="production python files",
    roots=SCAN_ROOTS,
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


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def canonical_helper_calls(source: str) -> list[int]:
    """Line numbers of calls to the canonical admin-aware fact-read helpers in *source*."""
    return [
        n.lineno
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call) and _call_name(n) in CANONICAL_READ_HELPERS
    ]


def helper_forwards_admin(source: str, helper: str = "can_read_fact") -> bool:
    """Whether *helper*'s body in *source* passes ``is_admin=`` to ``check_access``."""
    for fn in ast.walk(ast.parse(source)):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == helper:
            return any(
                isinstance(n, ast.Call)
                and _call_name(n) == "check_access"
                and any(k.arg == "is_admin" for k in n.keywords)
                for n in ast.walk(fn)
            )
    return False


@lru_cache(maxsize=1)
def _helper_scan() -> dict[str, list[int]]:
    found = {}
    read = 0
    for rel in REACH.examined(REPO_ROOT):
        lines = canonical_helper_calls((REPO_ROOT / rel).read_text(encoding="utf-8"))
        read += 1
        if lines:
            found[rel] = lines
    REACH.completed(read)  # the helper sweep is held to the same declared floor as the bypass sweep
    return found


@lru_cache(maxsize=1)
def _scan() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    read = 0
    for rel in REACH.examined(REPO_ROOT):
        lines = admin_bypass_calls((REPO_ROOT / rel).read_text(encoding="utf-8"))
        read += 1
        if lines:
            found[rel] = lines
    REACH.completed(read)
    return found


def test_only_explicit_read_apis_pass_the_admin_bypass():
    found = _scan()
    offenders = {rel: lines for rel, lines in found.items() if rel not in EXPLICIT_READ_APIS | PASS_THROUGH}
    assert not offenders, (
        "is_admin passed to an access check outside the explicit read APIs (#16662; owner decision on "
        f"#16654: an admin's chat gets no bypass): {offenders}"
    )


def test_every_explicit_read_api_passes_the_admin_input():
    """The owner decision is wired: each explicit read API reads as an admin."""
    found = set(_scan())
    if helper_forwards_admin((REPO_ROOT / HELPER_HOME).read_text(encoding="utf-8")):
        found |= set(_helper_scan())  # a canonical helper call is an admin-aware read (#18184)
    assert EXPLICIT_READ_APIS <= found, f"explicit read APIs not passing is_admin: {sorted(EXPLICIT_READ_APIS - found)}"


def test_the_canonical_helpers_forward_is_admin_and_only_allowed_files_call_them():
    """The allowance cannot rot: the helper passes is_admin to check_access, and chat paths do not call it."""
    src = (REPO_ROOT / HELPER_HOME).read_text(encoding="utf-8")
    for helper in ("can_read_fact",):
        assert helper_forwards_admin(src, helper), f"{helper} no longer passes is_admin to check_access"
    callers = set(_helper_scan()) - {HELPER_HOME}
    assert (
        callers <= HELPER_CALLERS
    ), f"canonical admin-aware read helper called outside the explicit read APIs: {sorted(callers - HELPER_CALLERS)}"


def test_helper_contrast_cases():
    """Direct check_access without is_admin fails; a helper call passes; a helper dropping is_admin fails."""
    direct = "async def r(m, f, u):\n    return await m.check_access(f, u, {})\n"
    assert admin_bypass_calls(direct) == [] and canonical_helper_calls(direct) == []  # reads as non-admin: no credit
    assert canonical_helper_calls("async def r(m, f, md, u):\n    return await can_read_fact(m, f, md, u)\n") == [2]
    good = "async def can_read_fact(m, f, md, u):\n    return await m.check_access(f, is_admin=True)\n"
    bad = "async def can_read_fact(m, f, md, u):\n    return await m.check_access(f, u)\n"
    assert helper_forwards_admin(good) and not helper_forwards_admin(bad)


def test_a_chat_path_passing_the_bypass_is_detected():
    """Known positive: the detector fires on the keyword form it claims to see."""
    src = "async def ground(kb, u, m):\n    return await kb.ownership_manager.check_access('f', u, m, is_admin=True)\n"
    assert admin_bypass_calls(src) == [2]
    assert admin_bypass_calls("async def ok(kb, u, m):\n    return await kb.check_access('f', u, m)\n") == []
