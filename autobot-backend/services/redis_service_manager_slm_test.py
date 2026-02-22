# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration tests for RedisServiceManager SLM API proxying (Issue #933)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.redis_service_manager import RedisConnectionError, RedisServiceManager


@pytest.fixture()
def manager():
    """Create a RedisServiceManager wired to a fake SLM URL."""
    return RedisServiceManager(
        slm_url="https://slm.example.com",
        slm_node_id="04-Databases",
        service_name="redis-stack-server",
    )


def _make_response(data: dict, status: int = 200):
    """Build a mock aiohttp response context manager."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_session(response_cm):
    """Build a mock aiohttp.ClientSession context manager."""
    session = MagicMock()
    session.post = MagicMock(return_value=response_cm)
    session.get = MagicMock(return_value=response_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return session_cm, session


class TestInit:
    """Tests for RedisServiceManager initialisation (Issue #933)."""

    def test_no_longer_raises_not_implemented(self):
        mgr = RedisServiceManager()
        assert mgr is not None

    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("SLM_URL", "https://slm.test")
        monkeypatch.setenv("REDIS_NODE_ID", "04-DBs")
        mgr = RedisServiceManager()
        assert mgr.slm_url == "https://slm.test"
        assert mgr.slm_node_id == "04-DBs"

    def test_explicit_params_override_env(self):
        mgr = RedisServiceManager(
            slm_url="https://override.example.com",
            slm_node_id="custom-node",
        )
        assert mgr.slm_url == "https://override.example.com"
        assert mgr.slm_node_id == "custom-node"

    def test_trailing_slash_stripped(self):
        mgr = RedisServiceManager(slm_url="https://slm.example.com/")
        assert mgr.slm_url == "https://slm.example.com"


class TestSlmServiceAction:
    """Tests for _slm_service_action (Issue #933)."""

    @pytest.mark.asyncio
    async def test_start_calls_correct_url(self, manager):
        resp_cm = _make_response({"success": True, "message": "started"})
        session_cm, session = _make_session(resp_cm)
        with patch(
            "services.redis_service_manager.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            ok, msg = await manager._slm_service_action("start")
        assert ok is True
        assert msg == "started"
        session.post.assert_called_once()
        called_url = session.post.call_args[0][0]
        assert "04-Databases/services/redis-stack-server/start" in called_url

    @pytest.mark.asyncio
    async def test_stop_calls_correct_url(self, manager):
        resp_cm = _make_response({"success": True, "message": "stopped"})
        session_cm, session = _make_session(resp_cm)
        with patch(
            "services.redis_service_manager.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            ok, _msg = await manager._slm_service_action("stop")
        called_url = session.post.call_args[0][0]
        assert called_url.endswith("/stop")
        assert ok is True

    @pytest.mark.asyncio
    async def test_restart_calls_correct_url(self, manager):
        resp_cm = _make_response({"success": True, "message": "restarted"})
        session_cm, session = _make_session(resp_cm)
        with patch(
            "services.redis_service_manager.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            ok, _msg = await manager._slm_service_action("restart")
        called_url = session.post.call_args[0][0]
        assert called_url.endswith("/restart")
        assert ok is True

    @pytest.mark.asyncio
    async def test_raises_when_no_slm_url(self):
        mgr = RedisServiceManager(slm_url="", slm_node_id="04-Databases")
        with pytest.raises(RedisConnectionError, match="SLM_URL not configured"):
            await mgr._slm_service_action("start")

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, manager):
        session_cm, session = _make_session(None)
        session.post.side_effect = Exception("connection refused")
        with patch(
            "services.redis_service_manager.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            with pytest.raises(RedisConnectionError):
                await manager._slm_service_action("start")


class TestSlmGetServiceStatus:
    """Tests for _slm_get_service_status (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_running_when_service_found(self, manager):
        data = {
            "services": [{"service_name": "redis-stack-server", "status": "running"}]
        }
        resp_cm = _make_response(data)
        session_cm, _session = _make_session(resp_cm)
        with patch(
            "services.redis_service_manager.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            status = await manager._slm_get_service_status()
        assert status == "running"

    @pytest.mark.asyncio
    async def test_returns_unknown_when_no_services(self, manager):
        resp_cm = _make_response({"services": []})
        session_cm, _session = _make_session(resp_cm)
        with patch(
            "services.redis_service_manager.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            status = await manager._slm_get_service_status()
        assert status == "unknown"

    @pytest.mark.asyncio
    async def test_returns_unknown_when_no_slm_url(self):
        mgr = RedisServiceManager(slm_url="", slm_node_id="04-Databases")
        status = await mgr._slm_get_service_status()
        assert status == "unknown"

    @pytest.mark.asyncio
    async def test_returns_unknown_on_http_error(self, manager):
        session_cm, session = _make_session(None)
        session.get.side_effect = Exception("timeout")
        with patch(
            "services.redis_service_manager.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            status = await manager._slm_get_service_status()
        assert status == "unknown"


class TestCheckRedisConnectivity:
    """Tests for _check_redis_connectivity (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_ping(self, manager):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        with patch(
            "services.redis_service_manager.get_redis_client",
            return_value=mock_client,
        ):
            connected, response_ms = await manager._check_redis_connectivity()
        assert connected is True
        assert response_ms >= 0

    @pytest.mark.asyncio
    async def test_returns_false_on_ping_failure(self, manager):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("connection refused"))
        with patch(
            "services.redis_service_manager.get_redis_client",
            return_value=mock_client,
        ):
            connected, response_ms = await manager._check_redis_connectivity()
        assert connected is False
        assert response_ms == 0.0
