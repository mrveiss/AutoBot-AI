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

#14683 — the fired self-update stage had no completion path in this process.
         It relied on the restart killing us so the startup resume hook would
         continue the fleet stage; when the play finished WITHOUT replacing the
         service, the stage stayed RUNNING and fleet_nodes stayed PENDING
         forever, so no node was ever updated and the job could not finish.
         Fix: _reconcile_self_update_stage() resolves the stage against the
         play's real completion.

  Bug 3: failure message / log_lines reported [DEPRECATION WARNING] noise
         instead of the real ansible fatal: line.
         Fix: _extract_ansible_fatal() filters WARNING/DEPRECATION lines and
         returns the first fatal: / FAILED! / msg: line (or the tail).
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Dev-host stub: minimal Pydantic models so the router can be imported
# without a full SLM venv.
# ---------------------------------------------------------------------------
# #11794: snapshot the models entries — restored right after api.code_sync
# loads (see below) so the pydantic stand-ins don't leak across directories.
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

from api.code_sync import (  # noqa: E402
    _UPDATE_ALL_STALE_SECONDS,
    UpdateAllJob,
    _await_self_update_completion,
    _clear_update_all_job,
    _completion_is_from_a_rotated_log,
    _completion_is_newer_than,
    _extract_ansible_fatal,
    _get_stage,
    _is_node_operational,
    _job_is_stale,
    _make_stage,
    _reconcile_self_update_stage,
    _run_fleet_stage,
    _set_update_all_job,
    _StageStatus,
    _sync_fleet_node,
    start_update_all,
)

# #11794: restore the pre-file models/models.schemas sys.modules entries now
# that api.code_sync is loaded.  The narrow pydantic stand-ins otherwise leak
# into later-collected directories (tests/services/test_saml_slo.py and
# test_token_denylist.py real-load services/auth.py, whose
# `from models.schemas import TokenResponse` breaks against them).
for _k, _v in _MODELS_SNAPSHOT.items():
    if _v is None:
        sys.modules.pop(_k, None)
    else:
        sys.modules[_k] = _v
if "models" in sys.modules and "models.schemas" in sys.modules:
    sys.modules["models"].schemas = sys.modules["models.schemas"]
del _MODELS_SNAPSHOT


def _run(coro):
    # #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
    # running before any async test on its worker had no current loop for get_event_loop().
    return asyncio.run(coro)


@contextlib.contextmanager
def _patched_db_service(mock_db_svc):
    """setattr/restore replacement for patch(..., create=True) (#11798).

    mock.patch with create=True delattr's the attribute on exit when it was
    an auto-created MagicMock child (not in __dict__); Mock records that
    deletion, so every LATER ``patch("services.database.db_service")`` in the
    sweep raises AttributeError (tests/api/test_component_resolve_job.py).
    """
    mod = sys.modules["services.database"]
    prev = getattr(mod, "db_service", None)
    mod.db_service = mock_db_svc
    try:
        yield
    finally:
        mod.db_service = prev


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
    """A degraded node that ansible cannot reach increments skipped, not failed.

    #11511 established the outcome: a node that cannot be contacted must not
    fail the job. #14297 changed how that is decided — the node is no longer
    skipped on its *health*, because a node too stale to heartbeat is exactly
    the one that needs the update, and skipping it on health was a deadlock.
    Ansible's UNREACHABLE verdict decides instead, so this test now supplies
    that verdict rather than asserting the playbook never ran.
    """
    degraded = _fake_node(
        node_id="node-vnc",
        hostname="VNC",
        ip_address="203.0.113.26",  # RFC 5737 TEST-NET-3 doc IP (no real fleet IPs in tests — SSOT)
        status=_STATUS_DEGRADED,
        last_heartbeat=None,
    )
    job = _job_with_fleet_stage()
    from api.code_sync import _get_stage

    stage = _get_stage(job, "fleet_nodes")
    stage.status = _StageStatus.RUNNING

    mock_executor = MagicMock()
    mock_executor.execute_playbook = AsyncMock(
        return_value={
            "success": False,
            "returncode": 4,
            "output": 'fatal: [node-vnc]: UNREACHABLE! => {"msg": "Failed to connect to the host via ssh"}',
        }
    )
    mock_db_svc = _make_db_service_for_node(degraded)

    with _patched_db_service(mock_db_svc):
        cont = _run(_sync_fleet_node(mock_executor, "node-vnc", job, stage, "10.0.0.1"))

    assert cont is True, "loop must continue after skipping an unreachable node"
    assert job.skipped_fleet_nodes == 1
    assert job.failed_fleet_nodes == 0
    assert job.completed_fleet_nodes == 0
    mock_executor.execute_playbook.assert_called_once()


