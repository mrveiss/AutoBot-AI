# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #12380: PATCH /batch-jobs/schedules/{schedule_id} toggle regression tests.

The frontend's ``useBatchProcessing.toggleSchedule`` PATCHes this route with
``{ enabled }`` to flip a schedule on/off. These tests lock down that the
route exists, persists the update to the same Redis-backed store the
GET/POST/DELETE handlers use, and 404s for an unknown schedule id.

Import notes
------------
``api/batch_jobs.py`` pulls in a heavy dependency chain not fully available
in the dev/CI venv. We pre-stub the same blocking sub-modules used by
``tests/test_health_probe_data_contract.py`` before importing the module
under test, then monkeypatch the sync ``get_redis_client`` per-test with an
in-memory fake.
"""

import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


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


def _pkg_stub(name: str, **attrs) -> types.ModuleType:
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
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__package__ = name.rpartition(".")[0]
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


_leaf_stub("utils.error_catalog", get_error=MagicMock())
_leaf_stub("utils.catalog_http_exceptions", raise_auth_error=MagicMock(), raise_http_error=MagicMock())
_pkg_stub("utils")

_leaf_stub("auth_middleware", get_current_user=MagicMock())

_pkg_stub("autobot_shared.redis_management.config", REDIS_DATABASES=MagicMock(), DEFAULT_MAX_CONNECTIONS=20)

if "autobot_shared.redis_client" not in sys.modules:
    _rc = types.ModuleType("autobot_shared.redis_client")
    _rc.__package__ = "autobot_shared"
    from unittest.mock import AsyncMock

    _rc.get_async_redis_client = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    _rc.get_redis_client = MagicMock(return_value=None)  # type: ignore[attr-defined]
    sys.modules["autobot_shared.redis_client"] = _rc

if "autobot_shared.error_boundaries" not in sys.modules:

    class _ErrorCategory(Enum):
        SERVER_ERROR = "server_error"
        CLIENT_ERROR = "client_error"

    _eb = types.ModuleType("autobot_shared.error_boundaries")
    _eb.__package__ = "autobot_shared"
    _eb.ErrorCategory = _ErrorCategory  # type: ignore[attr-defined]
    _eb.with_error_handling = lambda *a, **k: (lambda f: f)  # type: ignore[attr-defined]
    sys.modules["autobot_shared.error_boundaries"] = _eb

_pkg_stub("autobot_shared.models")
_leaf_stub("autobot_shared.models.pagination", PaginationParams=MagicMock())

_pkg_stub("autobot_shared.security")
_leaf_stub("autobot_shared.security.path_validator", validate_path=MagicMock())


def _pydantic_model(name: str) -> type:
    return type(name, (BaseModel,), {"__annotations__": {}})


def _stub_schemas_workflows() -> None:
    """Minimal hand-rolled fallback used only if the real module (below)
    can't be loaded in this environment. Builds real-field BatchSchedule /
    BatchScheduleUpdate classes directly (rather than the field-less
    ``_pydantic_model`` placeholder) since this file's tests construct real
    instances and read their fields (cron_expression, enabled, ...).
    """
    from typing import Optional

    _sw = types.ModuleType("api.schemas_workflows")
    _sw.__path__ = []
    _sw.__package__ = "api"

    _sw.BatchJobStatus = BatchJobStatus  # type: ignore[attr-defined]
    _sw.BatchJobType = BatchJobType  # type: ignore[attr-defined]

    class _BatchSchedule(BaseModel):
        schedule_id: str
        job_id: str
        cron_expression: str
        enabled: bool
        next_run: datetime

    class _BatchScheduleUpdate(BaseModel):
        enabled: Optional[bool] = None
        cron_expression: Optional[str] = None

    _sw.BatchSchedule = _BatchSchedule  # type: ignore[attr-defined]
    _sw.BatchScheduleUpdate = _BatchScheduleUpdate  # type: ignore[attr-defined]

    # NOTE: this list must stay a superset-compatible match with the stub list
    # in tests/test_health_probe_data_contract.py — both files guard their
    # sys.modules["api.schemas_workflows"] stub with "if not already present",
    # so whichever test file's module is collected first wins for the whole
    # pytest session. Missing names here would break that file's later import
    # of api.long_running_operations (which shares this schemas module).
    for _schema_name in [
        "APIBatchRequest",
        "APIBatchResponse",
        "BatchChatInitResponse",
        "BatchJobCreate",
        "BatchJobDeleteResponse",
        "BatchJobList",
        "BatchJob",
        "BatchLoadResponse",
        "BatchLogEntry",
        "BatchScheduleDeleteResponse",
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
    tests/test_health_probe_data_contract.py sibling) was collected before
    the real module, every unrelated route file's response_model= for a name
    not on the list resolved to that shared MagicMock, and FastAPI rejected
    it at route-registration time (``FastAPIError: Invalid args for response
    field!``) — poisoning ~9 unrelated collectors in full-suite runs.

    schemas_workflows.py only pulls in lightweight deps (pydantic,
    constants.path_constants, autobot_shared time/service_message helpers,
    models.approval — all already resolvable via conftest.py's baseline
    stubs), so real-loading it is safe and removes the whole class of bug.
    Falls back to a minimal hand-rolled stub if it genuinely can't load.
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

_pkg_stub("constants")
_leaf_stub(
    "constants.path_constants",
    PATH=types.SimpleNamespace(PROJECT_ROOT="/tmp"),  # nosec B108  # test/controlled code uses tmpdir intentionally
)
_leaf_stub("constants.threshold_constants", TimingConstants=MagicMock())


class _FakeRedis:
    """In-memory stand-in for the sync redis client used by api/batch_jobs.py."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value.encode("utf-8") if isinstance(value, str) else value

    def exists(self, key):
        return key in self._store

    def delete(self, key):
        self._store.pop(key, None)

    def sadd(self, *_a, **_k):
        return 1

    def srem(self, *_a, **_k):
        return 1


