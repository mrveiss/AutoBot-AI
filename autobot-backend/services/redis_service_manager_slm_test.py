# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for RedisServiceManager SLM API proxying (Issue #933)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.redis_service_manager as redis_service_manager_module
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


def _make_http_client(response_cm=None, side_effect=None):
    """Build a mock pooled HTTP client whose ``tracked_request()`` returns
    *response_cm* (or raises *side_effect*).

    #12979: RedisServiceManager now issues requests via
    ``get_http_client().tracked_request(...)`` instead of a raw
    ``aiohttp.ClientSession()`` — mock that entry point instead.
    """
    client = MagicMock()
    if side_effect is not None:
        client.tracked_request = MagicMock(side_effect=side_effect)
    else:
        client.tracked_request = MagicMock(return_value=response_cm)
    return client


class TestInit:
    """Tests for RedisServiceManager initialisation (Issue #933)."""

    def test_no_longer_raises_not_implemented(self) -> None:
        mgr = RedisServiceManager()
        assert mgr is not None

    def test_defaults_from_env(self, monkeypatch) -> None:
        # _DEFAULT_SLM_URL / _DEFAULT_REDIS_NODE_ID are resolved once at module
        # import time from ssot_config (itself an lru_cache'd singleton), so
        # monkeypatch.setenv() after import has no effect on them. Patch the
        # module-level constants directly to exercise the actual fallback path.
        monkeypatch.setattr(redis_service_manager_module, "_DEFAULT_SLM_URL", "https://slm.test")
        monkeypatch.setattr(redis_service_manager_module, "_DEFAULT_REDIS_NODE_ID", "04-DBs")
        mgr = RedisServiceManager()
        assert mgr.slm_url == "https://slm.test"
        assert mgr.slm_node_id == "04-DBs"

    def test_explicit_params_override_env(self) -> None:
        mgr = RedisServiceManager(
            slm_url="https://override.example.com",
            slm_node_id="custom-node",
        )
        assert mgr.slm_url == "https://override.example.com"
        assert mgr.slm_node_id == "custom-node"

    def test_trailing_slash_stripped(self) -> None:
        mgr = RedisServiceManager(slm_url="https://slm.example.com/")
        assert mgr.slm_url == "https://slm.example.com"


class TestSlmServiceAction:
    """Tests for _slm_service_action (Issue #933)."""

    @pytest.mark.asyncio
    async def test_start_calls_correct_url(self, manager) -> None:
        resp_cm = _make_response({"success": True, "message": "started"})
        client = _make_http_client(resp_cm)
        with patch(
            "services.redis_service_manager.get_http_client",
            return_value=client,
        ):
            ok, msg = await manager._slm_service_action("start")
        assert ok is True
        assert msg == "started"
        client.tracked_request.assert_called_once()
        call_args = client.tracked_request.call_args
        assert call_args[0][0] == "POST"
        assert "04-Databases/services/redis-stack-server/start" in call_args[0][1]
        assert call_args.kwargs["ssl"] is False

    @pytest.mark.asyncio
    async def test_stop_calls_correct_url(self, manager) -> None:
        resp_cm = _make_response({"success": True, "message": "stopped"})
        client = _make_http_client(resp_cm)
        with patch(
            "services.redis_service_manager.get_http_client",
            return_value=client,
        ):
            ok, _msg = await manager._slm_service_action("stop")
        called_url = client.tracked_request.call_args[0][1]
        assert called_url.endswith("/stop")
        assert ok is True

    @pytest.mark.asyncio
    async def test_restart_calls_correct_url(self, manager) -> None:
        resp_cm = _make_response({"success": True, "message": "restarted"})
        client = _make_http_client(resp_cm)
        with patch(
            "services.redis_service_manager.get_http_client",
            return_value=client,
        ):
            ok, _msg = await manager._slm_service_action("restart")
        called_url = client.tracked_request.call_args[0][1]
        assert called_url.endswith("/restart")
        assert ok is True

    @pytest.mark.asyncio
    async def test_raises_when_no_slm_url(self) -> None:
        mgr = RedisServiceManager(slm_url="", slm_node_id="04-Databases")
        with pytest.raises(RedisConnectionError, match="SLM_URL not configured"):
            await mgr._slm_service_action("start")

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, manager) -> None:
        client = _make_http_client(side_effect=Exception("connection refused"))
        with patch(
            "services.redis_service_manager.get_http_client",
            return_value=client,
        ):
            with pytest.raises(RedisConnectionError):
                await manager._slm_service_action("start")


class TestSlmGetServiceStatus:
    """Tests for _slm_get_service_status (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_running_when_service_found(self, manager) -> None:
        data = {"services": [{"service_name": "redis-stack-server", "status": "running"}]}
        resp_cm = _make_response(data)
        client = _make_http_client(resp_cm)
        with patch(
            "services.redis_service_manager.get_http_client",
            return_value=client,
        ):
            status = await manager._slm_get_service_status()
        assert status == "running"

    @pytest.mark.asyncio
    async def test_returns_unknown_when_no_services(self, manager) -> None:
        resp_cm = _make_response({"services": []})
        client = _make_http_client(resp_cm)
        with patch(
            "services.redis_service_manager.get_http_client",
            return_value=client,
        ):
            status = await manager._slm_get_service_status()
        assert status == "unknown"

    @pytest.mark.asyncio
    async def test_returns_unknown_when_no_slm_url(self) -> None:
        mgr = RedisServiceManager(slm_url="", slm_node_id="04-Databases")
        status = await mgr._slm_get_service_status()
        assert status == "unknown"

    @pytest.mark.asyncio
    async def test_returns_unknown_on_http_error(self, manager) -> None:
        client = _make_http_client(side_effect=Exception("timeout"))
        with patch(
            "services.redis_service_manager.get_http_client",
            return_value=client,
        ):
            status = await manager._slm_get_service_status()
        assert status == "unknown"


class TestCheckRedisConnectivity:
    """Tests for _check_redis_connectivity (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_ping(self, manager) -> None:
        # _check_redis_connectivity imports get_async_redis_client locally from
        # autobot_shared.redis_client (not a services.redis_service_manager
        # module attribute), so the patch target must be the source module.
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            AsyncMock(return_value=mock_client),
        ):
            connected, response_ms = await manager._check_redis_connectivity()
        assert connected is True
        assert response_ms >= 0

    @pytest.mark.asyncio
    async def test_returns_false_on_ping_failure(self, manager) -> None:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("connection refused"))
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            AsyncMock(return_value=mock_client),
        ):
            connected, response_ms = await manager._check_redis_connectivity()
        assert connected is False
        assert response_ms == 0.0