def test_sync_fleet_node_skips_never_heartbeated_node() -> None:
    """A node that never heartbeated is attempted, and skipped only if unreachable.

    Same reclassification as above (#14297): never having heartbeated is the
    signature of a node that has not been provisioned yet, which is precisely
    a node that should receive the deploy.
    """
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
    mock_executor.execute_playbook = AsyncMock(
        return_value={
            "success": False,
            "returncode": 4,
            "output": 'fatal: [node-new]: UNREACHABLE! => {"msg": "Failed to connect to the host via ssh"}',
        }
    )
    mock_db_svc = _make_db_service_for_node(never_beat)

    with _patched_db_service(mock_db_svc):
        cont = _run(_sync_fleet_node(mock_executor, "node-new", job, stage, ""))

    assert cont is True
    assert job.skipped_fleet_nodes == 1
    assert job.failed_fleet_nodes == 0
    mock_executor.execute_playbook.assert_called_once()


def test_sync_fleet_node_updates_a_degraded_but_reachable_node() -> None:
    """The deadlock-breaker (#14297).

    The node in the live report was degraded, SSH-reachable, and 1140 commits
    behind — skipped on every run by the health check, so it could never get
    the update that would let it heartbeat again. Reachable means it gets the
    deploy.
    """
    degraded = _fake_node(
        node_id="node-vnc",
        hostname="VNC",
        ip_address="203.0.113.26",  # RFC 5737 TEST-NET-3 doc IP (no real fleet IPs in tests — SSOT)
        status=_STATUS_DEGRADED,
        last_heartbeat=None,
    )
    job = _job_with_fleet_stage()
    from api.code_sync import _get_stage

    stage = _get_stage(job, "fleet_nodes")
    stage.status = _StageStatus.RUNNING

    mock_executor = MagicMock()
    mock_executor.execute_playbook = AsyncMock(return_value={"success": True, "output": "", "returncode": 0})
    mock_db_svc = _make_db_service_for_node(degraded)

    with _patched_db_service(mock_db_svc), patch("api.code_sync._update_fleet_node_version", new=AsyncMock()):
        cont = _run(_sync_fleet_node(mock_executor, "node-vnc", job, stage, "10.0.0.1"))

    assert cont is True
    assert job.completed_fleet_nodes == 1, "a reachable node must be updated even while degraded"
    assert job.skipped_fleet_nodes == 0
    assert job.failed_fleet_nodes == 0


def test_sync_fleet_node_fails_a_degraded_node_that_broke_rather_than_vanished() -> None:
    """A real failure must stay a failure, even for an unhealthy node.

    If every failure against a degraded node counted as "it was down", a broken
    deploy would report itself as a skip, the job would go green, and the node
    would stay stale — the original bug wearing a different hat.
    """
    degraded = _fake_node(
        node_id="node-vnc",
        hostname="VNC",
        ip_address="203.0.113.26",
        status=_STATUS_DEGRADED,
        last_heartbeat=None,
    )
    job = _job_with_fleet_stage()
    from api.code_sync import _get_stage

    stage = _get_stage(job, "fleet_nodes")
    stage.status = _StageStatus.RUNNING

    mock_executor = MagicMock()
    mock_executor.execute_playbook = AsyncMock(
        return_value={
            "success": False,
            "returncode": 2,
            "output": 'TASK [Install]\nfatal: [node-vnc]: FAILED! => {"msg": "pip resolution failed"}',
        }
    )
    mock_db_svc = _make_db_service_for_node(degraded)

    with _patched_db_service(mock_db_svc):
        cont = _run(_sync_fleet_node(mock_executor, "node-vnc", job, stage, "10.0.0.1"))

    assert cont is False, "a real failure halts the stage"
    assert job.failed_fleet_nodes == 1
    assert job.skipped_fleet_nodes == 0


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


