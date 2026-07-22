# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for co-located managed-service resolution in update-all (#11605).

update-all's slm_self_update stage covers only the SLM control plane and the
fleet stage skips the self-node, so on a co-located single-box install the
managed application services (autobot-backend / autobot-frontend) were updated
by NEITHER stage when the SLM commit was already current. These tests cover the
_resolve_colocated_managed_services helper that closes that gap via the existing
per-component drift/resolve path — including its explicit #11611 autobot_shared-
first ordering (this loop is a THIRD deploy site, so shared-first must be enforced
here too, not inherited).
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Dev-host stub for models.schemas so api.code_sync imports without a full venv.
# ---------------------------------------------------------------------------
_MODELS_SNAPSHOT = {_k: sys.modules.get(_k) for _k in ("models", "models.schemas")}
if "models" not in sys.modules or isinstance(sys.modules.get("models"), MagicMock):
    from pydantic import BaseModel as _BM

    def _pydantic_stub(name: str, **fields) -> type:
        return type(name, (_BM,), {"__annotations__": {k: type(v) for k, v in fields.items()}, **fields})

    _schemas = types.ModuleType("models.schemas")
    for _cls in [
        "CodeSyncStatusResponse",
        "CodeSyncRefreshResponse",
        "CodeVersionNotification",
        "CodeVersionNotificationResponse",
        "ComponentSyncJobStatus",
        "DriftResolveJobResponse",
        "DriftResolveRequest",
        "DriftResolveResponse",
        "FileDriftReport",
        "FleetSyncJobStatus",
        "FleetSyncNodeStatus",
        "FleetSyncRequest",
        "FleetSyncResponse",
        "MarkSyncedResponse",
        "NodeSyncRequest",
        "NodeSyncResponse",
        "PendingNodeResponse",
        "PendingNodesResponse",
        "ScheduleCreate",
        "ScheduleResponse",
        "ScheduleRunResponse",
        "ScheduleUpdate",
    ]:
        setattr(_schemas, _cls, _pydantic_stub(_cls))
    _models = sys.modules.get("models") or types.ModuleType("models")
    _models.schemas = _schemas  # type: ignore[attr-defined]
    sys.modules["models"] = _models
    sys.modules["models.schemas"] = _schemas

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

import api.code_sync as _CS  # noqa: E402
from api.code_sync import (  # noqa: E402
    UpdateAllStage,
    _resolve_colocated_managed_services,
)

for _k, _v in _MODELS_SNAPSHOT.items():
    if _v is None:
        sys.modules.pop(_k, None)
    else:
        sys.modules[_k] = _v
if "models" in sys.modules and "models.schemas" in sys.modules:
    sys.modules["models"].schemas = sys.modules["models.schemas"]
del _MODELS_SNAPSHOT


_ALLOWED = {"autobot-backend", "autobot-frontend"}


@pytest.fixture(autouse=True)
def _restore_event_loop_after():
    """asyncio.run() (this module's runner) tears down and NULLs the global event
    loop. Sibling test modules still use asyncio.get_event_loop() — restore a fresh
    loop after each test so the cross-module sweep does not RuntimeError.
    """
    yield
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def test_resolves_only_drifted_colocated_components() -> None:
    """A drifted co-located component is rsynced + post-synced; a clean one is skipped."""
    stage = UpdateAllStage(name="slm_self_update")

    # autobot-backend has drift, autobot-frontend does not.
    async def fake_drift(component: str) -> bool:
        return component == "autobot-backend"

    rsynced: list = []

    async def fake_rsync(src, comp, excludes):
        rsynced.append(comp)
        return True, ""

    post_synced: list = []

    async def fake_post_sync(comp, src, dep):
        post_synced.append(comp)
        return False, ["ok"], True

    with (
        patch("api.code_sync.ALLOWED_COMPONENTS", _ALLOWED),
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(True, ""))),
        patch("api.code_sync._component_has_file_drift", side_effect=fake_drift),
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/autobot-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/opt/autobot/autobot-backend"),
        patch("api.code_sync._rsync_component_local", side_effect=fake_rsync),
        patch("api.code_sync._run_post_sync_steps", side_effect=fake_post_sync),
    ):
        asyncio.run(_resolve_colocated_managed_services(stage))

    # Only the drifted component is resolved.
    assert rsynced == ["autobot-backend"]
    assert post_synced == ["autobot-backend"]


