# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #6916: regression tests for probe data-payload shapes.

These tests lock down the frontend-backend contract: the ``data`` dict
returned by each enriched health probe must contain the exact keys the
frontend reads from ``/api/system/health``.  Any future change to a probe
``data`` payload that would silently break the frontend must fail here first.

Probes under test
-----------------
* ``probe_batch_jobs``    (api/batch_jobs.py)
* ``probe_long_running``  (api/long_running_operations.py)

Import notes
------------
Both probe modules pull in heavy dependency chains that are not fully
available in the dev/CI venv.  We pre-stub all blocking sub-modules at the
top of this file (before any ``from api.*`` import) so the conftest stubs and
the module-level stubs here together give a clean import environment.  The
actual I/O paths (redis client, operation manager) are monkeypatched per-test.
"""

import importlib.util
import sys
import types
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Enum stubs — must mirror the real enum values so FastAPI accepts them as
# valid Query parameter types (FastAPI rejects plain Pydantic models as Query
# params, but accepts str-enum subclasses just fine).
# ---------------------------------------------------------------------------


class BatchJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BatchJobType(str, Enum):
    data_processing = "data_processing"
    ai_task = "ai_task"
    report = "report"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pkg_stub(name: str, **attrs) -> types.ModuleType:
    """Return (and register) a lightweight package stub."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__package__ = name.rpartition(".")[0]
    for k, v in attrs.items():
        setattr(mod, k, v)
    _m = MagicMock()
    mod.__getattr__ = lambda attr: _m  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def _leaf_stub(name: str, **attrs) -> types.ModuleType:
    """Return (and register) a simple (leaf) module stub."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__package__ = name.rpartition(".")[0]
    for k, v in attrs.items():
        setattr(mod, k, v)
    _m = MagicMock()
    mod.__getattr__ = lambda attr: _m  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def _pydantic_model(name: str) -> type:
    """Create a minimal Pydantic BaseModel subclass that FastAPI accepts as response_model."""
    return type(name, (BaseModel,), {"__annotations__": {}})


# ---------------------------------------------------------------------------
# Module-level stubs — must execute before any api.* import
# ---------------------------------------------------------------------------

# --- utils.error_catalog / utils.catalog_http_exceptions --------------------
# These files use  ``"SomeType" | None``  in function annotations at module
# level under Python 3.10 (missing ``from __future__ import annotations``
# guard), causing a TypeError at import time.  Stub the entire chain.
_leaf_stub("utils.error_catalog", get_error=MagicMock())
_leaf_stub("utils.catalog_http_exceptions", raise_auth_error=MagicMock(), raise_http_error=MagicMock())
_pkg_stub("utils")

# --- auth_middleware ----------------------------------------------------------
_leaf_stub("auth_middleware", get_current_user=MagicMock())

# --- autobot_shared.redis_management.config ----------------------------------
_pkg_stub("autobot_shared.redis_management.config", REDIS_DATABASES=MagicMock(), DEFAULT_MAX_CONNECTIONS=20)

# --- autobot_shared.redis_client ---------------------------------------------
# Stub the whole module so the real file (which tries to open sockets) is
# never executed.  Per-test monkeypatching then replaces get_async_redis_client
# on the api.batch_jobs namespace directly.
if "autobot_shared.redis_client" not in sys.modules:
    _rc = types.ModuleType("autobot_shared.redis_client")
    _rc.__package__ = "autobot_shared"
    _rc.get_async_redis_client = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    _rc.get_redis_client = MagicMock(return_value=None)  # type: ignore[attr-defined]
    sys.modules["autobot_shared.redis_client"] = _rc

# --- autobot_shared.error_boundaries -----------------------------------------
if "autobot_shared.error_boundaries" not in sys.modules:

    class _ErrorCategory(Enum):
        SERVER_ERROR = "server_error"
        CLIENT_ERROR = "client_error"

    _eb = types.ModuleType("autobot_shared.error_boundaries")
    _eb.__package__ = "autobot_shared"
    _eb.ErrorCategory = _ErrorCategory  # type: ignore[attr-defined]
    _eb.with_error_handling = lambda *a, **k: (lambda f: f)  # type: ignore[attr-defined]
    sys.modules["autobot_shared.error_boundaries"] = _eb

# --- autobot_shared.models.pagination ----------------------------------------
_pkg_stub("autobot_shared.models")
_leaf_stub("autobot_shared.models.pagination", PaginationParams=MagicMock())

# --- autobot_shared.security.path_validator ----------------------------------
_pkg_stub("autobot_shared.security")
_leaf_stub("autobot_shared.security.path_validator", validate_path=MagicMock())

# --- api.schemas_workflows ---------------------------------------------------
# FastAPI evaluates response_model= and Query-parameter type annotations at
# import time.  Pydantic BaseModel stubs are fine for response_model, but
# FastAPI rejects them as Query parameter types — those must be real str-enum
# subclasses.  We provide real Enum stubs for BatchJobStatus / BatchJobType
# and Pydantic BaseModel stubs for everything else — but only as a fallback:
# see _real_load_schemas_workflows() below (#12463 root-cause fix).


def _stub_schemas_workflows() -> None:
    _sw = types.ModuleType("api.schemas_workflows")
    _sw.__path__ = []
    _sw.__package__ = "api"

    # Enum types used as Query parameters — must be real str-enum subclasses.
    _sw.BatchJobStatus = BatchJobStatus  # type: ignore[attr-defined]
    _sw.BatchJobType = BatchJobType  # type: ignore[attr-defined]

    # Pydantic BaseModel stubs for response_model= / body schema usage.
    for _schema_name in [
        "APIBatchRequest",
        "APIBatchResponse",
        "BatchChatInitResponse",
        "BatchJob",
        "BatchJobCreate",
        "BatchJobDeleteResponse",
        "BatchJobList",
        "BatchLoadResponse",
        "BatchLogEntry",
        "BatchSchedule",
        "BatchScheduleDeleteResponse",
        "BatchScheduleUpdate",
        "BatchStatusResponse",
        "BatchTemplate",
        "BatchTemplateDeleteResponse",
        # Names used by api/long_running_operations.py route decorators
        "CodebaseIndexingRequest",
        "KnowledgeBaseRequest",
        "LongRunningOperationCancelResponse",
        "LongRunningOperationListResponse",
        "LongRunningOperationMigrateResponse",
        "LongRunningOperationResumeResponse",
        "LongRunningOperationStatusResponse",
        "SecurityScanRequest",
        "TestSuiteRequest",
    ]:
        setattr(_sw, _schema_name, _pydantic_model(_schema_name))

    _sw_mock = MagicMock()
    _sw.__getattr__ = lambda attr: _sw_mock  # type: ignore[attr-defined]
    sys.modules["api.schemas_workflows"] = _sw


def _real_load_schemas_workflows() -> None:
    """Real-load api/schemas_workflows.py (#12463 root-cause fix).

    ``sys.modules["api.schemas_workflows"]`` is process-global: dozens of
    route files (approval_gates, marketplace_sources, validation_dashboard,
    advanced_control, collaboration, ...) do
    ``from api.schemas_workflows import <RealResponseModel>``. The previous
    approach here hand-built a fake module with a hardcoded name allowlist
    plus a catch-all ``__getattr__`` returning a *single shared* bare
    ``MagicMock()`` for any name not on the list. Once this file (or its
    api/batch_jobs_schedules_test.py sibling) was collected before the real
    module, every unrelated route file's response_model= for a name not on
    the list resolved to that shared MagicMock, and FastAPI rejected it at
    route-registration time (``FastAPIError: Invalid args for response
    field!``) — poisoning ~9 unrelated collectors in full-suite runs.

    schemas_workflows.py only pulls in lightweight deps (pydantic,
    constants.path_constants, autobot_shared time/service_message helpers,
    models.approval — all already resolvable via conftest.py's baseline
    stubs), so real-loading it is safe and removes the whole class of bug.
    Falls back to the minimal hand-rolled stub above if it genuinely can't
    load.
    """
    if "api.schemas_workflows" in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        "api.schemas_workflows", _BACKEND_ROOT / "api" / "schemas_workflows.py"
    )
    if spec is None or spec.loader is None:
        _stub_schemas_workflows()
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules["api.schemas_workflows"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        del sys.modules["api.schemas_workflows"]
        _stub_schemas_workflows()
    else:
        if "api" in sys.modules:
            sys.modules["api"].schemas_workflows = mod  # type: ignore[attr-defined]


_real_load_schemas_workflows()

# --- constants.path_constants / constants.threshold_constants ----------------
# Imported by long_running_operations at module level.
_pkg_stub("constants")
_leaf_stub(
    "constants.path_constants",
    PATH=types.SimpleNamespace(PROJECT_ROOT="/tmp"),  # nosec B108  # test/controlled code uses tmpdir intentionally
)
_leaf_stub("constants.threshold_constants", TimingConstants=MagicMock())


import pytest  # noqa: E402  (intentionally after sys.modules setup)

# ---------------------------------------------------------------------------
# probe_batch_jobs — data contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_batch_jobs_data_shape_redis_ok(monkeypatch):
    """Happy path: redis ping succeeds — data must carry both required keys."""

    async def _fake_redis(database):
        class _Stub:
            async def ping(self):
                return True

        return _Stub()

    import api.batch_jobs as _bj

    monkeypatch.setattr(_bj, "get_async_redis_client", _fake_redis)

    result = await _bj.probe_batch_jobs(None)

    assert result.data is not None
    assert "redis_connected" in result.data
    assert "service" in result.data


@pytest.mark.asyncio
async def test_probe_batch_jobs_data_shape_redis_ping_fails(monkeypatch):
    """redis ping raises — probe must still return both keys (degraded path)."""

    async def _fake_redis(database):
        class _Stub:
            async def ping(self):
                raise ConnectionError("redis down")

        return _Stub()

    import api.batch_jobs as _bj

    monkeypatch.setattr(_bj, "get_async_redis_client", _fake_redis)

    result = await _bj.probe_batch_jobs(None)

    assert result.data is not None
    assert "redis_connected" in result.data
    assert "service" in result.data
    assert result.data["redis_connected"] is False


@pytest.mark.asyncio
async def test_probe_batch_jobs_data_shape_client_none(monkeypatch):
    """redis client returns None — probe must still return both keys (down path)."""

    async def _fake_redis(database):
        return None

    import api.batch_jobs as _bj

    monkeypatch.setattr(_bj, "get_async_redis_client", _fake_redis)

    result = await _bj.probe_batch_jobs(None)

    assert result.data is not None
    assert "redis_connected" in result.data
    assert "service" in result.data
    assert result.data["redis_connected"] is False


@pytest.mark.asyncio
async def test_probe_batch_jobs_data_service_value(monkeypatch):
    """The ``service`` key must be the canonical identifier the frontend expects."""

    async def _fake_redis(database):
        class _Stub:
            async def ping(self):
                return True

        return _Stub()

    import api.batch_jobs as _bj

    monkeypatch.setattr(_bj, "get_async_redis_client", _fake_redis)

    result = await _bj.probe_batch_jobs(None)

    assert result.data["service"] == "batch_jobs_manager"


# ---------------------------------------------------------------------------
# probe_long_running — data contract
# ---------------------------------------------------------------------------

_LONG_RUNNING_REQUIRED_KEYS = {
    "active_operations",
    "total_operations",
    "redis_connected",
    "background_processor_running",
}


@pytest.mark.asyncio
async def test_probe_long_running_data_shape_operations_unavailable(monkeypatch):
    """When _OPERATIONS_AVAILABLE is False the probe returns zeros — but all
    four required keys must still be present in data."""
    import api.long_running_operations as _lro

    monkeypatch.setattr(_lro, "_OPERATIONS_AVAILABLE", False)

    result = await _lro.probe_long_running(None)

    assert result.data is not None
    for key in _LONG_RUNNING_REQUIRED_KEYS:
        assert key in result.data, f"Missing key: {key!r}"


@pytest.mark.asyncio
async def test_probe_long_running_data_shape_operations_available(monkeypatch):
    """When _OPERATIONS_AVAILABLE is True and a minimal manager stub is provided
    the probe must return all four required keys."""
    import api.long_running_operations as _lro

    class _FakeStatus:
        RUNNING = "running"

    class _FakeManager:
        redis_client = object()  # non-None → redis_connected True

        def get_all_operations(self):
            return []

        def is_background_processor_running(self):
            return True

    monkeypatch.setattr(_lro, "_OPERATIONS_AVAILABLE", True)
    monkeypatch.setattr(_lro, "operation_integration_manager", _FakeManager())
    monkeypatch.setattr(_lro, "OperationStatus", _FakeStatus)

    result = await _lro.probe_long_running(None)

    assert result.data is not None
    for key in _LONG_RUNNING_REQUIRED_KEYS:
        assert key in result.data, f"Missing key: {key!r}"


@pytest.mark.asyncio
async def test_probe_long_running_data_counts_active_operations(monkeypatch):
    """active_operations must count only RUNNING operations; values are accurate."""
    import api.long_running_operations as _lro

    class _FakeStatus:
        RUNNING = "running"

    class _Op:
        def __init__(self, status):
            self.status = status

    class _FakeManager:
        redis_client = None  # None → redis_connected False

        def get_all_operations(self):
            return [
                _Op(_FakeStatus.RUNNING),
                _Op("completed"),
                _Op(_FakeStatus.RUNNING),
            ]

        def is_background_processor_running(self):
            return False

    monkeypatch.setattr(_lro, "_OPERATIONS_AVAILABLE", True)
    monkeypatch.setattr(_lro, "operation_integration_manager", _FakeManager())
    monkeypatch.setattr(_lro, "OperationStatus", _FakeStatus)

    result = await _lro.probe_long_running(None)

    assert result.data["active_operations"] == 2
    assert result.data["total_operations"] == 3
    assert result.data["redis_connected"] is False
    assert result.data["background_processor_running"] is False
