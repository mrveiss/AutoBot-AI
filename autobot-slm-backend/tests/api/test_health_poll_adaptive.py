# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11458: adaptive post-restart health-poll window.

_wait_component_healthy uses the full _HEALTH_POLL_TIMEOUT only when the venv was
just recreated (cold py3.14 interpreter); a warm restart uses the shorter
_FAST_HEALTH_POLL_TIMEOUT so fast resyncs don't burn the full window on a silent
hang. _ensure_venv_python signals recreation via its bool return so the caller
can pick the window. Rollback stays gated on a genuine systemd failure (not the
timeout), so the shorter window never reverts a slow-but-healthy deploy.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Minimal real Pydantic models for models.schemas so the router imports without a
# full SLM venv (mirrors the sibling code-sync tests).
if "models" not in sys.modules or isinstance(sys.modules.get("models"), MagicMock):
    from pydantic import BaseModel as _BM

    def _pydantic_stub(name: str) -> type:
        return type(name, (_BM,), {})

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

import asyncio  # noqa: E402

import api.code_sync as cs  # noqa: E402
from api.code_sync import _ensure_venv_python, _wait_component_healthy  # noqa: E402


def _run(coro):
    # Dedicated loop so tests that patch api.code_sync.asyncio.get_event_loop
    # (to control the health-poll deadline) don't also hijack the driver here.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _immediate_deadline_loop():
    """A fake event loop whose time() jumps past any deadline on the 2nd call, so
    _wait_component_healthy computes its deadline then exits the poll at once."""
    loop = MagicMock()
    loop.time.side_effect = [1000.0, 9.0e18]
    return loop


# ---------------------------------------------------------------------------
# _wait_component_healthy — adaptive window
# ---------------------------------------------------------------------------


def test_slow_start_uses_full_timeout_window() -> None:
    """slow_start=True (venv recreated) → the full _HEALTH_POLL_TIMEOUT window."""
    steps: list[str] = []
    with (
        patch.object(cs, "_HEALTH_POLL_TIMEOUT", 180.0),
        patch.object(cs, "_FAST_HEALTH_POLL_TIMEOUT", 60.0),
        patch("api.code_sync.asyncio.get_event_loop", return_value=_immediate_deadline_loop()),
        patch("api.code_sync._is_systemd_unit_failed", AsyncMock(return_value=False)),
    ):
        healthy = _run(_wait_component_healthy("autobot-backend", steps, slow_start=True))
    # timeout without a systemd failure → proceed (True), and the recorded window is 180s.
    assert healthy is True
    assert any("within 180s" in s for s in steps), steps


def test_warm_restart_uses_fast_timeout_window() -> None:
    """slow_start=False (warm restart) → the shorter _FAST_HEALTH_POLL_TIMEOUT window."""
    steps: list[str] = []
    with (
        patch.object(cs, "_HEALTH_POLL_TIMEOUT", 180.0),
        patch.object(cs, "_FAST_HEALTH_POLL_TIMEOUT", 60.0),
        patch("api.code_sync.asyncio.get_event_loop", return_value=_immediate_deadline_loop()),
        patch("api.code_sync._is_systemd_unit_failed", AsyncMock(return_value=False)),
    ):
        healthy = _run(_wait_component_healthy("autobot-backend", steps, slow_start=False))
    assert healthy is True
    assert any("within 60s" in s for s in steps), steps


def test_default_slow_start_is_false() -> None:
    """The default (no slow_start passed) is the fast window — safe for callers
    that never recreate a venv (frontend / shared-library restarts)."""
    steps: list[str] = []
    with (
        patch.object(cs, "_HEALTH_POLL_TIMEOUT", 180.0),
        patch.object(cs, "_FAST_HEALTH_POLL_TIMEOUT", 60.0),
        patch("api.code_sync.asyncio.get_event_loop", return_value=_immediate_deadline_loop()),
        patch("api.code_sync._is_systemd_unit_failed", AsyncMock(return_value=False)),
    ):
        _run(_wait_component_healthy("autobot-backend", steps))
    assert any("within 60s" in s for s in steps), steps


def test_systemd_failure_rolls_back_regardless_of_window() -> None:
    """A genuine systemd 'failed' state returns False (→ rollback) even on the
    fast window — the timeout length never gates rollback."""
    steps: list[str] = []
    with (patch("api.code_sync._is_systemd_unit_failed", AsyncMock(return_value=True)),):
        healthy = _run(_wait_component_healthy("autobot-backend", steps, slow_start=False))
    assert healthy is False


# ---------------------------------------------------------------------------
# _ensure_venv_python — recreation signal
# ---------------------------------------------------------------------------


def test_ensure_venv_returns_false_for_non_pip_component() -> None:
    """A component with no Python target (e.g. frontend) never recreates a venv."""
    steps: list[str] = []
    assert _run(_ensure_venv_python("autobot-slm-frontend", steps)) is False


def test_ensure_venv_returns_true_when_recreated() -> None:
    """A missing venv with the target interpreter present → recreated → True."""
    steps: list[str] = []
    component = next(iter(cs._COMPONENT_PIP_PATHS))  # a real pip-backed component
    with (
        patch("api.code_sync.shutil.which", return_value="/usr/bin/python3.14"),
        patch("api.code_sync._recreate_venv", AsyncMock()),
        patch("api.code_sync.Path.exists", return_value=False),
    ):
        recreated = _run(_ensure_venv_python(component, steps))
    assert recreated is True
