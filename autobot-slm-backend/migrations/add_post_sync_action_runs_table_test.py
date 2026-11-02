# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""add_post_sync_action_runs_table is idempotent and registered (#17455)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from migrations import add_post_sync_action_runs_table as mig
from migrations.runner import MIGRATIONS


def _conn(exists: bool):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = (exists,)
    return conn


def _statements(conn) -> list[str]:
    return [c.args[0] for c in conn.cursor.return_value.execute.call_args_list]


def test_creates_the_table_and_its_run_id_index_when_absent():
    conn = _conn(False)
    with patch.object(mig, "get_connection", return_value=conn):
        mig.migrate("postgresql://unused")
    sql = " ".join(_statements(conn))
    assert "CREATE TABLE post_sync_action_runs" in sql
    assert "CREATE INDEX ix_post_sync_action_runs_run_id" in sql
    conn.commit.assert_called_once()


def test_second_run_is_a_noop():
    conn = _conn(True)
    with patch.object(mig, "get_connection", return_value=conn):
        mig.migrate("postgresql://unused")
    assert not any("CREATE" in s for s in _statements(conn))
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_the_runner_lists_the_migration_exactly_once():
    assert MIGRATIONS.count("add_post_sync_action_runs_table") == 1
