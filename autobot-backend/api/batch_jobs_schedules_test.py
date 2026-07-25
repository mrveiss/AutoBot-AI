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

import json
import sys
import types
from datetime import datetime, timezone
from enum import Enum
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel


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


if "api.schemas_workflows" not in sys.modules:
    _sw = types.ModuleType("api.schemas_workflows")
    _sw.__path__ = []
    _sw.__package__ = "api"

    _sw.BatchJobStatus = BatchJobStatus  # type: ignore[attr-defined]
    _sw.BatchJobType = BatchJobType  # type: ignore[attr-defined]

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

# Issue #12380 review fix: this file and tests/test_health_probe_data_contract.py
# both stub sys.modules["api.schemas_workflows"], gated on "not already present"
# — so whichever test file collects first wins the base stub for the whole
# session. Neither file's base stub loop builds real-field BatchSchedule /
# BatchScheduleUpdate (both use the field-less `_pydantic_model` placeholder).
# This file's tests construct real BatchSchedule/BatchScheduleUpdate instances
# and read their fields (cron_expression, enabled, ...), so — regardless of
# which file collected first — force real-field versions onto the *shared*
# stub module here, before `import api.batch_jobs` below binds names from it.
# Collection (module import) always completes for every test file before any
# test *executes*, so this reassignment is visible to api.batch_jobs's own
# `from api.schemas_workflows import BatchSchedule, BatchScheduleUpdate` no
# matter which file the pytest run happens to collect first. Guarded by a
# `__spec__ is None` check so a genuine (non-stub) real module is never
# clobbered — hand-built `types.ModuleType()` stubs never populate `__spec__`
# (stays None), while every real import-system-loaded module gets a concrete
# `ModuleSpec`. NOTE: `hasattr(mod, "__file__")` is NOT a reliable stub-check
# here — both this file's and the health-probe file's stub set a catch-all
# `module.__getattr__` fallback (for arbitrary unlisted schema names), which
# makes `hasattr(mod, "__file__")` always True (returns a MagicMock) even
# though `__file__` was never actually set.
_schemas_workflows_mod = sys.modules["api.schemas_workflows"]
if _schemas_workflows_mod.__spec__ is None:
    from typing import Optional

    class _BatchSchedule(BaseModel):
        schedule_id: str
        job_id: str
        cron_expression: str
        enabled: bool
        next_run: datetime

    class _BatchScheduleUpdate(BaseModel):
        enabled: Optional[bool] = None
        cron_expression: Optional[str] = None

    _schemas_workflows_mod.BatchSchedule = _BatchSchedule  # type: ignore[attr-defined]
    _schemas_workflows_mod.BatchScheduleUpdate = _BatchScheduleUpdate  # type: ignore[attr-defined]

_pkg_stub("constants")
_leaf_stub(
    "constants.path_constants",
    PATH=types.SimpleNamespace(PROJECT_ROOT="/tmp"),  # nosec B108 - test/controlled code uses tmpdir intentionally
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
