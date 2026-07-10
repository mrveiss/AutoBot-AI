# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for fleet-node update-all fixes (#11511).

#11511 — three bugs in POST /code-sync/update-all fleet_nodes stage:

  Bug 1: Non-operational nodes (degraded / never-heartbeated) caused the whole
         job to be marked failed when their Ansible deploy predictably failed.
         Fix: _is_node_operational() gate — skip such nodes with a 'skipped'
         per-node result; the job reaches 'partial' (or 'completed') instead of
         'failed'.

  Bug 2: Per-node partial-success model was absent — a single node failure
         erased the overall success of slm_self_update and healthy nodes.
         Fix: skipped_fleet_nodes counter on UpdateAllJob; job status becomes
         'partial' when skips occurred but no operational node failed.

  Bug 3: failure message / log_lines reported [DEPRECATION WARNING] noise
         instead of the real ansible fatal: line.
         Fix: _extract_ansible_fatal() filters WARNING/DEPRECATION lines and
         returns the first fatal: / FAILED! / msg: line (or the tail).
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Dev-host stub: minimal Pydantic models so the router can be imported
# without a full SLM venv.
# ---------------------------------------------------------------------------
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

from api.code_sync import (  # noqa: E402
    UpdateAllJob,
    _extract_ansible_fatal,
    _is_node_operational,
    _make_stage,
    _run_fleet_stage,
    _StageStatus,
    _sync_fleet_node,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Node status string constants (mirror NodeStatus enum values).
# Used instead of importing NodeStatus to avoid mock contamination in
# tests that stub models.database indirectly.
# ---------------------------------------------------------------------------
_STATUS_ONLINE = "online"
_STATUS_MAINTENANCE = "maintenance"
_STATUS_DEGRADED = "degraded"
_STATUS_OFFLINE = "offline"
_STATUS_ERROR = "error"
_STATUS_PENDING = "pending"
_STATUS_ENROLLING = "enrolling"
_STATUS_DECOMMISSIONED = "decommissioned"

_NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def _fake_node(
    node_id: str = "node-abc",
    hostname: str = "test-host",
    ip_address: str = "10.0.0.2",
    status: str = _STATUS_ONLINE,
    last_heartbeat=None,
) -> SimpleNamespace:
    """Return a SimpleNamespace that mimics the Node fields _is_node_operational uses."""
    return SimpleNamespace(
        node_id=node_id,
        hostname=hostname,
        ip_address=ip_address,
        status=status,
        last_heartbeat=last_heartbeat,
    )


def _job_with_fleet_stage() -> UpdateAllJob:
    """Return an UpdateAllJob pre-populated with all four pipeline stages."""
    job = UpdateAllJob(job_id="test-job")
    job.stages = [
        _make_stage("github_fetch"),
        _make_stage("code_source_pull"),
        _make_stage("slm_self_update"),
        _make_stage("fleet_nodes"),
    ]
    return job


# ---------------------------------------------------------------------------
# Bug 1 — _is_node_operational: skip criteria
# ---------------------------------------------------------------------------


def test_is_node_operational_online_with_heartbeat() -> None:
    """An online node with a heartbeat is operational."""
    n = _fake_node(status=_STATUS_ONLINE, last_heartbeat=_NOW)
    assert _is_node_operational(n) is True


def test_is_node_operational_maintenance_with_heartbeat() -> None:
    """A maintenance node with a heartbeat is considered operational."""
    n = _fake_node(status=_STATUS_MAINTENANCE, last_heartbeat=_NOW)
    assert _is_node_operational(n) is True


def test_is_node_operational_no_heartbeat_is_not_operational() -> None:
    """A node with last_heartbeat=None is never operational (#11511 root cause)."""
    n = _fake_node(status=_STATUS_ONLINE, last_heartbeat=None)
    assert _is_node_operational(n) is False


def test_is_node_operational_degraded_is_not_operational() -> None:
    """A degraded node is not operational even with a heartbeat (#11511 root cause)."""
    n = _fake_node(status=_STATUS_DEGRADED, last_heartbeat=_NOW)
    assert _is_node_operational(n) is False


def test_is_node_operational_offline_is_not_operational() -> None:
    n = _fake_node(status=_STATUS_OFFLINE, last_heartbeat=_NOW)
    assert _is_node_operational(n) is False


def test_is_node_operational_error_is_not_operational() -> None:
    n = _fake_node(status=_STATUS_ERROR, last_heartbeat=_NOW)
    assert _is_node_operational(n) is False


def test_is_node_operational_pending_is_not_operational() -> None:
    n = _fake_node(status=_STATUS_PENDING, last_heartbeat=_NOW)
    assert _is_node_operational(n) is False


def test_is_node_operational_decommissioned_is_not_operational() -> None:
    n = _fake_node(status=_STATUS_DECOMMISSIONED, last_heartbeat=_NOW)
    assert _is_node_operational(n) is False


# ---------------------------------------------------------------------------
# Bug 3 — _extract_ansible_fatal: real error, not warning noise
# ---------------------------------------------------------------------------


def test_extract_ansible_fatal_returns_fatal_line() -> None:
    """The first 'fatal:' line is returned, not the deprecation warning."""
    output = (
        "[DEPRECATION WARNING]: DEFAULT_GATHER_SUBSET option, normalizing to 'all'\n"
        "PLAY [Update all nodes] **\n"
        "TASK [Gathering Facts] **\n"
        'fatal: [vnc]: UNREACHABLE! => {"changed": false, "msg": "Failed to connect"}\n'
    )
    result = _extract_ansible_fatal(output)
    assert "fatal:" in result
    assert "UNREACHABLE" in result
    assert "DEPRECATION WARNING" not in result


def test_extract_ansible_fatal_returns_failed_line() -> None:
    """FAILED! lines are captured as real errors."""
    output = "[WARNING]: some irrelevant warning\n" 'FAILED! => {"msg": "Permission denied"}\n'
    result = _extract_ansible_fatal(output)
    assert "FAILED!" in result
    assert "Permission denied" in result


def test_extract_ansible_fatal_skips_all_warning_lines() -> None:
    """Only [DEPRECATION WARNING] / [WARNING] prefixed lines are filtered."""
    output = "[DEPRECATION WARNING]: foo\n" "[WARNING]: bar\n" "DEPRECATION WARNING: baz\n" "fatal: [host]: FAILED!\n"
    result = _extract_ansible_fatal(output)
    assert "fatal:" in result
    assert "WARNING" not in result


def test_extract_ansible_fatal_falls_back_to_tail_when_no_fatal() -> None:
    """When there is no fatal: line, the tail of the output is returned."""
    output = "line1\nline2\nlast line"
    result = _extract_ansible_fatal(output)
    assert "last line" in result


def test_extract_ansible_fatal_handles_empty_output() -> None:
    """Empty/whitespace-only output yields a non-crashing fallback."""
    result = _extract_ansible_fatal("")
    assert result == "playbook failed (no output)"


def test_extract_ansible_fatal_deprecation_only_falls_back_to_tail() -> None:
    """When every line is a warning, falls back to last non-empty segment."""
    output = "[DEPRECATION WARNING]: foo\n[WARNING]: bar\n"
    result = _extract_ansible_fatal(output)
    # Falls through to tail — must not crash
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Bug 1 + 2 — _sync_fleet_node: degraded node is skipped, not failed
# ---------------------------------------------------------------------------


def _make_db_service_for_node(node):
    """Return a mock db_service that yields *node* for any node_id query."""
    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = node

    mock_db_session = MagicMock()
    mock_db_session.execute = AsyncMock(return_value=mock_db_result)

    mock_db_ctx = MagicMock()
    mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
    mock_db_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_db_svc = MagicMock()
    mock_db_svc.session.return_value = mock_db_ctx
    return mock_db_svc


def test_sync_fleet_node_skips_degraded_node() -> None:
    """A degraded node (no heartbeat) increments skipped, not failed (#11511)."""
    degraded = _fake_node(
        node_id="node-vnc",
        hostname="VNC",
        ip_address="172.16.168.26",
        status=_STATUS_DEGRADED,
        last_heartbeat=None,
    )
    job = _job_with_fleet_stage()
    from api.code_sync import _get_stage

    stage = _get_stage(job, "fleet_nodes")
    stage.status = _StageStatus.RUNNING

    mock_executor = MagicMock()
    mock_db_svc = _make_db_service_for_node(degraded)

    with patch("services.database.db_service", mock_db_svc, create=True):
        cont = _run(_sync_fleet_node(mock_executor, "node-vnc", job, stage, "10.0.0.1"))

    assert cont is True, "loop must continue after skipping a non-operational node"
    assert job.skipped_fleet_nodes == 1
    assert job.failed_fleet_nodes == 0
    assert job.completed_fleet_nodes == 0
    mock_executor.execute_playbook.assert_not_called()


def test_sync_fleet_node_skips_never_heartbeated_node() -> None:
    """A node that never sent a heartbeat is skipped regardless of status (#11511)."""
    never_beat = _fake_node(
        node_id="node-new",
        status=_STATUS_ONLINE,
        last_heartbeat=None,
    )
    job = _job_with_fleet_stage()
    from api.code_sync import _get_stage

    stage = _get_stage(job, "fleet_nodes")
    stage.status = _StageStatus.RUNNING

    mock_executor = MagicMock()
    mock_db_svc = _make_db_service_for_node(never_beat)

    with patch("services.database.db_service", mock_db_svc, create=True):
        cont = _run(_sync_fleet_node(mock_executor, "node-new", job, stage, ""))

    assert cont is True
    assert job.skipped_fleet_nodes == 1
    assert job.failed_fleet_nodes == 0
    mock_executor.execute_playbook.assert_not_called()


# ---------------------------------------------------------------------------
# Bug 2 — _run_fleet_stage: partial status when skips occur but no failure
# ---------------------------------------------------------------------------


def test_run_fleet_stage_partial_when_node_skipped() -> None:
    """job.status='partial' when only non-operational nodes were in the list (#11511)."""
    job = _job_with_fleet_stage()
    mock_executor = MagicMock()
    mock_executor.execute_playbook = AsyncMock(return_value={"success": True, "output": "", "returncode": 0})

    async def _fake_sync(executor, node_id, job, stage, slm_own_ip):
        job.skipped_fleet_nodes += 1
        return True

    with (
        patch("api.code_sync._sync_fleet_node", side_effect=_fake_sync),
        patch("api.code_sync.get_playbook_executor", return_value=mock_executor),
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        mock_settings.external_url = "http://10.0.0.1"
        _run(_run_fleet_stage(job, ["node-vnc"]))

    assert job.status == "partial", f"expected 'partial', got {job.status!r}"
    assert job.skipped_fleet_nodes == 1
    assert job.failed_fleet_nodes == 0
    mock_executor.execute_playbook.assert_not_called()


def test_run_fleet_stage_completed_when_no_skips_and_success() -> None:
    """job.status='completed' when all nodes deployed successfully with no skips."""
    job = _job_with_fleet_stage()
    mock_executor = MagicMock()

    async def _fake_sync(executor, node_id, job, stage, slm_own_ip):
        job.completed_fleet_nodes += 1
        return True

    with (
        patch("api.code_sync._sync_fleet_node", side_effect=_fake_sync),
        patch("api.code_sync.get_playbook_executor", return_value=mock_executor),
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        mock_settings.external_url = "http://10.0.0.1"
        _run(_run_fleet_stage(job, ["node-ok"]))

    assert job.status == "completed", f"expected 'completed', got {job.status!r}"
    assert job.skipped_fleet_nodes == 0
    assert job.completed_fleet_nodes == 1


def test_run_fleet_stage_failed_when_operational_node_fails() -> None:
    """job.status='failed' when an operational node's playbook fails (#11511).

    Also confirms that the failure_reason contains the real ansible error line,
    not a deprecation warning (Bug 3 integration check).
    """
    bad_output = (
        "[DEPRECATION WARNING]: DEFAULT_GATHER_SUBSET\n"
        'fatal: [node-fail]: UNREACHABLE! => {"msg": "Connection refused"}\n'
    )
    job = _job_with_fleet_stage()
    mock_executor = MagicMock()

    async def _fake_sync(executor, node_id, job, stage, slm_own_ip):
        from api.code_sync import _extract_ansible_fatal, _fail_fleet_stage

        error_msg = _extract_ansible_fatal(bad_output)
        job.failed_fleet_nodes += 1
        _fail_fleet_stage(job, stage, f"Fleet node {node_id} playbook failed: {error_msg}")
        return False

    with (
        patch("api.code_sync._sync_fleet_node", side_effect=_fake_sync),
        patch("api.code_sync.get_playbook_executor", return_value=mock_executor),
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        mock_settings.external_url = "http://10.0.0.1"
        _run(_run_fleet_stage(job, ["node-fail"]))

    assert job.status == "failed", f"expected 'failed', got {job.status!r}"
    assert job.failed_fleet_nodes == 1
    assert job.failure_reason is not None
    assert "DEPRECATION WARNING" not in job.failure_reason
    assert "UNREACHABLE" in job.failure_reason or "fatal:" in job.failure_reason


def test_run_fleet_stage_skips_degraded_continues_to_healthy() -> None:
    """A degraded node is skipped; the healthy node after it is still deployed."""
    job = _job_with_fleet_stage()

    # Patch _sync_fleet_node directly and track calls by node_id
    sync_calls: list[str] = []

    async def _fake_sync(executor, node_id, job, stage, slm_own_ip):
        sync_calls.append(node_id)
        if node_id == "node-vnc":
            job.skipped_fleet_nodes += 1
            return True
        if node_id == "node-ok":
            job.completed_fleet_nodes += 1
            return True
        return False

    mock_executor = MagicMock()

    with (
        patch("api.code_sync._sync_fleet_node", side_effect=_fake_sync),
        patch("api.code_sync.get_playbook_executor", return_value=mock_executor),
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        mock_settings.external_url = "http://10.0.0.1"
        _run(_run_fleet_stage(job, ["node-vnc", "node-ok"]))

    assert "node-vnc" in sync_calls
    assert "node-ok" in sync_calls
    assert job.skipped_fleet_nodes == 1
    assert job.completed_fleet_nodes == 1
    assert job.status == "partial", f"expected 'partial' (1 skip + 1 success), got {job.status!r}"
