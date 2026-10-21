# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Service-row upsert has ONE home, ``services/service_upsert.py`` (#19021).

Static (AST, stdlib only -- no SLM module is imported). Before #19021 two copies carried the same
lookup/create-or-update and each had to remember the unit-name guard (#19005). Pinned here:

* exactly one function in the backend both looks a Service up by (node_id, service_name) AND adds a
  new row -- the core; a second one is a fork;
* the core runs the guard BEFORE the lookup;
* each caller delegates to the core and keeps no query or guard of its own.

Contrast fixtures prove the detector sees a fork and ignores a lookup-only update.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SLM_ROOT = Path(__file__).resolve().parent.parent
_CORE = "services/service_upsert.py"
# Known third copy, tracked in #19059; delete this entry when it moves onto the core -- the
# stale-entry check below fails until it is deleted.
_KNOWN_FORKS = {"services/service_orchestrator.py:_update_service_record"}
_FORK_FIXTURE = """
async def _upsert_service(db, node_id, name):
    r = await db.execute(select(Service).where(Service.node_id == node_id, Service.service_name == name))
    row = r.scalar_one_or_none()
    if not row:
        db.add(Service(node_id=node_id, service_name=name))
"""
_LOOKUP_ONLY_FIXTURE = """
async def start_service(db, node_id, name):
    r = await db.execute(select(Service).where(Service.node_id == node_id, Service.service_name == name))
    r.scalar_one_or_none().status = "running"
"""


def _functions(tree: ast.AST):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _attrs(fn: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}


def _calls(fn: ast.AST) -> set[str]:
    names = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            names.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    return names


def _has_core_lookup(fn: ast.AST) -> bool:
    """select(Service) filtered on BOTH Service.node_id and Service.service_name."""
    selects_service = any(
        isinstance(n, ast.Call)
        and getattr(n.func, "id", "") == "select"
        and any(getattr(a, "id", "") == "Service" for a in n.args)
        for n in ast.walk(fn)
    )
    return selects_service and {"node_id", "service_name"} <= _attrs(fn)


#: Receivers that are an ORM session; ``set.add`` / ``list``-style ``.add`` on anything else is not a row write.
_SESSION_NAMES = frozenset({"db", "session"})


def _adds_to_session(fn: ast.AST) -> bool:
    """A ``db.add(...)`` / ``session.add(...)`` / ``self.session.add(...)`` call, not any ``.add``."""
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add":
            recv = n.func.value
            name = recv.id if isinstance(recv, ast.Name) else getattr(recv, "attr", "")
            if name in _SESSION_NAMES:
                return True
    return False


def _is_upsert_shaped(fn: ast.AST) -> bool:
    return _has_core_lookup(fn) and _adds_to_session(fn)


def test_a_set_add_is_not_a_row_write() -> None:
    """Contrast for the shape: the lookup plus ``seen.add`` is not an upsert; plus ``db.add`` is."""
    lookup = "select(Service).where(Service.node_id == n, Service.service_name == s)"
    not_upsert = ast.parse(f"async def f(db, n, s):\n    q = {lookup}\n    seen = set()\n    seen.add(s)\n")
    upsert = ast.parse(f"async def f(db, n, s):\n    q = {lookup}\n    db.add(object())\n")
    assert not _is_upsert_shaped(not_upsert.body[0])
    assert _is_upsert_shaped(upsert.body[0])


def _sources() -> dict[str, ast.AST]:
    out = {}
    for path in _SLM_ROOT.rglob("*.py"):
        rel = path.relative_to(_SLM_ROOT).as_posix()
        if rel.endswith("_test.py") or rel.startswith(("tests/", "migrations/", "venv/", ".venv/")) or "/test_" in rel:
            continue
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        out[rel] = ast.parse(path.read_text(encoding="utf-8"))
    return out


def _find(tree: ast.AST, name: str) -> ast.AST:
    (fn,) = [f for f in _functions(tree) if f.name == name]
    return fn


def test_detector_sees_a_fork_and_ignores_a_lookup_only_update():
    assert _is_upsert_shaped(_functions(ast.parse(_FORK_FIXTURE))[0])
    assert not _is_upsert_shaped(_functions(ast.parse(_LOOKUP_ONLY_FIXTURE))[0])


def test_exactly_one_function_in_the_backend_is_upsert_shaped_and_it_is_the_core():
    all_homes = sorted(
        f"{rel}:{fn.name}" for rel, tree in _sources().items() for fn in _functions(tree) if _is_upsert_shaped(fn)
    )
    stale = sorted(_KNOWN_FORKS - set(all_homes))
    assert not stale, f"_KNOWN_FORKS entries are gone or no longer upsert-shaped; remove them (#19059): {stale}"
    homes = [h for h in all_homes if h not in _KNOWN_FORKS]
    assert homes == [f"{_CORE}:upsert_service"], f"a second Service upsert is a fork of the core (#19021): {homes}"


def test_the_core_runs_the_unit_name_guard_before_the_lookup():
    core = _find(_sources()[_CORE], "upsert_service")
    guard, lookup = None, None
    for n in ast.walk(core):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "discovered_unit_name_ok":
            guard = n.lineno
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "select":
            lookup = n.lineno
    assert guard is not None and lookup is not None and guard < lookup


def test_both_callers_delegate_and_keep_no_query_or_guard_of_their_own():
    sources = _sources()
    callers = {
        "api/services.py": _find(sources["api/services.py"], "_upsert_service"),
        "services/reconciler.py": _find(sources["services/reconciler.py"], "_upsert_service"),
    }
    for rel, fn in callers.items():
        calls = _calls(fn)
        assert "upsert_service" in calls, f"{rel} must call the shared upsert"
        assert "discovered_unit_name_ok" not in calls, f"{rel} must leave the guard to the core"
        assert "select" not in calls, f"{rel} must not re-implement the lookup"
