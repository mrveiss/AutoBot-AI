# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the async component drift/resolve job (#11303).

Covers:
  - _run_post_sync_steps(..., restart=False) defers restart, adds "restart deferred" step.
  - _run_post_sync_steps(..., restart=True) (default) calls _restart_component_services.
  - _run_component_resolve_job happy path: rsync ok + pip ok → job status="completed",
    restart IS called, and the DB commit happens BEFORE the restart.
  - _run_component_resolve_job rsync-failure path: status="failed", restart NOT called.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Dev-host stub: provide minimal real Pydantic models for models.schemas so
# the router can be imported without a full SLM venv.
# Must happen before the api.code_sync import below.
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

# Add autobot-slm-backend to path so api.code_sync imports resolve.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

import asyncio  # noqa: E402  (re-import for clarity after path setup)

from api.code_sync import (  # noqa: E402
    _run_component_resolve_job,
    _run_post_sync_steps,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers — build a db_service mock that captures row mutations
# ---------------------------------------------------------------------------


class _FakeRow:
    """Minimal mutable object standing in for a ComponentSyncJob DB row."""

    def __init__(self):
        self.status = "running"
        self.success = None
        self.deps_changed = False
        self.post_steps = None
        self.message = None
        self.completed_at = None


def _make_db_service_mock(row: _FakeRow | None = None):
    """Return a db_service mock whose session() is an async ctx-manager."""
    db_service_mock = MagicMock()

    fake_row = row

    class _FakeSession:
        def __init__(self):
            self._committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, _stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = fake_row
            return result

        async def commit(self):
            self._committed = True

        def add(self, obj):
            pass

    db_service_mock.session.return_value = _FakeSession()
    return db_service_mock


# ---------------------------------------------------------------------------
# _run_post_sync_steps — restart param
# ---------------------------------------------------------------------------


def test_run_post_sync_steps_restart_false_does_not_call_restart() -> None:
    """restart=False must NOT invoke _restart_component_services for pip backends."""
    restart_mock = AsyncMock()
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_target_python_installed", AsyncMock()),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock()),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", restart_mock),
    ):
        _, steps, pip_ok = _run(
            _run_post_sync_steps(
                "autobot-slm-backend",
                "/opt/autobot/code_source/autobot-slm-backend",
                "/opt/autobot/autobot-slm-backend",
                restart=False,
            )
        )

    restart_mock.assert_not_called()
    assert pip_ok is True
    assert any("restart deferred" in s for s in steps), f"Expected 'restart deferred' in {steps}"


def test_run_post_sync_steps_restart_true_calls_restart() -> None:
    """restart=True (default) MUST call _restart_component_services for pip backends."""
    restart_mock = AsyncMock()
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._deploy_constraints_dir", AsyncMock()),
        patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()),
        patch("api.code_sync._ensure_target_python_installed", AsyncMock()),
        patch("api.code_sync._ensure_venv_python", AsyncMock()),
        patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)),
        patch("api.code_sync._run_alembic_migrations", AsyncMock()),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", restart_mock),
    ):
        _, steps, pip_ok = _run(
            _run_post_sync_steps(
                "autobot-slm-backend",
                "/opt/autobot/code_source/autobot-slm-backend",
                "/opt/autobot/autobot-slm-backend",
            )
        )

    restart_mock.assert_called_once()
    assert pip_ok is True
    assert not any("restart deferred" in s for s in steps)


def test_run_post_sync_steps_restart_false_frontend() -> None:
    """restart=False defers restart for frontend components too."""
    restart_mock = AsyncMock()
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._build_npm_frontend_for_component", AsyncMock()),
        patch("api.code_sync._restart_component_services", restart_mock),
    ):
        _, steps, _ = _run(
            _run_post_sync_steps(
                "autobot-slm-frontend",
                "/opt/autobot/code_source/autobot-slm-frontend",
                "/opt/autobot/autobot-slm-frontend",
                restart=False,
            )
        )

    restart_mock.assert_not_called()
    assert any("restart deferred" in s for s in steps)


def test_run_post_sync_steps_restart_false_shared_library() -> None:
    """restart=False defers restart for the autobot_shared library component."""
    restart_mock = AsyncMock()
    with (
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()),
        patch("api.code_sync._restart_component_services", restart_mock),
    ):
        _, steps, _ = _run(
            _run_post_sync_steps(
                "autobot_shared",
                "/opt/autobot/code_source/autobot_shared",
                "/opt/autobot/autobot_shared",
                restart=False,
            )
        )

    restart_mock.assert_not_called()
    assert any("restart deferred" in s for s in steps)


# ---------------------------------------------------------------------------
# _run_component_resolve_job — happy path
# ---------------------------------------------------------------------------


