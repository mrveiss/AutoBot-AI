# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for co-located managed-role resolution in update-all (#11605, #12083).

update-all's slm_self_update stage covers only the SLM control plane and the
fleet stage skips the self-node, so on a co-located single-box install the
managed application roles (backend, celery, scheduler, frontend, ai-stack,
slm-agent, ...) were updated by NEITHER stage when the SLM commit was already
current.

#11605 originally closed this gap with a code-rsync-only resolve for a
hardcoded (autobot-backend, autobot-frontend) 2-tuple — which never applied
env/systemd render or npm build (#12083's root cause). These tests now cover
the #12083 replacement: _resolve_colocated_managed_services runs each managed
role's COMPLETE ansible procedure (run_role_full_procedure, the same
entrypoint the per-role Migrate button uses) for a role set derived from
NodeRole/Node.roles — not a hardcoded tuple — while still enforcing the
#11611 autobot_shared-first ordering as a THIRD deploy site.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace
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


_NODE_ID = "00-SLM-Manager"


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


def _role(name: str, playbook: str | None = "playbooks/deploy_role.yml") -> SimpleNamespace:
    return SimpleNamespace(name=name, ansible_playbook=playbook)


# ---------------------------------------------------------------------------
# (a) update-all now invokes the FULL role procedure, not rsync
# ---------------------------------------------------------------------------


def test_resolves_full_procedure_for_each_colocated_role() -> None:
    """Each co-located role gets run_role_full_procedure — not rsync/post-sync."""
    stage = UpdateAllStage(name="slm_self_update")
    backend_role = _role("backend")
    ai_stack_role = _role("ai-stack", playbook="setup-ai-stack.yml")

    calls: list = []

    async def fake_full_procedure(role, node_id):
        calls.append((role.name, node_id))
        return {"success": True, "role": role.name, "output": "ok"}

    with (
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(True, ""))),
        patch("api.code_sync._get_colocated_managed_role_names", AsyncMock(return_value={"backend", "ai-stack"})),
        patch("api.code_sync._load_colocated_roles", AsyncMock(return_value=[backend_role, ai_stack_role])),
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure),
    ):
        asyncio.run(_resolve_colocated_managed_services(stage, _NODE_ID))

    assert set(calls) == {("backend", _NODE_ID), ("ai-stack", _NODE_ID)}


def test_role_without_playbook_is_skipped_not_run() -> None:
    """A role with no ansible_playbook (e.g. autobot_shared) is skipped, never invoked."""
    stage = UpdateAllStage(name="slm_self_update")
    no_playbook_role = _role("autobot_shared", playbook=None)

    with (
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(True, ""))),
        patch("api.code_sync._get_colocated_managed_role_names", AsyncMock(return_value={"autobot_shared"})),
        patch("api.code_sync._load_colocated_roles", AsyncMock(return_value=[no_playbook_role])),
        patch("api.roles.run_role_full_procedure", AsyncMock()) as proc_mock,
    ):
        asyncio.run(_resolve_colocated_managed_services(stage, _NODE_ID))

    proc_mock.assert_not_called()


# ---------------------------------------------------------------------------
# (b) the managed-role set is derived from node roles, not a hardcoded tuple
# ---------------------------------------------------------------------------


def test_role_set_derived_from_node_role_and_node_roles_column() -> None:
    """_get_colocated_managed_role_names unions NodeRole ACTIVE rows + Node.roles,
    minus control-plane roles and the docker/autobot_shared exclusions — never a
    hardcoded (autobot-backend, autobot-frontend) tuple.
    """

    class _FakeScalars:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    class _FakeResult:
        def __init__(self, values=None, scalar=None):
            self._values = values
            self._scalar = scalar

        def scalars(self):
            return _FakeScalars(self._values or [])

        def scalar_one_or_none(self):
            return self._scalar

    fake_db = MagicMock()
    fake_db.execute = AsyncMock(
        side_effect=[
            _FakeResult(values=["ai-stack", "slm-agent"]),  # NodeRole ACTIVE rows
            _FakeResult(scalar=["ai-stack", "slm-agent", "backend", "slm-backend", "docker"]),  # Node.roles
        ]
    )

    class _FakeSession:
        async def __aenter__(self):
            return fake_db

        async def __aexit__(self, *exc):
            return False

    fake_db_service = SimpleNamespace(session=lambda: _FakeSession())

    # Patched via the live module objects (importlib.import_module), not the
    # "services.database.db_service" string form: other test modules in a full
    # sweep pop/replace sys.modules["services"]'s attribute bindings (#9780-style
    # stub churn), which breaks unittest.mock's dotted-path getattr resolution
    # even though "services.database"/"services.role_registry" are themselves
    # present in sys.modules. Resolving the modules directly sidesteps that.
    import importlib

    _services_database = importlib.import_module("services.database")
    _services_role_registry = importlib.import_module("services.role_registry")
    with (
        patch.object(_services_database, "db_service", fake_db_service),
        patch.object(_services_role_registry, "CONTROL_PLANE_ROLE_NAMES", frozenset({"slm-backend", "slm-frontend"})),
    ):
        names = asyncio.run(_CS._get_colocated_managed_role_names(_NODE_ID))

    # ai-stack/slm-agent/backend survive; slm-backend (control-plane) and
    # docker (excluded infra role) are filtered out.
    assert names == {"ai-stack", "slm-agent", "backend"}


# ---------------------------------------------------------------------------
# (c) autobot_shared-first ordering preserved
# ---------------------------------------------------------------------------


