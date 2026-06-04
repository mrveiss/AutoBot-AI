# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for AuditLogger service.

Issue #3277: audit logging system — verify core behaviour without a live Redis
instance by mocking get_async_redis_client and aiofiles.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures import make_async_redis, make_redis_pipeline

# Stub heavy/optional imports that are pulled in by the models package on collection.
# These are unavailable in the dev venv; the tests do not exercise SQLAlchemy code.
for _stub in (
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.ext",
    "sqlalchemy.ext.declarative",
    "aiofiles",
):
    if _stub not in sys.modules:
        sys.modules[_stub] = MagicMock()

# Stub models package so services.audit_logger can import AuditQueryContext without
# triggering the heavy SQLAlchemy __init__.py chain.
if "models" not in sys.modules:
    _models_stub = MagicMock()

    from dataclasses import dataclass
    from datetime import datetime as _dt

    @dataclass
    class _AuditQueryContext:
        start_time: _dt
        end_time: _dt
        limit: int = 100
        offset: int = 0

    _models_stub.task_context = MagicMock()
    _models_stub.task_context.AuditQueryContext = _AuditQueryContext
    sys.modules["models"] = _models_stub
    sys.modules["models.task_context"] = _models_stub.task_context
elif "models.task_context" not in sys.modules:
    from dataclasses import dataclass as _dc
    from datetime import datetime as _dt2
    from unittest.mock import MagicMock as _MM

    @_dc
    class _AuditQueryContext2:
        start_time: _dt2
        end_time: _dt2
        limit: int = 100
        offset: int = 0

    _tc_stub = _MM()
    _tc_stub.AuditQueryContext = _AuditQueryContext2
    sys.modules["models.task_context"] = _tc_stub