def test_shared_first_called_before_component_rsync() -> None:
    """#11611: _ensure_autobot_shared_synced runs BEFORE the component rsync (order lock)."""
    stage = UpdateAllStage(name="slm_self_update")
    calls: list = []

    async def fake_drift(component: str) -> bool:
        return component == "autobot-backend"

    async def fake_shared(component: str):
        calls.append(("shared", component))
        return True, "ok"

    async def fake_rsync(src, comp, excludes):
        calls.append(("rsync", comp))
        return True, ""

    async def fake_post_sync(comp, src, dep):
        calls.append(("post", comp))
        return False, ["ok"], True

    with (
        patch("api.code_sync.ALLOWED_COMPONENTS", _ALLOWED),
        patch("api.code_sync._ensure_autobot_shared_synced", side_effect=fake_shared),
        patch("api.code_sync._component_has_file_drift", side_effect=fake_drift),
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/autobot-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/opt/autobot/autobot-backend"),
        patch("api.code_sync._rsync_component_local", side_effect=fake_rsync),
        patch("api.code_sync._run_post_sync_steps", side_effect=fake_post_sync),
    ):
        asyncio.run(_resolve_colocated_managed_services(stage))

    # shared-first for autobot-backend precedes its own rsync, which precedes post-sync.
    assert calls == [
        ("shared", "autobot-backend"),
        ("rsync", "autobot-backend"),
        ("post", "autobot-backend"),
    ]


def test_shared_sync_failure_skips_component_rsync() -> None:
    """#11611 fail-safe: a failed shared sync skips the component rsync + restart entirely."""
    stage = UpdateAllStage(name="slm_self_update")

    async def fake_drift(component: str) -> bool:
        return component == "autobot-backend"

    with (
        patch("api.code_sync.ALLOWED_COMPONENTS", _ALLOWED),
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(False, "shared boom"))),
        patch("api.code_sync._component_has_file_drift", side_effect=fake_drift),
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/autobot-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/opt/autobot/autobot-backend"),
        patch("api.code_sync._rsync_component_local", AsyncMock()) as rsync_mock,
        patch("api.code_sync._run_post_sync_steps", AsyncMock()) as post_mock,
    ):
        asyncio.run(_resolve_colocated_managed_services(stage))

    rsync_mock.assert_not_called()
    post_mock.assert_not_called()


def test_no_resolution_when_no_drift() -> None:
    """When neither co-located service drifts, nothing is synced or restarted."""
    stage = UpdateAllStage(name="slm_self_update")

    with (
        patch("api.code_sync._component_has_file_drift", AsyncMock(return_value=False)),
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock()) as shared_mock,
        patch("api.code_sync._rsync_component_local", AsyncMock()) as rsync_mock,
        patch("api.code_sync._run_post_sync_steps", AsyncMock()) as post_mock,
    ):
        asyncio.run(_resolve_colocated_managed_services(stage))

    shared_mock.assert_not_called()
    rsync_mock.assert_not_called()
    post_mock.assert_not_called()


def test_rsync_failure_does_not_abort_other_components() -> None:
    """A per-component rsync failure is logged and the loop continues (non-fatal)."""
    stage = UpdateAllStage(name="slm_self_update")

    async def fake_drift(component: str) -> bool:
        return True  # both drift

    post_synced: list = []

    async def fake_post_sync(comp, src, dep):
        post_synced.append(comp)
        return False, ["ok"], True

    async def fake_rsync(src, comp, excludes):
        # autobot-backend fails to rsync; autobot-frontend succeeds.
        if comp == "autobot-backend":
            return False, "rsync boom"
        return True, ""

    with (
        patch("api.code_sync.ALLOWED_COMPONENTS", _ALLOWED),
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(True, ""))),
        patch("api.code_sync._component_has_file_drift", side_effect=fake_drift),
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/x"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/opt/autobot/x"),
        patch("api.code_sync._rsync_component_local", side_effect=fake_rsync),
        patch("api.code_sync._run_post_sync_steps", side_effect=fake_post_sync),
    ):
        asyncio.run(_resolve_colocated_managed_services(stage))

    # backend rsync failed → not post-synced; frontend still resolved.
    assert post_synced == ["autobot-frontend"]


def test_component_has_file_drift_false_when_not_deployed() -> None:
    """A component whose deployed dir is absent is treated as not co-located (no drift)."""
    with (
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/autobot-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/nonexistent/path/autobot-backend"),
    ):
        result = asyncio.run(_CS._component_has_file_drift("autobot-backend"))
    assert result is False
