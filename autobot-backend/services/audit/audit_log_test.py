# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the structured audit log service (Issue #4456).

Tests cover:
- record_event writes correct data to both Redis sorted sets
- query_audit_log filters by user_id, action, and timestamp range
- audit_record (sync fire-and-forget) schedules the coroutine
- Graceful handling when Redis is unavailable
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.audit.audit_log import (
    _GLOBAL_KEY,
    AuditAction,
    audit_record,
    query_audit_log,
    record_event,
)
from tests.fixtures import make_async_redis, make_redis_pipeline

# ---------------------------------------------------------------------------
# Module-level stubs — keep import chain clean without a full backend venv
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline_mock():
    # Migrated to canonical ``make_redis_pipeline()`` (#7280 round 6, post-#7339).
    return make_redis_pipeline(execute_returns=[1, 1, 1, 1, 1])


def _make_redis_mock(pipeline=None):
    # Migrated to canonical ``make_async_redis(pipeline=...)`` (#7280 round 6).
    return make_async_redis(
        pipeline=pipeline or _make_pipeline_mock(),
        zrangebyscore_returns=[],
    )


# ---------------------------------------------------------------------------
# AuditAction enum
# ---------------------------------------------------------------------------


class TestAuditAction:
    def test_all_required_values_present(self) -> None:
        required = {
            "SESSION_CREATE",
            "SESSION_DELETE",
            "SESSION_EXPORT",  # #7399: added after the test was written
            "KNOWLEDGE_ADD",
            "KNOWLEDGE_REMOVE",
            "API_KEY_CREATE",
            "API_KEY_REVOKE",
            "USER_CREATE",
            "USER_DELETE",
            "CONFIG_CHANGE",
            "ADMIN_ACTION",
        }
        names = {a.name for a in AuditAction}
        assert required == names

    def test_values_are_strings(self) -> None:
        for action in AuditAction:
            assert isinstance(action.value, str)
            assert "." in action.value  # dot-separated namespacing


# ---------------------------------------------------------------------------
# record_event
# ---------------------------------------------------------------------------


class TestRecordEvent:
    @pytest.mark.asyncio
    async def test_writes_to_user_and_global_keys(self) -> None:
        pipe = _make_pipeline_mock()
        redis = _make_redis_mock(pipe)

        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await record_event(
                user_id="alice",
                action=AuditAction.SESSION_CREATE,
                resource_type="session",
                resource_id="sess-001",
                ip_address="192.168.1.1",
                session_id="sess-001",
                outcome="success",
            )

        # Pipeline should have been called twice for zadd (user + global)
        zadd_calls = pipe.zadd.call_args_list
        keys_written = [c.args[0] for c in zadd_calls]
        assert "audit_log:alice" in keys_written
        assert _GLOBAL_KEY in keys_written

    @pytest.mark.asyncio
    async def test_entry_contains_expected_fields(self):
        captured: list = []
        pipe = _make_pipeline_mock()

        original_zadd = pipe.zadd

        async def capturing_zadd(key, mapping):
            if key == "audit_log:carol":
                captured.extend(mapping.keys())
            return await original_zadd(key, mapping)

        pipe.zadd = capturing_zadd
        redis = _make_redis_mock(pipe)

        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await record_event(
                user_id="carol",
                action=AuditAction.API_KEY_CREATE,
                metadata={"key_name": "ci-key"},
            )

        assert len(captured) == 1
        entry = json.loads(captured[0])
        assert entry["user_id"] == "carol"
        assert entry["action"] == AuditAction.API_KEY_CREATE.value
        assert entry["metadata"] == {"key_name": "ci-key"}
        assert "id" in entry
        assert "created_at" in entry

    @pytest.mark.asyncio
    async def test_noop_when_redis_unavailable(self) -> None:
        """record_event must not raise when Redis is None."""
        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            # Should complete without exception
            await record_event(user_id="bob", action=AuditAction.USER_DELETE)


# ---------------------------------------------------------------------------
# query_audit_log
# ---------------------------------------------------------------------------


class TestQueryAuditLog:
    def _make_raw_entry(self, user_id: str, action: AuditAction, created_at: float) -> bytes:
        entry = {
            "id": "test-id",
            "user_id": user_id,
            "action": action.value,
            "resource_type": None,
            "resource_id": None,
            "metadata": {},
            "ip_address": None,
            "session_id": None,
            "outcome": "success",
            "created_at": created_at,
        }
        return json.dumps(entry).encode()

    @pytest.mark.asyncio
    async def test_returns_empty_when_redis_unavailable(self) -> None:
        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            results = await query_audit_log(user_id="dave")
        assert results == []

    @pytest.mark.asyncio
    async def test_queries_user_key_when_user_id_given(self) -> None:
        redis = _make_redis_mock()
        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await query_audit_log(user_id="eve")
        redis.zrangebyscore.assert_awaited_once()
        called_key = redis.zrangebyscore.call_args.args[0]
        assert called_key == "audit_log:eve"

    @pytest.mark.asyncio
    async def test_queries_global_key_when_no_user_id(self) -> None:
        redis = _make_redis_mock()
        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await query_audit_log()
        called_key = redis.zrangebyscore.call_args.args[0]
        assert called_key == _GLOBAL_KEY

    @pytest.mark.asyncio
    async def test_filters_by_action(self) -> None:
        t = 1_700_000_000.0
        raw_create = self._make_raw_entry("frank", AuditAction.SESSION_CREATE, t)
        raw_delete = self._make_raw_entry("frank", AuditAction.SESSION_DELETE, t + 1)
        redis = _make_redis_mock()
        redis.zrangebyscore = AsyncMock(return_value=[raw_create, raw_delete])

        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            results = await query_audit_log(user_id="frank", action=AuditAction.SESSION_CREATE)

        assert len(results) == 1
        assert results[0]["action"] == AuditAction.SESSION_CREATE.value

    @pytest.mark.asyncio
    async def test_results_newest_first(self) -> None:
        t = 1_700_000_000.0
        raws = [
            self._make_raw_entry("grace", AuditAction.KNOWLEDGE_ADD, t),
            self._make_raw_entry("grace", AuditAction.KNOWLEDGE_REMOVE, t + 10),
            self._make_raw_entry("grace", AuditAction.CONFIG_CHANGE, t + 5),
        ]
        redis = _make_redis_mock()
        redis.zrangebyscore = AsyncMock(return_value=raws)

        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            results = await query_audit_log(user_id="grace")

        timestamps = [r["created_at"] for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_limit_and_offset(self) -> None:
        t = 1_700_000_000.0
        raws = [self._make_raw_entry("hank", AuditAction.USER_CREATE, t + i) for i in range(10)]
        redis = _make_redis_mock()
        redis.zrangebyscore = AsyncMock(return_value=raws)

        with patch(
            "services.audit.audit_log.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            results = await query_audit_log(user_id="hank", limit=3, offset=2)

        assert len(results) == 3


# ---------------------------------------------------------------------------
# audit_record (sync fire-and-forget)
# ---------------------------------------------------------------------------


class TestAuditRecord:
    def test_schedules_coroutine_via_run_redis_write(self) -> None:
        with patch("services.audit.audit_log.run_redis_write") as mock_rrw:
            audit_record(
                user_id="ivan",
                action=AuditAction.API_KEY_REVOKE,
                resource_type="api_key",
                resource_id="key-xyz",
            )
        assert mock_rrw.called
        _, kwargs = mock_rrw.call_args
        assert kwargs.get("label") == "audit_log"
