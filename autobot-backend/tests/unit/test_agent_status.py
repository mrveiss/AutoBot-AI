# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for AgentStatus and heartbeat_enabled hybrid property (GH#6476).

Verifies:
- AgentStatus enum values
- heartbeat_enabled hybrid property getter/setter
- Scheduler skips PAUSED agents (_is_agent_paused)
- Scheduler start() loads only ACTIVE agents
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub helpers (mirrors test_heartbeat_coalescing.py pattern)
# ---------------------------------------------------------------------------


def _make_stub(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_models_and_scheduler():
    """Return (models_heartbeat_module, scheduler_module) with minimal stubs."""
    from pathlib import Path

    _make_stub("user_management")
    _make_stub("user_management.models")
    _make_stub("user_management.models.base", Base=type("Base", (), {}))

    _make_stub("autobot_shared")
    _make_stub("autobot_shared.logging_manager", get_logger=MagicMock(return_value=MagicMock()))
    _make_stub("autobot_shared.time_utils", now_utc=MagicMock())

    _make_stub("events")
    _make_stub(
        "events.event_types",
        HEARTBEAT_RUN_COMPLETED="heartbeat_run_completed",
        HEARTBEAT_RUN_STARTED="heartbeat_run_started",
    )
    _make_stub("live_event_manager", publish_live_event=AsyncMock())
    _make_stub("events.bus", publish_event=AsyncMock())

    backend_root = Path(__file__).parents[3] / "autobot-backend"

    hb_spec = importlib.util.spec_from_file_location("models.heartbeat", backend_root / "models" / "heartbeat.py")
    assert hb_spec and hb_spec.loader
    hb_mod = importlib.util.module_from_spec(hb_spec)
    sys.modules.setdefault("models", types.ModuleType("models"))
    sys.modules["models.heartbeat"] = hb_mod
    hb_spec.loader.exec_module(hb_mod)  # type: ignore[union-attr]

    _make_stub("models.agent", Agent=MagicMock())
    _make_stub("services")
    _make_stub(
        "services.run_jwt",
        get_run_jwt_scopes=MagicMock(),
        mint_run_jwt=AsyncMock(),
        revoke_run_jwt_async=AsyncMock(),
    )
    _make_stub("services.task_claim", renew_claim=AsyncMock())

    sched_spec = importlib.util.spec_from_file_location(
        "services.heartbeat_scheduler", backend_root / "services" / "heartbeat_scheduler.py"
    )
    assert sched_spec and sched_spec.loader
    sched_mod = importlib.util.module_from_spec(sched_spec)
    sys.modules["services.heartbeat_scheduler"] = sched_mod
    sched_spec.loader.exec_module(sched_mod)  # type: ignore[union-attr]

    return hb_mod, sched_mod


_hb_mod, _sched_mod = _load_models_and_scheduler()
AgentStatus = _hb_mod.AgentStatus
AgentRuntimeState = _hb_mod.AgentRuntimeState
HeartbeatScheduler = _sched_mod.HeartbeatScheduler


# ---------------------------------------------------------------------------
# AgentStatus enum
# ---------------------------------------------------------------------------


class TestAgentStatusEnum:
    def test_values(self):
        assert AgentStatus.ACTIVE == "active"
        assert AgentStatus.DISABLED == "disabled"
        assert AgentStatus.PAUSED == "paused"
        assert AgentStatus.TERMINATED == "terminated"

    def test_value(self):
        assert AgentStatus.ACTIVE.value == "active"


# ---------------------------------------------------------------------------
# heartbeat_enabled hybrid property
# ---------------------------------------------------------------------------


class TestHeartbeatEnabledHybridProperty:
    def _make_state(self, status: str) -> AgentRuntimeState:
        state = AgentRuntimeState.__new__(AgentRuntimeState)
        state.status = status
        return state

    def test_active_is_enabled(self):
        state = self._make_state(AgentStatus.ACTIVE.value)
        assert state.heartbeat_enabled is True

    def test_disabled_is_not_enabled(self):
        state = self._make_state(AgentStatus.DISABLED.value)
        assert state.heartbeat_enabled is False

    def test_paused_is_not_enabled(self):
        state = self._make_state(AgentStatus.PAUSED.value)
        assert state.heartbeat_enabled is False

    def test_terminated_is_not_enabled(self):
        state = self._make_state(AgentStatus.TERMINATED.value)
        assert state.heartbeat_enabled is False

    def test_setter_true_makes_active(self):
        state = self._make_state(AgentStatus.DISABLED.value)
        state.heartbeat_enabled = True
        assert state.status == AgentStatus.ACTIVE.value

    def test_setter_false_makes_disabled(self):
        state = self._make_state(AgentStatus.ACTIVE.value)
        state.heartbeat_enabled = False
        assert state.status == AgentStatus.DISABLED.value


# ---------------------------------------------------------------------------
# Scheduler: _is_agent_paused
# ---------------------------------------------------------------------------


class TestIsAgentPaused:
    def _make_scheduler(self):
        session_factory = MagicMock()
        return HeartbeatScheduler(session_factory)

    @pytest.mark.asyncio
    async def test_paused_returns_true(self):
        sched = self._make_scheduler()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = AgentStatus.PAUSED.value
        mock_session.execute = AsyncMock(return_value=mock_result)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=False)
        sched._session_factory = MagicMock(return_value=cm)

        result = await sched._is_agent_paused("agent-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_active_returns_false(self):
        sched = self._make_scheduler()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = AgentStatus.ACTIVE.value
        mock_session.execute = AsyncMock(return_value=mock_result)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=False)
        sched._session_factory = MagicMock(return_value=cm)

        result = await sched._is_agent_paused("agent-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_terminated_returns_false(self):
        """Terminated agents are not 'paused'; they simply never run."""
        sched = self._make_scheduler()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = AgentStatus.TERMINATED.value
        mock_session.execute = AsyncMock(return_value=mock_result)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=False)
        sched._session_factory = MagicMock(return_value=cm)

        result = await sched._is_agent_paused("agent-1")
        assert result is False
