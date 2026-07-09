# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the shared Alembic guard helpers (#10027).

The inspector-backed guards run against an in-memory SQLite database under a
real ``Operations.context`` so ``op.get_bind()`` resolves exactly as it does
inside a version script. ``ensure_pg_enum``/``drop_pg_enum`` are
Postgres-only (``CREATE TYPE``) and are exercised by the fresh-database
schema verification instead (see PR evidence and the #10002 migration gate).
"""

import ast
from pathlib import Path

import pytest

# Real alembic required: the backend conftest stubs alembic with a MagicMock
# when it is not installed, which cannot drive an Operations context.
_alembic_migration = pytest.importorskip("alembic.migration")
_alembic_operations = pytest.importorskip("alembic.operations")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from migrations.guards import (  # noqa: E402
    existing_columns,
    has_column,
    has_index,
    has_table,
    pg_enum,
)

MigrationContext = _alembic_migration.MigrationContext
Operations = _alembic_operations.Operations

pytestmark = pytest.mark.migration_gate


@pytest.fixture()
def op_context():
    """An installed ``op`` proxy bound to an in-memory SQLite schema."""
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(sa.text("CREATE INDEX ix_sample_name ON sample (name)"))
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            yield


class TestInspectorGuards:
    def test_has_table(self, op_context) -> None:
        assert has_table("sample") is True
        assert has_table("absent") is False

    def test_has_column(self, op_context) -> None:
        assert has_column("sample", "name") is True
        assert has_column("sample", "absent") is False
        assert has_column("absent", "name") is False

    def test_existing_columns(self, op_context) -> None:
        assert existing_columns("sample") == {"id", "name"}
        assert existing_columns("absent") == set()

    def test_has_index(self, op_context) -> None:
        assert has_index("sample", "ix_sample_name") is True
        assert has_index("sample", "ix_absent") is False
        assert has_index("absent", "ix_sample_name") is False


class TestPgEnum:
    def test_reference_shape(self) -> None:
        enum_type = pg_enum("approvalstatus", "pending", "approved")
        assert isinstance(enum_type, postgresql.ENUM)
        assert enum_type.name == "approvalstatus"
        assert list(enum_type.enums) == ["pending", "approved"]

    def test_never_auto_created(self) -> None:
        # create_type=False is the entire point: op.create_table must not
        # emit CREATE TYPE for a column that references this type (#9759).
        assert pg_enum("boardtype", "kanban", "sprint").create_type is False


# ---------------------------------------------------------------------------
# #11346 — migration lint: no generic sa.Enum() (enforce pg_enum)
# ---------------------------------------------------------------------------

_MIGRATIONS_VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def _generic_enum_call_lines(path: Path) -> list[int]:
    """Line numbers of generic ``sa.Enum(...)`` / ``sqlalchemy.Enum(...)`` calls.

    AST-based so comments/docstrings mentioning ``sa.Enum(`` (the guard files
    explain *why* they avoid it) don't false-positive.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Enum"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in ("sa", "sqlalchemy")
        ):
            hits.append(node.lineno)
    return hits


def test_migrations_use_pg_enum_not_generic_sa_enum() -> None:
    """Alembic migrations must build Postgres enums via ``migrations.guards.pg_enum``,
    never generic ``sa.Enum()`` (#11337/#11338/#11346).

    ``sa.Enum(..., create_type=False)`` is **silently ignored** by SQLAlchemy 2.0
    (only ``postgresql.ENUM`` honours ``create_type``), so ``op.create_table``
    re-emits ``CREATE TYPE`` for the column → ``DuplicateObjectError`` when the type
    already exists (partially-applied DB). ``pg_enum()`` returns a ``postgresql.ENUM``
    that ``op.create_table`` never auto-creates; pair it with ``ensure_pg_enum``.
    """
    assert _MIGRATIONS_VERSIONS.is_dir(), f"migrations/versions not found at {_MIGRATIONS_VERSIONS}"
    violations: list[str] = []
    for f in sorted(_MIGRATIONS_VERSIONS.glob("*.py")):
        violations += [f"{f.name}:{line}" for line in _generic_enum_call_lines(f)]
    assert not violations, (
        "Migrations must use migrations.guards.pg_enum(), not generic sa.Enum() — "
        "create_type=False is ignored on the generic Enum, causing duplicate CREATE TYPE. "
        f"Offending call sites: {violations}"
    )
