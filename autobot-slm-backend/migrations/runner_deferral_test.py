# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A migration that did nothing must not be recorded as done (#14300).

Observed live: ``column audit_logs.updated_at does not exist`` raised on an HTTP
request, while ``add_role_permission_audit_log_timestamps`` — the migration
written for exactly that column, and registered in the runner — sat marked
applied.

Two independent holes produced that, and both are the same shape: an absence
read as a success.

1. ``add_column_if_not_exists`` skips when the table is missing (#9785, correct
   in itself — the alternative is an ALTER that errors). The runner then marked
   the migration applied, so the skip became permanent. ``audit_logs`` lives in
   the user-management database while the runner connects to one URL, so the
   table is *never* there and the column could never arrive.

2. ``run_all_migrations``'s exception handler recorded the error only when
   ``results == []``. An exception after one success therefore left a list of
   nothing but successes, and the startup caller — which raises on any failure
   entry — saw a clean run and continued with the schema half migrated.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    """Load a migrations module standalone — the package pulls in psycopg2 users."""
    spec = importlib.util.spec_from_file_location(name, _BACKEND_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


_utils = _load("_mig_utils_14300", "migrations/utils.py")


class _Cursor:
    """Minimal cursor matching the two queries the helpers actually issue.

    CI caught this standing in badly: ``table_exists`` runs
    ``SELECT EXISTS (...)`` and reads ``cursor.fetchone()[0]`` unconditionally,
    so a *missing* table is the row ``(False,)`` — not the absence of a row.
    Returning ``None`` for "no rows" made every missing-table case raise
    ``TypeError: 'NoneType' object is not subscriptable`` instead of exercising
    the deferral path this file exists to test.

    A fake that answers a question the real code never asks is worse than no
    fake: it fails for a reason the production code cannot produce.
    """

    def __init__(self, tables: dict[str, list[str]]):
        self._tables = tables
        self.executed: list[str] = []
        self._result: list = []

    def execute(self, sql, params=None):
        self.executed.append(sql)
        lowered = sql.lower()
        name = params[0] if params else ""
        if "information_schema.tables" in lowered:
            # SELECT EXISTS(...) always returns exactly one row: (bool,)
            self._result = [(name in self._tables,)]
        elif "information_schema.columns" in lowered:
            self._result = [(c,) for c in self._tables.get(name, [])]
        else:
            self._result = []

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else None


@pytest.fixture(autouse=True)
def _clear_deferrals():
    _utils.reset_deferrals()
    yield
    _utils.reset_deferrals()


def test_a_missing_table_is_recorded_as_a_deferral():
    """The signal the runner needs, which previously existed only as a DEBUG line."""
    cursor = _Cursor({"other_table": ["id"]})

    added = _utils.add_column_if_not_exists(cursor, "audit_logs", "updated_at", "TIMESTAMP")

    assert added is False
    assert _utils.deferrals() == ["audit_logs.updated_at"]
    assert not [sql for sql in cursor.executed if "ALTER TABLE" in sql], "must not ALTER a table that is absent"


def test_a_present_table_missing_the_column_is_altered_and_not_deferred():
    cursor = _Cursor({"audit_logs": ["id", "created_at"]})

    added = _utils.add_column_if_not_exists(cursor, "audit_logs", "updated_at", "TIMESTAMP")

    assert added is True
    assert _utils.deferrals() == []
    assert any("ALTER TABLE audit_logs ADD COLUMN updated_at" in sql for sql in cursor.executed)


def test_an_existing_column_is_neither_altered_nor_deferred():
    """The genuinely-idempotent case must stay silent — a deferral here would
    make every re-run refuse to mark the migration applied, forever."""
    cursor = _Cursor({"audit_logs": ["id", "updated_at"]})

    added = _utils.add_column_if_not_exists(cursor, "audit_logs", "updated_at", "TIMESTAMP")

    assert added is False
    assert _utils.deferrals() == []
    assert not [sql for sql in cursor.executed if "ALTER TABLE" in sql]


def test_deferrals_accumulate_across_calls_within_one_migration():
    """A migration touching three tables reports every one it could not reach."""
    cursor = _Cursor({})

    _utils.add_column_if_not_exists(cursor, "role_permissions", "created_at", "TIMESTAMP")
    _utils.add_column_if_not_exists(cursor, "role_permissions", "updated_at", "TIMESTAMP")
    _utils.add_column_if_not_exists(cursor, "audit_logs", "updated_at", "TIMESTAMP")

    assert _utils.deferrals() == [
        "role_permissions.created_at",
        "role_permissions.updated_at",
        "audit_logs.updated_at",
    ]


def test_reset_clears_between_migrations():
    """Without this the runner would attribute one migration's deferral to the next."""
    cursor = _Cursor({})
    _utils.add_column_if_not_exists(cursor, "audit_logs", "updated_at", "TIMESTAMP")
    assert _utils.deferrals()

    _utils.reset_deferrals()

    assert _utils.deferrals() == []


# --------------------------------------------------------------------------
# The runner's two rules, asserted structurally — importing runner.py needs
# psycopg2 and a live DSN, neither of which belongs in a unit test.
# --------------------------------------------------------------------------


def _runner_source() -> str:
    return (_BACKEND_ROOT / "migrations" / "runner.py").read_text(encoding="utf-8")


def test_a_deferred_migration_is_not_marked_applied():
    """The permanence half of the bug.

    Marking a migration applied when it skipped every operation is what turned
    a one-boot ordering problem into a column that could never arrive.
    """
    import ast

    tree = ast.parse(_runner_source())
    func = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "run_all_migrations"
    )
    called = {
        node.func.attr for node in ast.walk(func) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {node.func.id for node in ast.walk(func) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

    assert "reset_deferrals" in called, "the runner never clears deferrals, so they leak between migrations"
    assert "deferrals" in called, "the runner never reads the deferral record"

    # The `continue` must live in the branch that tested for deferrals, not
    # merely somewhere in the function. An earlier version of this assertion
    # accepted `"Continue" in ast.dump(func)` — a substring check over dumped
    # source, which is the shape this repo keeps getting bitten by: it would
    # pass on a `continue` in an unrelated loop while the deferral branch fell
    # straight through to mark_migration_applied.
    deferral_branches = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.If)
        and any(isinstance(inner, ast.Name) and inner.id == "deferred" for inner in ast.walk(node.test))
    ]
    assert deferral_branches, "no branch tests whether the migration deferred anything"
    assert any(
        isinstance(inner, ast.Continue) for branch in deferral_branches for inner in ast.walk(branch)
    ), "the deferral branch falls through to mark_migration_applied instead of skipping it"


