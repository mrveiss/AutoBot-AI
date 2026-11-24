# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AnalyticsMiddleware tracking and the telemetry opt-out (#9035, #21684)."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from autobot_shared.ssot_config import config
from initialization.middleware import configure_analytics
from middleware.analytics_middleware import AnalyticsMiddleware


def _build_app(controller) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AnalyticsMiddleware, analytics_controller=controller)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    await asyncio.sleep(0.05)  # let the fire-and-forget tracking task finish
    return response


@pytest.fixture
def controller() -> AsyncMock:
    return AsyncMock()


async def test_tracks_api_calls_when_telemetry_enabled(controller, monkeypatch):
    monkeypatch.setattr(config.telemetry, "enabled", True)
    response = await _get(_build_app(controller), "/api/ping")
    assert response.status_code == 200
    controller.track_api_call.assert_awaited_once()
    endpoint, _elapsed, status = controller.track_api_call.await_args.args
    assert (endpoint, status) == ("GET /api/ping", 200)
    assert response.headers["X-Tracked-Analytics"] == "true"
    assert response.headers["X-Response-Time"].endswith("s")


async def test_no_tracking_and_no_header_when_telemetry_disabled(controller, monkeypatch):
    monkeypatch.setattr(config.telemetry, "enabled", False)
    response = await _get(_build_app(controller), "/api/ping")
    assert response.status_code == 200
    controller.track_api_call.assert_not_awaited()
    assert "X-Tracked-Analytics" not in response.headers
    assert "X-Response-Time" not in response.headers


async def test_non_api_paths_are_untouched(controller, monkeypatch):
    monkeypatch.setattr(config.telemetry, "enabled", True)
    response = await _get(_build_app(controller), "/health")
    assert response.status_code == 200
    controller.track_api_call.assert_not_awaited()
    assert "X-Tracked-Analytics" not in response.headers
    assert "X-Response-Time" not in response.headers


async def test_a_failing_controller_never_breaks_the_request(controller, monkeypatch):
    monkeypatch.setattr(config.telemetry, "enabled", True)
    controller.track_api_call.side_effect = RuntimeError("redis down")
    response = await _get(_build_app(controller), "/api/ping")
    assert response.status_code == 200


def test_configure_analytics_mounts_the_middleware_with_the_live_controller():
    from api.analytics_controller import analytics_controller

    app = FastAPI()
    configure_analytics(app)
    mounted = [m for m in app.user_middleware if m.cls is AnalyticsMiddleware]
    assert len(mounted) == 1
    assert mounted[0].kwargs["analytics_controller"] is analytics_controller