from services.audit_logger import (  # noqa: E402
    AuditEntry,
    AuditLogger,
    close_audit_logger,
    get_audit_logger,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline_mock():
    # Migrated to canonical ``make_redis_pipeline()`` (#7280 round 7, post-#7339).
    return make_redis_pipeline()


def _make_redis_mock(pipeline=None):
    # Migrated to canonical ``make_async_redis(pipeline=...)`` (#7280 round 7).
    return make_async_redis(
        pipeline=pipeline or _make_pipeline_mock(),
        zrange_returns=[],
    )


# ---------------------------------------------------------------------------
# AuditEntry tests
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

    def test_json_roundtrip(self) -> None:
        entry = AuditEntry(
            operation="file.upload",
            result="success",
            user_id="bob",
            details={"size": 1024},
        )
        json_str = entry.to_json()
        restored = AuditEntry.from_json(json_str)
        assert restored.id == entry.id
        assert restored.operation == entry.operation
        assert restored.user_id == entry.user_id
        assert restored.details == entry.details

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
# AuditLogger — log and batch flush
# ---------------------------------------------------------------------------


class TestAuditLoggerLog:
    @pytest.fixture
    def logger(self, tmp_path):
        al = AuditLogger(
            retention_days=7,
            batch_size=5,
            batch_timeout_seconds=0.05,
            fallback_log_dir=str(tmp_path / "audit"),
        )
        return al

    @pytest.mark.asyncio
    async def test_log_returns_true_on_success(self, logger, tmp_path) -> None:
        pipe = _make_pipeline_mock()
        redis = _make_redis_mock(pipe)
        with patch(
            "services.audit_logger.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await logger.initialize()
            ok = await logger.log(
                operation="auth.login",
                result="success",
                user_id="alice",
                ip_address="127.0.0.1",
            )
        assert ok is True
        assert logger._total_logged == 1

    @pytest.mark.asyncio
    async def test_batch_flushed_when_full(self, tmp_path) -> None:
        al = AuditLogger(
            retention_days=7,
            batch_size=3,
            batch_timeout_seconds=60,
            fallback_log_dir=str(tmp_path / "audit"),
        )
        pipe = _make_pipeline_mock()
        redis = _make_redis_mock(pipe)

        with patch(
            "services.audit_logger.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await al.initialize()
            for i in range(3):
                await al.log(operation="auth.login", user_id=f"u{i}")

        # Pipeline execute should have been called when batch hit size=3
        assert pipe.execute.called

    @pytest.mark.asyncio
    async def test_fallback_log_written_when_redis_unavailable(self, tmp_path) -> None:
        al = AuditLogger(
            retention_days=7,
            batch_size=1,
            batch_timeout_seconds=60,
            fallback_log_dir=str(tmp_path / "audit"),
        )
        with patch(
            "services.audit_logger.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            await al.initialize()
            ok = await al.log(operation="auth.login", user_id="alice")

        assert ok is True
        fallback_files = list((tmp_path / "audit").glob("audit_*.jsonl"))
        assert fallback_files, "Expected fallback JSONL file"
        first_line = fallback_files[0].read_text(encoding="utf-8").splitlines()[0]
        data = json.loads(first_line)
        assert "entry" in data

    @pytest.mark.asyncio
    async def test_flush_drains_queue(self, tmp_path) -> None:
        al = AuditLogger(
            retention_days=7,
            batch_size=100,
            batch_timeout_seconds=60,
            fallback_log_dir=str(tmp_path / "audit"),
        )
        pipe = _make_pipeline_mock()
        redis = _make_redis_mock(pipe)

        with patch(
            "services.audit_logger.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await al.initialize()
            await al.log(operation="config.update")
            assert len(al._batch_queue) == 1
            await al.flush()
            assert len(al._batch_queue) == 0


# ---------------------------------------------------------------------------
# AuditLogger — query helpers
# ---------------------------------------------------------------------------


class TestAuditLoggerQuery:
    @pytest.mark.asyncio
    async def test_query_returns_empty_when_redis_unavailable(self, tmp_path) -> None:
        al = AuditLogger(fallback_log_dir=str(tmp_path / "audit"))
        with patch(
            "services.audit_logger.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            await al.initialize()
            results = await al.query(user_id="alice")
        assert results == []

    @pytest.mark.asyncio
    async def test_query_time_range_parses_json_entries(self, tmp_path) -> None:
        al = AuditLogger(fallback_log_dir=str(tmp_path / "audit"))

        now = datetime.now(tz=timezone.utc)
        entry = AuditEntry(
            operation="session.create",
            user_id="bob",
            timestamp=now.timestamp(),
            date=now.strftime("%Y-%m-%d"),
        )
        pipe = _make_pipeline_mock()
        redis = _make_redis_mock(pipe)
        redis.zrange = AsyncMock(return_value=[entry.to_json().encode()])

        with patch(
            "services.audit_logger.get_async_redis_client",
            new=AsyncMock(return_value=redis),
        ):
            await al.initialize()
            results = await al.query(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
            )

        assert len(results) == 1
        assert results[0].operation == "session.create"
        assert results[0].user_id == "bob"


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingletonHelpers:
    @pytest.mark.asyncio
    async def test_get_audit_logger_returns_same_instance(self, tmp_path) -> None:
        with (
            patch(
                "services.audit_logger.get_async_redis_client",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "services.audit_logger.AuditLogger._initialize_impl",
                new=AsyncMock(return_value=True),
            ),
        ):
            import services.audit_logger as _mod

            # Reset singleton
            _mod._audit_logger = None
            a = await get_audit_logger()
            b = await get_audit_logger()
            assert a is b
            _mod._audit_logger = None  # clean up

    @pytest.mark.asyncio
    async def test_close_audit_logger_resets_singleton(self, tmp_path) -> None:
        import services.audit_logger as _mod

        _mod._audit_logger = None
        with (
            patch(
                "services.audit_logger.get_async_redis_client",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "services.audit_logger.AuditLogger._initialize_impl",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "services.audit_logger.AuditLogger.close",
                new=AsyncMock(),
            ),
        ):
            await get_audit_logger()
            assert _mod._audit_logger is not None
            await close_audit_logger()
            assert _mod._audit_logger is None


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
