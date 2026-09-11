# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310 review (BLOCKING 1) — deletion only fires after a confirmed sync.

``_run_colocated_role_procedures`` calls ``apply_role_deletions`` only when
``run_role_full_procedure`` reports ``success=True`` for that role. A failed
or errored role procedure must never reach the deletion pass, so a failed
sync leaves both the tree and the marker untouched by construction (the
function is simply never called) -- these tests pin that gate, and
``services/sync_deletions_test.py`` pins the marker/no-data-loss guarantees
of the function itself.

Bootstrap mirrors tests/api/test_colocated_managed_update_11605.py.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

from api.code_sync import UpdateAllStage, _run_colocated_role_procedures  # noqa: E402

for _k, _v in _MODELS_SNAPSHOT.items():
    if _v is None:
        sys.modules.pop(_k, None)
    else:
        sys.modules[_k] = _v
if "models" in sys.modules and "models.schemas" in sys.modules:
    sys.modules["models"].schemas = sys.modules["models.schemas"]
del _MODELS_SNAPSHOT


@pytest.fixture(autouse=True)
def _restore_event_loop_after():
    yield
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _role(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, ansible_playbook="playbooks/deploy_role.yml")


def test_a_successful_role_procedure_triggers_deletion() -> None:
    stage = UpdateAllStage(name="slm_self_update")
    role = _role("backend")

    async def fake_full_procedure(role, node_id):
        return {"success": True, "role": role.name, "output": "ok"}

    with (
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure),
        patch("api.code_sync.apply_role_deletions", AsyncMock(return_value=["autobot-backend: removed 1"])) as ard,
    ):
        asyncio.run(_run_colocated_role_procedures(stage, [role], "00-SLM-Manager"))

    ard.assert_called_once_with("backend")
    assert any("removed 1" in line for line in stage.log_lines)


def test_a_failed_role_procedure_never_calls_deletion() -> None:
    stage = UpdateAllStage(name="slm_self_update")
    role = _role("backend")

    async def fake_full_procedure(role, node_id):
        return {"success": False, "role": role.name, "error": "playbook_failed"}

    with (
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure),
        patch("api.code_sync.apply_role_deletions", AsyncMock()) as ard,
    ):
        asyncio.run(_run_colocated_role_procedures(stage, [role], "00-SLM-Manager"))

    ard.assert_not_called()
    assert any("FAILED" in line for line in stage.log_lines)


def test_a_no_playbook_role_never_calls_deletion() -> None:
    """The no_playbook branch `continue`s before the success check -- pin it too."""
    stage = UpdateAllStage(name="slm_self_update")
    role = _role("autobot_shared")

    async def fake_full_procedure(role, node_id):
        return {"success": False, "role": role.name, "error": "no_playbook"}

    with (
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure),
        patch("api.code_sync.apply_role_deletions", AsyncMock()) as ard,
    ):
        asyncio.run(_run_colocated_role_procedures(stage, [role], "00-SLM-Manager"))

    ard.assert_not_called()


def test_a_role_procedure_that_raises_never_calls_deletion() -> None:
    stage = UpdateAllStage(name="slm_self_update")
    role = _role("backend")

    async def fake_full_procedure(role, node_id):
        raise RuntimeError("ssh unreachable")

    with (
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure),
        patch("api.code_sync.apply_role_deletions", AsyncMock()) as ard,
    ):
        asyncio.run(_run_colocated_role_procedures(stage, [role], "00-SLM-Manager"))

    ard.assert_not_called()