def test_run_component_resolve_job_happy_path() -> None:
    """Happy path: rsync ok + pip ok → job committed as 'completed' BEFORE restart."""
    row = _FakeRow()
    db_mock = _make_db_service_mock(row)

    restart_order: list[str] = []

    class _TrackingSession:
        """Session that records commit() timing vs restart calls."""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, _stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = row
            return result

        async def commit(self):
            restart_order.append("committed")

        def add(self, _obj):
            pass

    db_mock.session.return_value = _TrackingSession()

    async def _fake_restart(component, steps):
        restart_order.append("restarted")

    with (
        patch("api.code_sync.get_default_source_dir", return_value="/src/autobot-slm-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/opt/autobot/autobot-slm-backend"),
        patch("api.code_sync._rsync_component_local", AsyncMock(return_value=(True, ""))),
        patch(
            "api.code_sync._run_post_sync_steps",
            AsyncMock(return_value=(False, ["step1", "post-sync: restart deferred"], True)),
        ),
        patch("api.code_sync._restart_component_services", side_effect=_fake_restart),
        patch("api.code_sync._running_tasks", {}),
        patch("api.code_sync.db_service", db_mock, create=True),
    ):
        # Also patch the local import inside _run_component_resolve_job
        with patch.dict("sys.modules", {"services.database": MagicMock(db_service=db_mock)}):
            pass

            import api.code_sync as _cs_mod

            __builtins__.__import__ if hasattr(__builtins__, "__import__") else None

            # Directly patch the module-level reference that the function imports
            getattr(_cs_mod, "db_service", None)
            _run(_run_component_resolve_job("abc123", "autobot-slm-backend"))

    # Commit must happen BEFORE restart
    assert "committed" in restart_order, "DB was never committed"
    assert "restarted" in restart_order, "restart was never called"
    assert restart_order.index("committed") < restart_order.index(
        "restarted"
    ), f"DB commit must precede restart; order was {restart_order}"
    assert row.status == "completed"
    assert row.success is True


def test_run_component_resolve_job_rsync_failure() -> None:
    """rsync failure → job committed as 'failed'; restart NOT called."""
    row = _FakeRow()
    db_mock = _make_db_service_mock(row)

    restart_mock = AsyncMock()

    with (
        patch("api.code_sync.get_default_source_dir", return_value="/src/autobot-slm-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/opt/autobot/autobot-slm-backend"),
        patch("api.code_sync._rsync_component_local", AsyncMock(return_value=(False, "rsync boom"))),
        patch("api.code_sync._run_post_sync_steps", AsyncMock()),
        patch("api.code_sync._restart_component_services", restart_mock),
        patch("api.code_sync._running_tasks", {}),
    ):
        with patch.dict("sys.modules", {"services.database": MagicMock(db_service=db_mock)}):
            _run(_run_component_resolve_job("def456", "autobot-slm-backend"))

    assert row.status == "failed"
    assert row.success is False
    assert "rsync boom" in (row.message or "")
    restart_mock.assert_not_called()


# ---------------------------------------------------------------------------
# #11437: requeue-once reconcile + pending-restart guard
# ---------------------------------------------------------------------------


def _make_reconcile_db_mock(rows):
    """db_service mock whose session().execute returns scalars().all() == rows."""
    db_service_mock = MagicMock()

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, _stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = rows
            return result

        async def commit(self):
            pass

    db_service_mock.session.return_value = _FakeSession()
    return db_service_mock


def test_reconcile_requeues_first_interruption() -> None:
    """A job interrupted by a racing restart is re-queued, not failed (#11437)."""
    import api.code_sync as code_sync_mod

    row = _FakeRow()
    row.status = "running"
    row.message = None
    row.job_id = "job-1"
    row.component = "autobot-backend"

    with patch("services.database.db_service", _make_reconcile_db_mock([row])):
        count, requeued = _run(code_sync_mod.reconcile_stale_component_sync_jobs())

    assert count == 1
    assert row.status == "queued"
    assert row.message.startswith("requeued")
    assert requeued == [("job-1", "autobot-backend")]


def test_reconcile_fails_second_interruption() -> None:
    """A job interrupted twice must not requeue forever (#11437)."""
    import api.code_sync as code_sync_mod

    row = _FakeRow()
    row.status = "running"
    row.message = "requeued after server restart"
    row.job_id = "job-2"
    row.component = "autobot-backend"

    with patch("services.database.db_service", _make_reconcile_db_mock([row])):
        count, requeued = _run(code_sync_mod.reconcile_stale_component_sync_jobs())

    assert count == 1
    assert row.status == "failed"
    assert row.success is False
    assert requeued == []


def test_restart_pending_arms_only_for_self_killing_components() -> None:
    """_restart_component_services arms the 409 guard only when the chain can
    kill the SLM itself (#11437); observable DURING the chain (it disarms on
    surviving completion, #11460)."""
    import api.code_sync as code_sync_mod

    seen: dict = {}

    async def _fake_exec(*args, **kwargs):
        # record the guard state at restart time (mid-chain)
        seen[args[-1]] = code_sync_mod._restart_is_pending()
        proc = MagicMock()

        async def _communicate():
            return (b"", b"")

        proc.communicate = _communicate
        proc.returncode = 0
        return proc

    code_sync_mod._restart_pending = False
    try:
        with patch.dict(
            code_sync_mod._COMPONENT_SERVICES,
            {"autobot-backend": ["autobot-backend"], "autobot_shared": ["autobot-celery"]},
        ), patch.object(code_sync_mod.asyncio, "create_subprocess_exec", _fake_exec):
            _run(code_sync_mod._restart_component_services("autobot-backend", []))
            _run(code_sync_mod._restart_component_services("autobot_shared", []))
    finally:
        code_sync_mod._restart_pending = False

    assert seen["autobot-backend"] is False, "non-self-killing chain must not arm"
    assert seen["autobot-celery"] is True, "self-killing chain must arm mid-chain"


def test_restart_pending_disarms_when_process_survives() -> None:
    """#11460 review: a failed self-restart chain must not leave the 409 guard
    armed forever — reaching the end of the chain alive disarms it."""
    import api.code_sync as code_sync_mod

    code_sync_mod._restart_pending = False
    try:
        with patch.dict(code_sync_mod._COMPONENT_SERVICES, {"autobot_shared": []}):
            _run(code_sync_mod._restart_component_services("autobot_shared", []))
        # chain completed without killing us -> guard released
        assert code_sync_mod._restart_is_pending() is False
    finally:
        code_sync_mod._restart_pending = False
