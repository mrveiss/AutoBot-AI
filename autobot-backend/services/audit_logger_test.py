# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the operation audit logger -- an adapter onto the canonical audit service.

Issue #3277 (the logger), #17225 D3 (it stores nothing of its own): every entry is
recorded through ``services.audit.audit`` and read back from it.
"""

import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.audit_logger as audit_logger_module
from services.audit.purge import PurgeResult
from services.audit.taxonomy import AuditCategory
from services.audit_logger import (
    SYSTEM_ACTOR,
    AuditEntry,
    AuditLogger,
    audit_log,
    close_audit_logger,
    get_audit_logger,
)

# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------


class TestAuditEntry:
    def test_defaults(self) -> None:
        entry = AuditEntry(operation="auth.login", result="success")
        assert entry.id
        assert entry.timestamp > 0
        assert entry.date  # YYYY-MM-DD
        assert entry.result == "success"

    def test_sanitize_removes_sensitive_keys(self) -> None:
        entry = AuditEntry(
            operation="auth.login",
            details={
                "username": "alice",
                "password": "s3cr3t",
                "token": "abc123",
                "api_key": "key",
            },
        )
        entry.sanitize()
        assert "password" not in entry.details
        assert "token" not in entry.details
        assert "api_key" not in entry.details
        assert entry.details["username"] == "alice"

    def test_sanitize_case_insensitive(self) -> None:
        entry = AuditEntry(
            operation="auth.login",
            details={"PASSWORD": "bad", "Authorization": "Bearer x"},
        )
        entry.sanitize()
        assert "PASSWORD" not in entry.details
        assert "Authorization" not in entry.details

    def test_event_roundtrip(self) -> None:
        """An entry recorded as a canonical event reads back as the same entry (D3 field mapping)."""
        entry = AuditEntry(
            operation="file.upload",
            result="denied",
            user_id="bob",
            session_id="s1",
            resource="/api/files",
            user_role="user",
            vm_name="backend",
            details={"size": 1024},
            performance_ms=3.5,
        )
        event = entry.to_event()
        assert event.category is AuditCategory.SECURITY
        assert (event.action, event.actor_id, event.outcome, event.resource_id) == (
            "file.upload",
            "bob",
            "denied",
            "/api/files",
        )
        restored = AuditEntry.from_event(event.to_dict())
        assert restored == entry

    def test_a_system_operation_is_recorded_as_the_system_actor(self) -> None:
        assert AuditEntry(operation="egress.check").to_event().actor_id == SYSTEM_ACTOR

    def test_another_producers_event_reads_as_an_entry(self) -> None:
        """One trail: an emit_security record shows up in the operation view with its metadata as details."""
        restored = AuditEntry.from_event(
            {
                "action": "api_key.create",
                "actor_id": "carol",
                "outcome": "success",
                "metadata": {"k": 1},
                "occurred_at": 5.0,
            }
        )
        assert (restored.operation, restored.user_id, restored.details) == ("api_key.create", "carol", {"k": 1})

    def test_to_response_dict_keys(self) -> None:
        entry = AuditEntry(operation="session.create", user_id="carol")
        d = entry.to_response_dict()
        expected_keys = {
            "id",
            "timestamp",
            "date",
            "operation",
            "result",
            "user_id",
            "session_id",
            "ip_address",
            "resource",
            "vm_source",
            "vm_name",
            "user_role",
            "details",
            "performance_ms",
        }
        assert expected_keys == set(d.keys())


# ---------------------------------------------------------------------------
# AuditLogger -- records and reads through the canonical service
# ---------------------------------------------------------------------------


class TestAuditLoggerLog:
    @pytest.mark.asyncio
    async def test_log_records_one_sanitised_security_event(self) -> None:
        emit = MagicMock(return_value=True)
        with patch.object(audit_logger_module.canonical, "emit", new=emit):
            ok = await AuditLogger().log("auth.login", "success", user_id="alice", details={"password": "x", "n": 1})
        assert ok is True
        event = emit.call_args.args[0]
        assert (event.category, event.action, event.actor_id) == (AuditCategory.SECURITY, "auth.login", "alice")
        assert event.metadata["details"] == {"n": 1}, "OWASP: the secret never reaches the record"

    @pytest.mark.asyncio
    async def test_audit_log_helper_uses_the_same_path(self) -> None:
        emit = MagicMock(return_value=True)
        audit_logger_module._audit_logger = None
        try:
            with patch.object(audit_logger_module.canonical, "emit", new=emit):
                assert await audit_log("config.update", user_id="admin") is True
        finally:
            audit_logger_module._audit_logger = None
        assert emit.call_args.args[0].action == "config.update"

    @pytest.mark.asyncio
    async def test_a_failing_record_returns_false_and_never_raises(self) -> None:
        al = AuditLogger()
        with (
            patch.object(audit_logger_module.canonical, "emit", side_effect=RuntimeError("boom")),
            patch.object(audit_logger_module.canonical, "count_since", new=AsyncMock(return_value=0)),
        ):
            assert await al.log("auth.login") is False
            assert (await al.get_statistics())["total_failed"] == 1


class TestAuditLoggerQuery:
    @pytest.mark.asyncio
    async def test_filters_map_onto_one_canonical_query(self) -> None:
        query = AsyncMock(return_value=[])
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        with patch.object(audit_logger_module.canonical, "query_filtered", new=query):
            await AuditLogger().query(
                start_time=start, end_time=end, user_id="u", vm_name="backend", result="denied", operation=None, limit=5
            )
        flt = query.call_args.args[0]
        assert (flt.actor_id, flt.outcome, flt.action) == ("u", "denied", None)
        assert flt.metadata == (("vm_name", "backend"),)
        assert (flt.from_ts, flt.to_ts) == (start.timestamp(), end.timestamp())
        assert flt.category is None, "the operation view spans every category -- one trail"
        assert query.call_args.kwargs == {"limit": 5, "offset": 0}

    @pytest.mark.asyncio
    async def test_results_come_back_as_entries(self) -> None:
        stored = {"action": "auth.login", "actor_id": "alice", "outcome": "success", "metadata": {}, "occurred_at": 9.0}
        with patch.object(audit_logger_module.canonical, "query_filtered", new=AsyncMock(return_value=[stored])):
            entries = await AuditLogger().query()
        assert [(e.operation, e.user_id) for e in entries] == [("auth.login", "alice")]


class TestStatisticsAndRetention:
    @pytest.mark.asyncio
    async def test_statistics_report_an_unreachable_store(self) -> None:
        with patch.object(audit_logger_module.canonical, "count_since", new=AsyncMock(return_value=None)):
            stats = await AuditLogger().get_statistics()
        assert stats["redis_available"] is False and "entries_last_24h" not in stats

    @pytest.mark.asyncio
    async def test_statistics_count_the_last_day(self) -> None:
        with patch.object(audit_logger_module.canonical, "count_since", new=AsyncMock(return_value=4)):
            stats = await AuditLogger().get_statistics()
        assert stats["entries_last_24h"] == 4

    @pytest.mark.asyncio
    async def test_cleanup_goes_through_the_one_purge_path(self) -> None:
        apply = AsyncMock(return_value=PurgeResult(deleted=2))
        with patch.object(audit_logger_module.canonical, "apply_retention", new=apply):
            await AuditLogger().cleanup_old_logs(days_to_keep=30)
        apply.assert_awaited_once_with(cap_days=30)


class TestSingletonHelpers:
    @pytest.mark.asyncio
    async def test_get_audit_logger_returns_same_instance(self) -> None:
        audit_logger_module._audit_logger = None
        try:
            assert await get_audit_logger() is await get_audit_logger()
        finally:
            audit_logger_module._audit_logger = None

    @pytest.mark.asyncio
    async def test_close_audit_logger_resets_singleton(self) -> None:
        audit_logger_module._audit_logger = None
        await get_audit_logger()
        assert audit_logger_module._audit_logger is not None
        await close_audit_logger()
        assert audit_logger_module._audit_logger is None


# ---------------------------------------------------------------------------
# configure_audit middleware registration
# ---------------------------------------------------------------------------


class TestConfigureAudit:
    @staticmethod
    def _load_configure_audit():
        """Import configure_audit directly from the module file, bypassing the
        initialization package __init__.py which pulls in SQLAlchemy."""
        import importlib.util
        import pathlib

        spec = importlib.util.spec_from_file_location(
            "initialization.middleware",
            pathlib.Path(__file__).parent.parent / "initialization" / "middleware.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("initialization.middleware", mod)
        spec.loader.exec_module(mod)
        return mod.configure_audit

    def test_configure_audit_adds_middleware(self) -> None:
        from fastapi import FastAPI

        configure_audit = self._load_configure_audit()
        app = FastAPI()
        with patch("middleware.audit_middleware.AuditMiddleware.__init__", return_value=None):
            configure_audit(app)
        # Starlette stores middleware in app.middleware_stack after first request;
        # before that, user_middleware list holds them.
        middleware_types = [m.cls.__name__ for m in app.user_middleware if hasattr(m, "cls")]
        assert "AuditMiddleware" in middleware_types

    def test_configure_audit_graceful_on_import_error(self) -> None:
        """configure_audit must not raise when AuditMiddleware is unavailable."""
        from fastapi import FastAPI

        configure_audit = self._load_configure_audit()
        app = FastAPI()
        with patch.dict("sys.modules", {"middleware.audit_middleware": None}):
            # Should not raise
            try:
                configure_audit(app)
            except ImportError:
                pytest.fail("configure_audit raised ImportError instead of logging warning")