def test_shared_first_called_before_role_procedures() -> None:
    """#11611: _ensure_autobot_shared_synced runs BEFORE any role procedure (order lock)."""
    stage = UpdateAllStage(name="slm_self_update")
    calls: list = []

    async def fake_shared(component: str):
        calls.append(("shared", component))
        return True, "ok"

    async def fake_get_names(node_id):
        calls.append(("get_names", node_id))
        return {"backend"}

    async def fake_load_roles(role_names):
        calls.append(("load_roles", tuple(sorted(role_names))))
        return [_role("backend")]

    async def fake_full_procedure(role, node_id):
        calls.append(("procedure", role.name))
        return {"success": True}

    with (
        patch("api.code_sync._ensure_autobot_shared_synced", side_effect=fake_shared),
        patch("api.code_sync._get_colocated_managed_role_names", side_effect=fake_get_names),
        patch("api.code_sync._load_colocated_roles", side_effect=fake_load_roles),
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure),
    ):
        asyncio.run(_resolve_colocated_managed_services(stage, _NODE_ID))

    assert calls[0] == ("shared", "autobot-backend")
    assert calls[-1] == ("procedure", "backend")


def test_shared_sync_failure_aborts_before_any_role_procedure() -> None:
    """#11611 fail-safe: a failed shared sync skips role resolution + procedures entirely."""
    stage = UpdateAllStage(name="slm_self_update")

    with (
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(False, "shared boom"))),
        patch("api.code_sync._get_colocated_managed_role_names", AsyncMock()) as names_mock,
        patch("api.code_sync._load_colocated_roles", AsyncMock()) as load_mock,
        patch("api.roles.run_role_full_procedure", AsyncMock()) as proc_mock,
    ):
        asyncio.run(_resolve_colocated_managed_services(stage, _NODE_ID))

    names_mock.assert_not_called()
    load_mock.assert_not_called()
    proc_mock.assert_not_called()


def test_no_resolution_when_no_roles_assigned() -> None:
    """When no managed role is assigned/detected on this node, nothing runs."""
    stage = UpdateAllStage(name="slm_self_update")

    with (
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(True, ""))),
        patch("api.code_sync._get_colocated_managed_role_names", AsyncMock(return_value=set())),
        patch("api.code_sync._load_colocated_roles", AsyncMock(return_value=[])) as load_mock,
        patch("api.roles.run_role_full_procedure", AsyncMock()) as proc_mock,
    ):
        asyncio.run(_resolve_colocated_managed_services(stage, _NODE_ID))

    load_mock.assert_called_once_with(set())
    proc_mock.assert_not_called()


# ---------------------------------------------------------------------------
# (d) per-role failure is non-fatal
# ---------------------------------------------------------------------------


def test_role_procedure_failure_does_not_abort_other_roles() -> None:
    """A per-role procedure exception is logged and the loop continues (non-fatal)."""
    stage = UpdateAllStage(name="slm_self_update")
    backend_role = _role("backend")
    frontend_role = _role("frontend")

    async def fake_full_procedure(role, node_id):
        if role.name == "backend":
            raise RuntimeError("ansible boom")
        return {"success": True, "role": role.name}

    with (
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(True, ""))),
        patch(
            "api.code_sync._get_colocated_managed_role_names",
            AsyncMock(return_value={"backend", "frontend"}),
        ),
        patch(
            "api.code_sync._load_colocated_roles",
            AsyncMock(return_value=[backend_role, frontend_role]),
        ),
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure) as proc_mock,
    ):
        asyncio.run(_resolve_colocated_managed_services(stage, _NODE_ID))

    # Both roles were attempted despite backend raising.
    assert proc_mock.call_count == 2
    assert any("resolve error" in msg for msg in stage.log_lines)


def test_role_procedure_unsuccessful_result_is_non_fatal() -> None:
    """A role procedure that returns success=False is logged and the loop continues."""
    stage = UpdateAllStage(name="slm_self_update")
    backend_role = _role("backend")
    frontend_role = _role("frontend")

    async def fake_full_procedure(role, node_id):
        if role.name == "backend":
            return {"success": False, "role": "backend", "error": "playbook_not_found"}
        return {"success": True, "role": "frontend"}

    with (
        patch("api.code_sync._ensure_autobot_shared_synced", AsyncMock(return_value=(True, ""))),
        patch(
            "api.code_sync._get_colocated_managed_role_names",
            AsyncMock(return_value={"backend", "frontend"}),
        ),
        patch(
            "api.code_sync._load_colocated_roles",
            AsyncMock(return_value=[backend_role, frontend_role]),
        ),
        patch("api.roles.run_role_full_procedure", side_effect=fake_full_procedure) as proc_mock,
    ):
        asyncio.run(_resolve_colocated_managed_services(stage, _NODE_ID))

    assert proc_mock.call_count == 2
    assert any("FAILED" in msg for msg in stage.log_lines)


# ---------------------------------------------------------------------------
# Retained utility coverage (#11605): _component_has_file_drift itself is
# still correct even though it is no longer called from the co-located
# resolve path (superseded by the DB-driven role-presence check, #12083).
# ---------------------------------------------------------------------------


def test_component_has_file_drift_false_when_not_deployed() -> None:
    """A component whose deployed dir is absent is treated as not co-located (no drift)."""
    with (
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/autobot-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/nonexistent/path/autobot-backend"),
    ):
        result = asyncio.run(_CS._component_has_file_drift("autobot-backend"))
    assert result is False
