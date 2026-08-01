# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the SLM self-update skip-decision signal (#12202).

Root cause: the update-all pipeline's stage 2 (code_source_pull) advances
/opt/autobot/code_source HEAD to remote_commit BEFORE stage 3
(slm_self_update) runs its "already current" check. The old
_get_slm_deployed_commit() read git_tracker.get_local_commit() — which IS
code_source HEAD — so the check was always remote == remote and the SLM
control-plane install (/opt/autobot/autobot-slm-backend) was never
redeployed.

Fix: _get_slm_deployed_commit() now reads a ``.deployed_commit`` marker file
written into the INSTALL directory (get_default_deployed_dir) by the
slm_manager Ansible role right after its rsync task. Absent/unreadable marker
returns None, which is fail-safe: _run_slm_stage does NOT skip when the
deployed commit is unknown, so the self-update fires.

Covers:
  - _get_slm_deployed_commit reads the INSTALL marker, not code_source HEAD.
  - Marker absent / unreadable / empty -> None.
  - _run_slm_stage skip-decision matrix: marker == target -> SKIPS (CURRENT);
    marker != target -> FIRES; marker absent (None) -> FIRES (regression guard).
"""

from __future__ import annotations

import ast
import asyncio
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

# The dev-host has a conflicting `multipart` package that breaks FastAPI's import
# of `starlette.formparsers`. Stub it out before anything imports FastAPI so
# that test collection can proceed (same workaround as test_collect_outdated_node_ids.py).
if "multipart" in sys.modules and not hasattr(sys.modules["multipart"], "multipart"):
    sys.modules.pop("multipart", None)
_mp_stub = types.ModuleType("multipart")
_mp_stub.multipart = types.ModuleType("multipart.multipart")  # type: ignore[attr-defined]
sys.modules.setdefault("multipart", _mp_stub)
sys.modules.setdefault("multipart.multipart", _mp_stub.multipart)  # type: ignore[attr-defined]

# When conftest.py stubs `models.schemas` as a MagicMock, FastAPI cannot build
# request/response fields from MagicMock schema types at router-decoration time.
# Swap a benign `dict` in for every schema name api/code_sync.py imports from
# models.schemas, derived from the import block itself (no hand-list to rot).
_code_sync_src = (_BACKEND_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
_SCHEMA_NAMES = tuple(
    sorted(
        alias.name
        for node in ast.walk(ast.parse(_code_sync_src))
        if isinstance(node, ast.ImportFrom) and node.module == "models.schemas"
        for alias in node.names
    )
)
_schemas_stub = sys.modules.get("models.schemas")
if isinstance(_schemas_stub, MagicMock):
    for _name in _SCHEMA_NAMES:
        setattr(_schemas_stub, _name, dict)

from api.code_sync import (  # noqa: E402
    UpdateAllJob,
    UpdateAllStage,
    _get_slm_deployed_commit,
    _run_slm_stage,
    _StageStatus,
)

REMOTE_COMMIT = "deadbeef1234deadbeef1234"
SLM_IP = "10.0.1.10"


def _job() -> UpdateAllJob:
    return UpdateAllJob(
        job_id="test-job",
        status="running",
        created_at="2026-01-01T00:00:00+00:00",
        stages=[
            UpdateAllStage(name="github_fetch", status="success"),
            UpdateAllStage(name="code_source_pull", status="success"),
            UpdateAllStage(name="slm_self_update", status="pending"),
            UpdateAllStage(name="fleet_nodes"),
        ],
    )


def _db_service_mock(slm_node: Any) -> Any:
    """db_service mock whose session().execute() returns slm_node for the IP lookup."""
    db_service_ref = MagicMock()

    class _FakeCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = slm_node
            return result

    db_service_ref.session.return_value = _FakeCtx()
    return db_service_ref


# ---------------------------------------------------------------------------
# _get_slm_deployed_commit — reads the INSTALL marker, not code_source HEAD
# ---------------------------------------------------------------------------


class TestGetSlmDeployedCommit:
    @pytest.mark.asyncio
    async def test_reads_install_dir_marker_not_code_source_head(self, tmp_path):
        """Guard: the deployed commit comes from get_default_deployed_dir(), and
        get_git_tracker() (code_source HEAD, the #12202 bug) must not be consulted.
        """
        install_dir = tmp_path / "autobot-slm-backend"
        install_dir.mkdir()
        (install_dir / ".deployed_commit").write_text("installedsha0000\n", encoding="utf-8")

        with (
            patch("api.code_sync.get_default_deployed_dir", return_value=str(install_dir)) as get_dir_mock,
            patch("api.code_sync.get_git_tracker", side_effect=AssertionError("must not read code_source HEAD")),
        ):
            result = await _get_slm_deployed_commit()

        assert result == "installedsha0000"
        get_dir_mock.assert_called_once_with("autobot-slm-backend")

    @pytest.mark.asyncio
    async def test_marker_absent_returns_none(self, tmp_path):
        install_dir = tmp_path / "autobot-slm-backend"
        install_dir.mkdir()  # no .deployed_commit written

        with patch("api.code_sync.get_default_deployed_dir", return_value=str(install_dir)):
            result = await _get_slm_deployed_commit()

        assert result is None

    @pytest.mark.asyncio
    async def test_marker_empty_returns_none(self, tmp_path):
        install_dir = tmp_path / "autobot-slm-backend"
        install_dir.mkdir()
        (install_dir / ".deployed_commit").write_text("   \n", encoding="utf-8")

        with patch("api.code_sync.get_default_deployed_dir", return_value=str(install_dir)):
            result = await _get_slm_deployed_commit()

        assert result is None

    @pytest.mark.asyncio
    async def test_marker_unreadable_returns_none(self, tmp_path):
        """Install dir itself missing (unreadable path) -> None, not an exception."""
        install_dir = tmp_path / "does-not-exist"

        with patch("api.code_sync.get_default_deployed_dir", return_value=str(install_dir)):
            result = await _get_slm_deployed_commit()

        assert result is None


# ---------------------------------------------------------------------------
# _run_slm_stage — skip-decision matrix (C4)
# ---------------------------------------------------------------------------


class TestRunSlmStageSkipDecision:
    @pytest.mark.asyncio
    async def test_marker_equals_target_skips_stage(self):
        """marker == remote_commit -> stage SKIPS (status CURRENT), returns False."""
        slm_node = types.SimpleNamespace(node_id="slm-node", ip_address=SLM_IP)
        job = _job()

        with (
            patch("api.code_sync.settings") as mock_settings,
            patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value=REMOTE_COMMIT)),
            patch("api.code_sync._resolve_colocated_managed_services", AsyncMock()) as resolve_mock,
        ):
            mock_settings.external_url = f"http://{SLM_IP}"
            db_svc = _db_service_mock(slm_node)
            fired = await _run_slm_stage(job, REMOTE_COMMIT, [], db_svc)

        stage = next(s for s in job.stages if s.name == "slm_self_update")
        assert fired is False
        assert stage.status == _StageStatus.CURRENT
        resolve_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_marker_differs_from_target_fires_stage(self):
        """marker != remote_commit -> stage FIRES (not skipped), returns True."""
        slm_node = types.SimpleNamespace(node_id="slm-node", ip_address=SLM_IP)
        job = _job()

        with (
            patch("api.code_sync.settings") as mock_settings,
            patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value="oldsha0000")),
            patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
            patch("api.code_sync._persist_resume_plan", AsyncMock()) as persist_mock,
            patch("api.code_sync.asyncio.create_task") as create_task_mock,
        ):
            mock_settings.external_url = f"http://{SLM_IP}"
            db_svc = _db_service_mock(slm_node)
            fired = await _run_slm_stage(job, REMOTE_COMMIT, [], db_svc)

        stage = next(s for s in job.stages if s.name == "slm_self_update")
        assert fired is True
        assert stage.status != _StageStatus.CURRENT
        assert stage.status != _StageStatus.SKIPPED
        persist_mock.assert_awaited_once()
        create_task_mock.assert_called_once()
        # Close the (mocked) coroutine passed to create_task to avoid a
        # "coroutine was never awaited" warning from the AsyncMock call site.
        _, kwargs = create_task_mock.call_args
        coro = create_task_mock.call_args.args[0]
        if asyncio.iscoroutine(coro):
            coro.close()

    @pytest.mark.asyncio
    async def test_marker_absent_fires_stage_fail_safe(self):
        """Regression guard (#12202): marker missing/unreadable (None) must NOT
        be treated as "already current" — the stage must FIRE (fail-safe toward
        deploying), never silently skip because the signal is unknown.
        """
        slm_node = types.SimpleNamespace(node_id="slm-node", ip_address=SLM_IP)
        job = _job()

        with (
            patch("api.code_sync.settings") as mock_settings,
            patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value=None)),
            patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
            patch("api.code_sync._persist_resume_plan", AsyncMock()) as persist_mock,
            patch("api.code_sync.asyncio.create_task") as create_task_mock,
        ):
            mock_settings.external_url = f"http://{SLM_IP}"
            db_svc = _db_service_mock(slm_node)
            fired = await _run_slm_stage(job, REMOTE_COMMIT, [], db_svc)

        stage = next(s for s in job.stages if s.name == "slm_self_update")
        assert fired is True, "marker-absent must fire the self-update, not skip it (#12202 regression)"
        assert stage.status != _StageStatus.CURRENT
        persist_mock.assert_awaited_once()
        create_task_mock.assert_called_once()
        coro = create_task_mock.call_args.args[0]
        if asyncio.iscoroutine(coro):
            coro.close()