# ---------------------------------------------------------------------------
# #14683 — the fired self-update stage must resolve without a restart
# ---------------------------------------------------------------------------


def _fired_job() -> UpdateAllJob:
    """A job whose slm_self_update stage has fired and is awaiting completion."""
    job = _job_with_fleet_stage()
    stage = _get_stage(job, "slm_self_update")
    stage.status = _StageStatus.RUNNING
    stage.started_at = "2026-08-21T12:08:47.427212+00:00"
    return job


_BEFORE_FIRING = "2026-08-21T12:00:00+00:00"
_AFTER_FIRING = "2026-08-21T12:09:17.784629+00:00"
_TARGET = "4b6defc41813bef8201c8ce6921588aa60bcafb7"
_FIRED_AT = "2026-08-21T12:08:47.427212+00:00"


def test_stale_completion_is_not_our_play() -> None:
    """The whole defect in one assertion.

    A play that finished BEFORE we fired must never be read as ours, or the
    stage resolves instantly against someone else's run.
    """
    assert _completion_is_newer_than(_BEFORE_FIRING, "2026-08-21T12:08:47.427212+00:00") is False


def test_fresh_completion_is_our_play() -> None:
    assert _completion_is_newer_than(_AFTER_FIRING, "2026-08-21T12:08:47.427212+00:00") is True


def test_absent_or_unparseable_completion_is_not_a_completion() -> None:
    """An unreadable timestamp must not read as 'finished'."""
    fired = "2026-08-21T12:08:47.427212+00:00"
    assert _completion_is_newer_than(None, fired) is False
    assert _completion_is_newer_than("", fired) is False
    assert _completion_is_newer_than("not-a-timestamp", fired) is False
    assert _completion_is_newer_than(_AFTER_FIRING, None) is False


def test_naive_timestamps_are_treated_as_utc() -> None:
    """Mixed aware/naive input must compare, not raise."""
    assert _completion_is_newer_than("2026-08-21T12:09:17", "2026-08-21T12:08:47+00:00") is True
    assert _completion_is_newer_than("2026-08-21T12:00:00", "2026-08-21T12:08:47+00:00") is False


def test_wait_does_not_resolve_while_the_unit_state_is_unknown() -> None:
    """in_progress=None means 'could not query' — unknown is not finished."""
    unknown = SimpleNamespace(in_progress=None, reason="unknown", last_completed_play_at=_AFTER_FIRING)
    with (
        patch("api.code_sync.read_deploy_activity", AsyncMock(return_value=unknown)),
        patch("api.code_sync._SELF_UPDATE_WATCH_TIMEOUT_SECONDS", 2),
        patch("api.code_sync._SELF_UPDATE_WATCH_POLL_SECONDS", 1),
    ):
        assert _run(_await_self_update_completion("2026-08-21T12:08:47.427212+00:00")) is None


def test_wait_returns_the_completion_once_the_play_ends() -> None:
    done = SimpleNamespace(
        in_progress=False, reason="no self-update play is running", last_completed_play_at=_AFTER_FIRING
    )
    with (
        patch("api.code_sync.read_deploy_activity", AsyncMock(return_value=done)),
        patch("api.code_sync._SELF_UPDATE_WATCH_TIMEOUT_SECONDS", 5),
        patch("api.code_sync._SELF_UPDATE_WATCH_POLL_SECONDS", 1),
    ):
        assert _run(_await_self_update_completion("2026-08-21T12:08:47.427212+00:00")) == _AFTER_FIRING