import api.batch_jobs as _bj  # noqa: E402  (intentionally after sys.modules setup)
from api.schemas_workflows import BatchSchedule, BatchScheduleUpdate  # noqa: E402


def _seed_schedule(redis, schedule_id="sched-1", enabled=True):
    schedule = BatchSchedule(
        schedule_id=schedule_id,
        job_id="job-1",
        cron_expression="0 * * * *",
        enabled=enabled,
        next_run=datetime.now(tz=timezone.utc),
    )
    redis.set(_bj._get_schedule_key(schedule_id), schedule.model_dump_json())
    return schedule


@pytest.mark.asyncio
async def test_patch_schedule_toggles_enabled_and_persists(monkeypatch):
    """PATCH {enabled: false} disables a schedule and persists the change."""
    redis = _FakeRedis()
    _seed_schedule(redis, schedule_id="sched-1", enabled=True)
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: redis)

    result = await _bj.update_batch_schedule(
        "sched-1",
        BatchScheduleUpdate(enabled=False),
        current_user={"user_id": "test"},
    )

    assert result.enabled is False
    assert result.schedule_id == "sched-1"

    persisted = json.loads(redis.get(_bj._get_schedule_key("sched-1")).decode("utf-8"))
    assert persisted["enabled"] is False


@pytest.mark.asyncio
async def test_patch_schedule_unknown_id_404(monkeypatch):
    """PATCH against a nonexistent schedule id raises 404."""
    from fastapi import HTTPException

    redis = _FakeRedis()
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: redis)

    with pytest.raises(HTTPException) as exc_info:
        await _bj.update_batch_schedule(
            "does-not-exist",
            BatchScheduleUpdate(enabled=False),
            current_user={"user_id": "test"},
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_patch_schedule_leaves_unset_fields_untouched(monkeypatch):
    """Fields absent from the request body (exclude_unset) are not overwritten."""
    redis = _FakeRedis()
    _seed_schedule(redis, schedule_id="sched-2", enabled=True)
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: redis)

    result = await _bj.update_batch_schedule(
        "sched-2",
        BatchScheduleUpdate(enabled=False),
        current_user={"user_id": "test"},
    )

    assert result.cron_expression == "0 * * * *"
