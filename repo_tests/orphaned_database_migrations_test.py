# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A table created only in the orphaned database/migrations/ chain never reaches a real DB (#16464).

``autobot-backend/migrations/alembic.ini`` sets ``script_location = migrations``
and ``version_locations = migrations/versions`` — ``alembic upgrade head``
never looks at ``autobot-backend/database/migrations/`` at all, and
``migrations/schema_bootstrap.py`` confirms there is no silent
``Base.metadata.create_all()`` fallback for a real (non-SQLite) database
either. A table whose only ``CREATE TABLE`` lives in the orphaned directory
does not exist on any properly-migrated deployment.

This is not hypothetical twice over: #10750 A2 found and fixed 8 LLC tables
in exactly this state, and #16464 found 6 more — including
``session_collaborations``, which ``api/collaboration.py``'s entire REST API
depends on. Both times the gap was found by hand, well after the code built
on top of the missing table shipped. This guard is the general form: it
fails the moment a NEW table is added to the orphaned chain without also
landing in the canonical one, rather than waiting for the next by-hand
discovery.

**Scope, stated because an unstated limit reads as coverage:** this guard
reads ``op.create_table(...)`` / ``Table(...)`` calls only — it does not
see ``op.add_column`` drift onto an existing table (a related but distinct
question), and it is not a database (it cannot tell whether a table was
also created by some out-of-band manual fix).
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_ORPHANED_DIR = _REPO_ROOT / "autobot-backend" / "database" / "migrations"
_CANONICAL_DIR = _REPO_ROOT / "autobot-backend" / "migrations" / "versions"

#: Tables genuinely NOT managed by the Postgres/Alembic chain, with the
#: reason stated inline — checked once (#16464), not assumed. All five are
#: database/migrations/001_create_conversation_files.py's own dedicated
#: SQLite file (conversation_files.db), built by a self-contained migration
#: runner (ConversationFilesMigration) invoked live from
#: conversation_file_manager.py — a deliberate, separate storage system, not
#: an orphaned Postgres migration.
_NOT_ALEMBIC_MANAGED = {
    "conversation_files",
    "file_metadata",
    "session_file_associations",
    "file_access_log",
    "file_cleanup_queue",
    "schema_migrations",
}


def _created_table_names(path: Path) -> set[str]:
    """Table names from every ``op.create_table("name", ...)`` or
    ``x = Table("name", ...)`` call in *path*. Both shapes appear in this
    repo's migrations (Alembic-op style and raw SQLAlchemy Core style)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_create_table_call = (isinstance(func, ast.Attribute) and func.attr == "create_table") or (
            isinstance(func, ast.Name) and func.id == "Table"
        )
        if not is_create_table_call:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            names.add(first_arg.value)
    return names


def test_every_orphaned_migrations_table_is_ported_or_explicitly_excluded() -> None:
    orphaned_files = sorted(_ORPHANED_DIR.glob("*.py"))
    canonical_files = sorted(_CANONICAL_DIR.glob("*.py"))

    # A scan that silently sees zero files reports clean for the wrong
    # reason -- a moved/renamed directory must fail loudly, not pass quietly.
    assert len(orphaned_files) >= 10, (
        f"Expected >=10 files in {_ORPHANED_DIR}, found {len(orphaned_files)}. "
        "If this directory was renamed or removed, update this guard rather than "
        "letting it report a false-clean zero-file scan."
    )
    assert len(canonical_files) >= 80, (
        f"Expected >=80 files in {_CANONICAL_DIR}, found {len(canonical_files)}. "
        "If the canonical migration directory moved, update this guard's path."
    )

    orphaned_tables: dict[str, str] = {}
    for f in orphaned_files:
        for table in _created_table_names(f):
            orphaned_tables.setdefault(table, f.name)

    canonical_tables: set[str] = set()
    for f in canonical_files:
        canonical_tables |= _created_table_names(f)

    missing = {
        table: source_file
        for table, source_file in orphaned_tables.items()
        if table not in canonical_tables and table not in _NOT_ALEMBIC_MANAGED
    }

    assert not missing, (
        "Table(s) created in autobot-backend/database/migrations/ (not Alembic's "
        f"version_locations) with no matching CREATE TABLE under migrations/versions/: "
        f"{missing}. Port each into migrations/versions/ (see #16464 / #10750 A2's "
        "20260630_065_llc_missing_feature_tables.py for the pattern -- has_table()-guarded, "
        "matches the current ORM model, forward-only downgrade), or if it is genuinely "
        "managed by its own separate migration system (like conversation_files' dedicated "
        "SQLite file), add it to _NOT_ALEMBIC_MANAGED above with a one-line reason."
    )