def test_a_mid_run_exception_is_always_recorded():
    """The visibility half, asserted on structure rather than on source text.

    `if results == []` meant an exception after one success produced an
    all-successes list, and the startup caller raises only on a failure entry —
    so a half-migrated schema started cleanly.

    Review finding: the first version of this test matched raw substrings, so
    the identical bug rewritten as `if not results:` — or merely reformatted —
    would have passed it while reproducing the defect exactly. It now walks the
    handler and requires the append to be unconditional.
    """
    import ast

    func = next(
        node
        for node in ast.walk(ast.parse(_runner_source()))
        if isinstance(node, ast.FunctionDef) and node.name == "run_all_migrations"
    )
    handlers = [h for node in ast.walk(func) if isinstance(node, ast.Try) for h in node.handlers]
    recording = []
    for handler in handlers:
        appends = [
            n for n in ast.walk(handler) if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "append"
        ]
        if not appends:
            continue
        # every append must sit directly in the handler body, not inside an If
        gated = {
            id(n)
            for branch in ast.walk(handler)
            if isinstance(branch, ast.If)
            for n in ast.walk(branch)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "append"
        }
        recording.append(any(id(a) not in gated for a in appends))

    assert recording, "no except handler records anything into results"
    assert all(recording), "an except handler records the failure only conditionally (#14300)"