def test_no_restart_still_reaches_the_fleet_stage() -> None:
    """The regression: this is the run that used to hang forever."""
    job = _fired_job()
    fleet = AsyncMock()
    verdict = SimpleNamespace(failed_hosts=0, unreachable_hosts=0, reason=None)
    with (
        patch("api.code_sync._await_self_update_completion", AsyncMock(return_value=_AFTER_FIRING)),
        patch("api.code_sync._run_fleet_stage_or_already_current", fleet),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
        patch("services.self_update_log_reader.read_self_update_verdict", return_value=verdict),
        # The deployed commit must match the target or the stage refuses to
        # continue -- the play that completed may not have been ours.
        patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value=_TARGET)),
    ):
        _run(_reconcile_self_update_stage(job, _TARGET, ["node-a"]))

    stage = _get_stage(job, "slm_self_update")
    assert stage.status == _StageStatus.SUCCESS, f"stage left at {stage.status!r}"
    assert stage.completed_at, "a resolved stage must carry a completion time"
    fleet.assert_awaited_once()


def test_failed_play_fails_the_job_with_a_reason() -> None:
    """A count alone gave the operator nothing to act on."""
    job = _fired_job()
    fleet = AsyncMock()
    verdict = SimpleNamespace(failed_hosts=1, unreachable_hosts=0, reason=None)
    with (
        patch("api.code_sync._await_self_update_completion", AsyncMock(return_value=_AFTER_FIRING)),
        patch("api.code_sync._run_fleet_stage_or_already_current", fleet),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
        patch("services.self_update_log_reader.read_self_update_verdict", return_value=verdict),
    ):
        _run(_reconcile_self_update_stage(job, "4b6defc4", ["node-a"]))

    stage = _get_stage(job, "slm_self_update")
    assert stage.status == _StageStatus.FAILED
    assert "failed" in stage.message
    assert job.status == "failed"
    # a failed self-update must not go on to deploy to the fleet
    fleet.assert_not_awaited()


def test_timeout_fails_the_stage_rather_than_hanging() -> None:
    job = _fired_job()
    fleet = AsyncMock()
    with (
        patch("api.code_sync._await_self_update_completion", AsyncMock(return_value=None)),
        patch("api.code_sync._run_fleet_stage_or_already_current", fleet),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        _run(_reconcile_self_update_stage(job, "4b6defc4", ["node-a"]))

    stage = _get_stage(job, "slm_self_update")
    assert stage.status == _StageStatus.FAILED
    assert job.status == "failed"
    assert stage.completed_at
    fleet.assert_not_awaited()


def test_a_foreign_play_does_not_resolve_this_stage() -> None:
    """The completion signal is box-global (#14685 review).

    POST /self-update and the fleet sync job share the same log and unit, and
    neither checks for an update-all in flight, so an unrelated play can satisfy
    the wait. A deployed commit that is not the target means the outcome was not
    ours, and the fleet must not be touched on the strength of it.
    """
    job = _fired_job()
    fleet = AsyncMock()
    verdict = SimpleNamespace(failed_hosts=0, unreachable_hosts=0, reason=None)
    with (
        patch("api.code_sync._await_self_update_completion", AsyncMock(return_value=_AFTER_FIRING)),
        patch("api.code_sync._run_fleet_stage_or_already_current", fleet),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
        patch("services.self_update_log_reader.read_self_update_verdict", return_value=verdict),
        patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value="0000000000000000")),
    ):
        _run(_reconcile_self_update_stage(job, _TARGET, ["node-a"]))

    assert job.status == "failed", "a play that left the wrong commit deployed must not pass"
    fleet.assert_not_awaited()


