# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One AsyncSQLiteConnectionPool: the aiosqlite pool serves the former sync-wrapper callers (#18450)."""

import inspect

from utils import async_database_pool, database_pool


def test_sync_module_no_longer_defines_async_pool():
    assert not hasattr(database_pool, "AsyncSQLiteConnectionPool")


def test_canonical_pool_keeps_former_constructor_and_methods():
    cls = async_database_pool.AsyncSQLiteConnectionPool
    params = list(inspect.signature(cls.__init__).parameters)
    assert params[:3] == ["self", "db_path", "pool_size"]
    for name in ("get_connection", "close_all"):
        assert callable(getattr(cls, name))
