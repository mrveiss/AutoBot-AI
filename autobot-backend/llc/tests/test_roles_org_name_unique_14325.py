# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``roles`` must be unique on ``(org_id, name)`` within a company (#14325).

The table carried no uniqueness at all, so one company could hold two roles of
the same name. Since #14221 hangs occupancy, workflow attachments and
permissions off a role, two identically named roles with different permission
sets are indistinguishable in any UI that lists them by name.

These tests pin the two properties that are easy to get subtly wrong:

* the index is **partial** — a plain ``UNIQUE(org_id, name)`` reads as though it
  forbids duplicate system-role names but does not, because Postgres treats
  NULLs as distinct and system roles carry ``org_id IS NULL``;
* the constraint exists on **both** provisioning paths — the migration and the
  model. A create_all-provisioned database would otherwise diverge from a
  migrated one, and only the migrated path would be protected.

Structural rather than behavioural: the constraint targets Postgres and the
partial predicate is dialect-specific, so asserting on the declared metadata is
what can run without a live database. The behaviour itself is exercised by the
migration gate against real Postgres.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_MIGRATION = (
    _REPO / "autobot-backend" / "migrations" / "versions" / "20260821_081_roles_org_name_unique.py"
)
_MODEL = _REPO / "autobot_shared" / "user_management" / "models" / "role.py"

INDEX_NAME = "uq_roles_org_id_name"
PREDICATE = "org_id IS NOT NULL"


@pytest.fixture(scope="module")
def migration_source() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def model_source() -> str:
    return _MODEL.read_text(encoding="utf-8")


def test_the_migration_exists_and_parses(migration_source: str) -> None:
    assert ast.parse(migration_source) is not None


def test_the_index_is_partial_not_a_plain_unique_constraint(migration_source: str) -> None:
    """The whole point: NULL org_id must stay outside the constraint."""
    assert PREDICATE in migration_source
    assert "postgresql_where" in migration_source
    assert "unique=True" in migration_source


def test_the_model_declares_the_same_partial_index(model_source: str) -> None:
    """create_all must produce the index too, or fresh databases are unprotected."""
    assert INDEX_NAME in model_source
    assert PREDICATE in model_source
    assert "__table_args__" in model_source


def test_the_model_and_migration_agree_on_the_index_name(
    migration_source: str, model_source: str
) -> None:
    """Two spellings would mean two indexes, and a migrated DB drifting from a fresh one."""
    assert INDEX_NAME in migration_source
    assert INDEX_NAME in model_source


def test_upgrade_scans_for_duplicates_before_creating_the_index(migration_source: str) -> None:
    """Order matters.

    Creating a unique index over duplicate rows fails with a Postgres error
    naming one arbitrary conflicting key, which says nothing about scale or
    shape. The scan must come first and report the full set.
    """
    tree = ast.parse(migration_source)
    upgrade = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )
    body = ast.dump(upgrade)

    scan_at = body.find("_DUPLICATE_SCAN")
    create_at = body.find("create_index")

    assert scan_at != -1, "upgrade must scan for existing duplicates"
    assert create_at != -1, "upgrade must create the index"
    assert scan_at < create_at, "the duplicate scan must run BEFORE the index is created"


def test_upgrade_refuses_rather_than_letting_postgres_fail(migration_source: str) -> None:
    """A found duplicate must raise with the offending groups, not fall through."""
    tree = ast.parse(migration_source)
    upgrade = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )

    raises = [node for node in ast.walk(upgrade) if isinstance(node, ast.Raise)]

    assert raises, "upgrade must raise when duplicates exist rather than proceeding"


def test_the_scan_only_considers_company_scoped_rows(migration_source: str) -> None:
    """Scanning system roles too would block the migration on rows it does not govern."""
    assert "WHERE org_id IS NOT NULL" in migration_source
    assert "GROUP BY org_id, name" in migration_source
    assert "HAVING COUNT(*) > 1" in migration_source


def test_the_migration_is_reversible(migration_source: str) -> None:
    tree = ast.parse(migration_source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}

    assert {"upgrade", "downgrade"} <= names
    assert "drop_index" in migration_source


def test_the_chain_is_linear_from_the_previous_head(migration_source: str) -> None:
    """A second migration claiming the same down_revision splits the alembic head."""
    assert 'revision: str = "20260821_081"' in migration_source
    assert 'down_revision: Union[str, None] = "20260820_080"' in migration_source

    siblings = [
        path
        for path in _MIGRATION.parent.glob("*.py")
        if path != _MIGRATION and '"20260820_080"' in path.read_text(encoding="utf-8")
    ]
    claimants = [
        path.name
        for path in siblings
        if 'down_revision: Union[str, None] = "20260820_080"' in path.read_text(encoding="utf-8")
    ]

    assert claimants == [], f"split alembic head — these also revise 20260820_080: {claimants}"