def test_a_rotated_log_is_not_read_as_a_fresh_completion() -> None:
    """logrotate uses copytruncate, so the live log's mtime dates the truncation.

    That timestamp is recent enough to pass the freshness check while describing
    no play at all, with the verdict coming from an older run.
    """
    done = SimpleNamespace(
        in_progress=False, reason="no self-update play is running", last_completed_play_at=_AFTER_FIRING
    )
    with (
        patch("api.code_sync.read_deploy_activity", AsyncMock(return_value=done)),
        patch("api.code_sync._completion_is_from_a_rotated_log", return_value=True),
        patch("api.code_sync._SELF_UPDATE_WATCH_TIMEOUT_SECONDS", 2),
        patch("api.code_sync._SELF_UPDATE_WATCH_POLL_SECONDS", 1),
    ):
        assert _run(_await_self_update_completion(_FIRED_AT)) is None


def test_a_stubbed_verdict_reader_does_not_refuse_every_completion() -> None:
    """The rotated check must not trip on a Mock's blanket truthiness.

    `getattr(mock, "from_rotated_log", False)` returns a Mock, which is truthy,
    so a truthiness test here would refuse every completion and hang the stage.
    """
    with patch("services.self_update_log_reader.read_self_update_verdict", return_value=MagicMock()):
        assert _completion_is_from_a_rotated_log() is False


# #14703 — a wedged job must not lock out every future update
# ---------------------------------------------------------------------------


def _job_at(progress_at: str | None, created_at: str = "2026-08-21T12:00:00+00:00") -> UpdateAllJob:
    job = _job_with_fleet_stage()
    job.status = "running"
    job.created_at = created_at
    job.last_progress_at = progress_at
    return job


def test_a_job_that_stopped_advancing_is_stale() -> None:
    """The defect: this job used to 409 every future update forever."""
    long_ago = (datetime.now(timezone.utc) - timedelta(seconds=_UPDATE_ALL_STALE_SECONDS + 60)).isoformat()
    assert _job_is_stale(_job_at(long_ago)) is True


def test_a_job_still_making_progress_is_not_stale() -> None:
    """The dangerous direction: reaping live work would be worse than the lockout."""
    just_now = datetime.now(timezone.utc).isoformat()
    assert _job_is_stale(_job_at(just_now)) is False


def test_a_long_fleet_update_stays_fresh_while_nodes_progress() -> None:
    """Staleness is judged on progress, not age.

    A job created hours ago is fine as long as it keeps stamping — otherwise a
    legitimate update across many nodes would be reaped mid-run.
    """
    old_creation = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    recent_progress = datetime.now(timezone.utc).isoformat()
    assert _job_is_stale(_job_at(recent_progress, created_at=old_creation)) is False


def test_falls_back_to_created_at_when_nothing_stamped() -> None:
    long_ago = (datetime.now(timezone.utc) - timedelta(seconds=_UPDATE_ALL_STALE_SECONDS + 60)).isoformat()
    assert _job_is_stale(_job_at(None, created_at=long_ago)) is True


def test_an_unreadable_timestamp_is_never_stale() -> None:
    """A bad reading must not retire a job that may be running."""
    assert _job_is_stale(_job_at("not-a-timestamp")) is False
    assert _job_is_stale(_job_at(None, created_at="")) is False


