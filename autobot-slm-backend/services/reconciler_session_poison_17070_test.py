# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17070: a DB-level failure in _upsert_service must not poison the session
for every remaining service (row-level, absorbed by a savepoint) or keep
issuing statements on a dead connection (connection-level, aborts once).

The module is loaded from disk, not imported, because the package conftest
stubs `services.*` and a plain `import services.reconciler` yields a
MagicMock that would satisfy every check here while exercising nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    spec = importlib.util.spec_from_file_location(
        "reconciler_under_session_poison_17070_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_session_poison_17070_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()


class _FakeNestedTransaction:
    """Stand-in for the object ``session.begin_nested()`` returns.

    Never suppresses an exception raised inside its ``async with`` block --
    matches the real one's behavior: a savepoint rollback undoes the
    savepoint's own effects and re-raises the original error.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _execute_result(row=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    result.scalars.return_value.all.return_value = []
    return result


def _make_db(execute_side_effect) -> AsyncMock:
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_FakeNestedTransaction())
    db.execute = AsyncMock(side_effect=execute_side_effect)
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


def _svc(name: str) -> dict:
    return {"name": name, "status": "running"}


class TestRowLevelFailureIsAbsorbed:
    """A row-level error (IntegrityError) rolls back only its own savepoint (#17070)."""

    @pytest.mark.asyncio
    async def test_the_loop_continues_after_one_services_row_level_failure(self):
        service = reconciler.ReconcilerService()
        db = _make_db(
            execute_side_effect=[
                IntegrityError("INSERT", None, Exception("dup key")),  # service "a"
                _execute_result(row=None),  # service "b" -- not found, created
                _execute_result(row=None),  # service "c" -- not found, created
                _execute_result(),  # _remove_stale_services' own select
            ]
        )

        result = await service._sync_discovered_services(db, "node-1", [_svc("a"), _svc("b"), _svc("c")])

        assert result is False  # none of these are managed/churning
        assert db.execute.await_count == 4  # 3 upserts + the stale-removal select
        assert db.add.call_count == 2  # b and c created; a's insert was rolled back, not retried


class TestConnectionLevelFailureAbortsOnce:
    """A connection-level error (OperationalError) aborts the whole sync immediately (#17070)."""

    @pytest.mark.asyncio
    async def test_the_sync_aborts_after_the_first_connection_level_failure(self):
        service = reconciler.ReconcilerService()
        db = _make_db(execute_side_effect=[OperationalError("SELECT", None, Exception("server closed the connection"))])

        with pytest.raises(OperationalError):
            await service._sync_discovered_services(db, "node-1", [_svc("a"), _svc("b"), _svc("c")])

        # No further db.execute call after the first failure -- b, c, and the
        # stale-removal select are never attempted on the broken connection.
        assert db.execute.await_count == 1
        assert db.add.call_count == 0

    @pytest.mark.asyncio
    async def test_exactly_one_error_is_logged_naming_node_stage_and_exception_class(self, caplog):
        service = reconciler.ReconcilerService()
        db = _make_db(execute_side_effect=[OperationalError("SELECT", None, Exception("timeout"))])

        with caplog.at_level("ERROR"):
            with pytest.raises(OperationalError):
                await service._sync_discovered_services(db, "node-42", [_svc("a")])

        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_records) == 1
        message = error_records[0].getMessage()
        assert "node-42" in message
        assert "service sync" in message
        assert "OperationalError" in message

    @pytest.mark.asyncio
    async def test_a_failure_during_stale_removal_also_aborts_with_that_stage_named(self, caplog):
        """The savepoint on _remove_stale_services is exercised here, not just _upsert_service."""
        service = reconciler.ReconcilerService()
        db = _make_db(
            execute_side_effect=[
                _execute_result(row=None),  # service "a" upserts cleanly
                OperationalError("SELECT", None, Exception("server closed the connection")),  # stale removal
            ]
        )

        with caplog.at_level("ERROR"):
            with pytest.raises(OperationalError):
                await service._sync_discovered_services(db, "node-7", [_svc("a")])

        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_records) == 1
        assert "stale service removal" in error_records[0].getMessage()


class TestNegativeControlProvingNoCascade:
    """Directly reproduces the pre-#17070 trigger against _upsert_service alone.

    Before the savepoint, a DB-level failure on the first statement left the
    session's transaction aborted at the database itself: every later
    statement on that SAME session raised PendingRollbackError instead of
    running -- masking the original error and repeating once per remaining
    service, which is the reported symptom (1,545 warnings in 2h). This
    proves the fixed code never reaches a second `db.execute` call at all
    once a connection-level failure is detected on the first one, so there
    is nothing left to cascade.
    """

    @pytest.mark.asyncio
    async def test_a_connection_level_failure_never_produces_a_second_distinct_error(self):
        service = reconciler.ReconcilerService()
        now = datetime.now(timezone.utc)
        db = _make_db(execute_side_effect=[OperationalError("SELECT", None, Exception("connection lost"))])

        with pytest.raises(OperationalError):
            await service._upsert_service(db, "node-1", _svc("a"), now)

        assert db.execute.await_count == 1
