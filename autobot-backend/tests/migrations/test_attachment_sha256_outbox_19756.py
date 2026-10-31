# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 107 carries the ORM's attachment ``sha256`` and outbox table (#19756).

The Postgres-backed drift test (``test_orm_columns_match_migrations_17996``) is skipped
without a disposable database. This one runs everywhere: it executes the migration against a
recording ``op`` and compares what it would create with the ORM.
"""

import importlib
from unittest.mock import MagicMock, patch

from tests.migrations.test_orm_columns_match_migrations_17996 import _orm_tables, orm_column_drift

_MODULE = "migrations.versions.20261031_107_llc_attachment_sha256_and_deletion_outbox"


def _run_upgrade(*, has_column: bool = False, has_table: bool = False):
    module = importlib.import_module(_MODULE)
    op = MagicMock()
    with (
        patch.object(module, "op", op),
        patch.object(module, "has_column", return_value=has_column),
        patch.object(module, "has_table", return_value=has_table),
    ):
        module.upgrade()
    return module, op


def test_the_migration_adds_the_columns_the_orm_declares():
    _, op = _run_upgrade()
    added = op.add_column.call_args.args
    created = op.create_table.call_args
    migrated = {
        "llc_work_item_attachments": {
            c.name for t in _orm_tables() if t.name == "llc_work_item_attachments" for c in t.columns
        }
        - {"sha256"}
        | {added[1].name},
        created.args[0]: {c.name for c in created.args[1:] if hasattr(c, "name") and hasattr(c, "type")},
    }
    drift, compared = orm_column_drift(_orm_tables(), migrated)
    assert not drift, drift
    assert {"llc_work_item_attachments", "llc_attachment_file_deletions"} <= set(compared)


def test_the_new_column_is_nullable_so_no_existing_row_is_rewritten():
    _, op = _run_upgrade()
    column = op.add_column.call_args.args[1]
    assert column.nullable is True and column.server_default is None


def test_the_migration_is_idempotent_on_a_create_all_database():
    _, op = _run_upgrade(has_column=True, has_table=True)
    op.add_column.assert_not_called()
    op.create_table.assert_not_called()


def test_the_revision_chains_from_the_current_head():
    module = importlib.import_module(_MODULE)
    assert (module.revision, module.down_revision) == ("20261031_107", "20261030_105")