def test_fleet_stage_stamps_progress_per_node() -> None:
    """Without this the stamps exist but nothing sets them during the long stage."""
    job = _job_with_fleet_stage()
    job.last_progress_at = None
    stamps = []

    async def _fake_sync(executor, node_id, job, stage, slm_own_ip):
        stamps.append(job.last_progress_at)
        job.completed_fleet_nodes += 1
        return True

    with (
        patch("api.code_sync._sync_fleet_node", side_effect=_fake_sync),
        patch("api.code_sync.get_playbook_executor", return_value=MagicMock()),
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        mock_settings.external_url = "http://10.0.0.1"
        _run(_run_fleet_stage(job, ["node-a", "node-b"]))

    assert all(s is not None for s in stamps), f"a node ran before any progress was stamped: {stamps}"
    assert stamps[0] != stamps[1] or job.last_progress_at is not None


# ---------------------------------------------------------------------------
# #14703 review: the retirement path itself, not just the staleness predicate
# ---------------------------------------------------------------------------


def _stale_job() -> UpdateAllJob:
    """A job that `_job_is_stale` will judge stale."""
    long_ago = (datetime.now(timezone.utc) - timedelta(seconds=_UPDATE_ALL_STALE_SECONDS + 60)).isoformat()
    return _job_at(long_ago)


@contextlib.contextmanager
def _no_real_orchestration():
    """Keep the endpoint from launching a real update while under test."""
    import api.code_sync as cs

    started = []

    async def _fake_orchestration(job, _db):
        started.append(job.job_id)
        await asyncio.sleep(0)

    original = cs._run_update_all_orchestration
    cs._run_update_all_orchestration = _fake_orchestration
    try:
        yield started
    finally:
        cs._run_update_all_orchestration = original
        cs._update_all_task = None
        _clear_update_all_job()


def test_a_live_resume_plan_blocks_retiring_a_stale_looking_job() -> None:
    """The #14703 review's critical finding, as a test.

    `slm_self_update` detaches its playbook and stops stamping progress the
    moment it fires, so a healthy long self-update is indistinguishable from a
    dead job by timestamps alone. Retirement used to run first and call
    `_clear_resume_plan()`, deleting the very evidence the C3-b guard reads —
    so a second full orchestration could start against nodes the first was
    still updating.
    """
    import api.code_sync as cs

    cleared = []

    async def _plan_exists():
        return True

    async def _record_clear():
        cleared.append(True)

    with _no_real_orchestration() as started:
        _set_update_all_job(_stale_job())
        with (
            patch.object(cs, "_check_persisted_plan_exists", _plan_exists),
            patch.object(cs, "_clear_resume_plan", _record_clear),
        ):
            with pytest.raises(HTTPException) as excinfo:
                _run(start_update_all({}))

        assert excinfo.value.status_code == 409
        assert not cleared, "a live resume plan must never be cleared by retirement"
        assert not started, "no orchestration may start while a self-update is in flight"


def test_a_stale_job_is_still_retired_when_no_plan_is_live() -> None:
    """The fix must not disable the feature it is protecting.

    Without this, moving the plan check earlier could simply block every
    retirement and silently restore the #14703 lockout.
    """
    import api.code_sync as cs

    async def _no_plan():
        return False

    async def _noop_clear():
        return None

    with _no_real_orchestration() as started:
        _set_update_all_job(_stale_job())
        with (
            patch.object(cs, "_check_persisted_plan_exists", _no_plan),
            patch.object(cs, "_clear_resume_plan", _noop_clear),
        ):
            job = _run(start_update_all({}))
            _run(asyncio.sleep(0))

        assert job.status == "pending", "a fresh job should have been created"
        assert started == [job.job_id], "exactly the new job should have been orchestrated"


def test_concurrent_starts_only_create_one_orchestration() -> None:
    """Two POSTs against the same stale job must not both start a run.

    The decide-retire-create sequence awaits in the middle, so without a lock
    both callers read the same stale job, both retire it, and both launch an
    orchestration against the same live nodes — strictly worse than the
    lockout retirement exists to fix.
    """
    import api.code_sync as cs

    async def _no_plan():
        # Yield control so a second caller can interleave here if the lock is absent.
        await asyncio.sleep(0)
        return False

    async def _noop_clear():
        await asyncio.sleep(0)

    async def _drive():
        _set_update_all_job(_stale_job())
        results = await asyncio.gather(start_update_all({}), start_update_all({}), return_exceptions=True)
        await asyncio.sleep(0)
        return results

    with _no_real_orchestration() as started:
        with (
            patch.object(cs, "_check_persisted_plan_exists", _no_plan),
            patch.object(cs, "_clear_resume_plan", _noop_clear),
        ):
            results = _run(_drive())

        accepted = [r for r in results if isinstance(r, UpdateAllJob)]
        rejected = [r for r in results if isinstance(r, HTTPException)]

        assert len(accepted) == 1, f"exactly one caller may start a run, got {len(accepted)}: {results}"
        assert len(rejected) == 1 and rejected[0].status_code == 409
        assert len(started) <= 1, f"double orchestration: {started}"
