# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A real in-memory SQLite engine whose SAVEPOINT and unique-index behaviour match a server database (#10200).

Shared test support (tests/helpers), reused by the database-backed user tests so none of them mocks
``begin_nested``: a mock cannot catch an ``add`` that flushes outside the SAVEPOINT.
Test support only; nothing in the application imports it.
"""

from __future__ import annotations

from typing import AsyncIterator, Sequence

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from user_management.models.base import Base

_SQLITE_URL = "sqlite+aiosqlite://"  # canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_WRITES = ("SAVEPOINT", "INSERT", "UPDATE", "DELETE")


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


def begin_transactions_properly(engine) -> None:  # noqa: ANN001
    """Open the transaction at the first write, as a server database does, instead of pysqlite's quirks.

    pysqlite only opens one at the first INSERT, so a SAVEPOINT taken first is released as a commit. An
    IMMEDIATE begin at the first write also makes a second writer wait and then see the first's rows,
    which is how the unique conflict is reached instead of "database is locked".
    """
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "connect")
    def _autocommit(dbapi_connection, _record) -> None:  # noqa: ANN001
        dbapi_connection.isolation_level = None

    @event.listens_for(sync_engine, "checkout")
    def _fresh(_dbapi_connection, record, _proxy) -> None:  # noqa: ANN001
        record.info["open"] = False

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _begin_at_first_write(conn, cursor, statement, *_rest) -> None:  # noqa: ANN001
        info = conn.connection.info
        if not info.get("open") and statement.lstrip().upper().startswith(_WRITES):
            cursor.execute("BEGIN IMMEDIATE")
            info["open"] = True

    @event.listens_for(sync_engine, "commit")
    @event.listens_for(sync_engine, "rollback")
    def _closed(conn) -> None:  # noqa: ANN001
        conn.connection.info["open"] = False


async def real_savepoint_session_factory(tables: Sequence, url: str = _SQLITE_URL) -> AsyncIterator:
    """Yield a session factory over a fresh database (in-memory by default) holding *tables* (``Model.__table__``)."""
    engine = create_async_engine(url)  # canonical: ignore py-adhoc-db-engine (test-local, in-memory)
    begin_transactions_properly(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=list(tables))
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine (as above)
    finally:
        await engine.dispose()
