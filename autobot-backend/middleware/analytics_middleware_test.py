# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AnalyticsMiddleware tracking and the telemetry opt-out (#9035, #21684)."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from api.settings_telemetry_test import _make_app as _settings_app
from autobot_shared.eventually import eventually
from autobot_shared.ssot_config import config
from config import config_manager
from initialization.middleware import configure_analytics
from middleware.analytics_middleware import AnalyticsMiddleware
from services.telemetry_settings import get_telemetry_settings


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
    return response


async def _post(app: FastAPI, path: str, body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body)


@pytest.fixture
def isolated_config_file(tmp_path, monkeypatch):
    """Point the file-backed config at a temp file, and reload the real one afterwards.

    The settings route reloads the manager from the file it just wrote; without the reload the saved opt-out
    would stay in the manager's memory and leak into every later test in the process.
    """
    monkeypatch.setattr(config_manager, "base_config_file", tmp_path / "config.yaml")
    yield
    monkeypatch.undo()
    config_manager.reload()


@pytest.fixture
def controller() -> AsyncMock:
    return AsyncMock()


async def test_tracks_api_calls_when_telemetry_enabled(controller, monkeypatch):
    monkeypatch.setattr(config.telemetry, "enabled", True)
    response = await _get(_build_app(controller), "/api/ping")
    await eventually(lambda: controller.track_api_call.await_count == 1)
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


async def test_a_handler_error_is_still_tracked_as_a_500(controller, monkeypatch):
    monkeypatch.setattr(config.telemetry, "enabled", True)
    app = FastAPI()
    app.add_middleware(AnalyticsMiddleware, analytics_controller=controller)

    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("handler broke")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/api/boom")
    await eventually(lambda: controller.track_api_call.await_count == 1)
    assert controller.track_api_call.await_args.args[0] == "GET /api/boom"
    assert controller.track_api_call.await_args.args[2] == 500


async def test_the_route_template_is_stored_not_the_raw_path(controller, monkeypatch):
    monkeypatch.setattr(config.telemetry, "enabled", True)
    app = FastAPI()
    app.add_middleware(AnalyticsMiddleware, analytics_controller=controller)

    @app.get("/api/items/{item_id}")
    async def item(item_id: int):
        return {"id": item_id}

    await _get(app, "/api/items/12345")
    await eventually(lambda: controller.track_api_call.await_count == 1)
    assert controller.track_api_call.await_args.args[0] == "GET /api/items/{item_id}"


async def test_an_admin_opt_out_saved_through_the_settings_route_stops_tracking(
    controller, isolated_config_file, monkeypatch
):
    """The real POST writes the config file and never touches the SSOT object; the middleware must still obey it."""
    monkeypatch.setattr(config.telemetry, "enabled", True)  # the env default stays "on"
    app = _settings_app(with_session=False)
    app.add_middleware(AnalyticsMiddleware, analytics_controller=controller)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    await _get(app, "/api/ping")
    await eventually(lambda: controller.track_api_call.await_count == 1)
    assert controller.track_api_call.await_count == 1  # tracked before the opt-out

    body = {"enabled": False, "anonymous_usage_stats": False, "first_run_prompt_shown": True}
    assert (await _post(app, "/api/settings/telemetry", body)).status_code == 200

    controller.track_api_call.reset_mock()
    response = await _get(app, "/api/ping")
    controller.track_api_call.assert_not_awaited()
    assert "X-Tracked-Analytics" not in response.headers

    body["enabled"] = True
    assert (await _post(app, "/api/settings/telemetry", body)).status_code == 200
    await _get(app, "/api/ping")
    await eventually(lambda: controller.track_api_call.await_count == 1)
    assert controller.track_api_call.await_count == 1  # opting back in resumes tracking


async def test_dismissing_the_prompt_keeps_a_saved_opt_out(isolated_config_file, monkeypatch):
    """The dismissal rewrites the config file; it must not drop the opt-out saved before it."""

    monkeypatch.setattr(config.telemetry, "enabled", True)
    app = _settings_app(with_session=False)
    body = {"enabled": False, "anonymous_usage_stats": False, "first_run_prompt_shown": False}
    assert (await _post(app, "/api/settings/telemetry", body)).status_code == 200
    assert get_telemetry_settings()["enabled"] is False

    dismissed = await _post(app, "/api/settings/telemetry/prompt-shown", {})
    assert dismissed.status_code == 200
    assert get_telemetry_settings()["enabled"] is False
    assert get_telemetry_settings()["first_run_prompt_shown"] is True


async def test_the_in_process_call_history_is_a_bounded_ring(monkeypatch):
    """Every tracked /api call is appended; unbounded, a long-lived process grows without limit (#21684)."""
    from collections import deque

    from api import analytics_controller as module

    ring = deque(maxlen=5)
    monkeypatch.setitem(module.analytics_state, "api_call_patterns", ring)
    controller = module.AnalyticsController.__new__(module.AnalyticsController)
    controller.api_frequencies = module.defaultdict(int)
    controller.response_times = module.defaultdict(list)
    controller.error_counts = module.defaultdict(int)
    controller.get_redis_connection = AsyncMock(return_value=None)

    for number in range(12):
        await controller.track_api_call(f"GET /api/item/{number}", 0.01, 200)

    assert len(ring) == 5
    assert [call["endpoint"] for call in ring][-1].endswith("/11")  # the newest survive, the oldest drop


def test_the_ring_size_comes_from_the_environment():
    from api import analytics_controller as module

    assert module.analytics_state["api_call_patterns"].maxlen == module.MAX_API_CALL_PATTERNS


async def test_the_persisted_call_history_is_trimmed_to_the_same_bound(monkeypatch):
    """The Redis copy keeps exactly as many calls as the in-process ring, from one setting (#21684)."""
    from api import analytics_controller as module

    monkeypatch.setattr(module, "MAX_API_CALL_PATTERNS", 7)
    redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis.pipeline.return_value = pipe
    controller = module.AnalyticsController.__new__(module.AnalyticsController)
    controller.api_frequencies = module.defaultdict(int)
    controller.response_times = module.defaultdict(list)
    controller.error_counts = module.defaultdict(int)
    controller.get_redis_connection = AsyncMock(return_value=redis)

    await controller.track_api_call("GET /api/item/1", 0.01, 200)

    # one pipeline, LPUSH queued before LTRIM, so the bound holds even at the limit
    assert [c[0] for c in pipe.method_calls] == ["lpush", "ltrim", "execute"]
    pipe.ltrim.assert_called_once_with("analytics:api_calls", 0, 6)
    pipe.execute.assert_awaited_once()


async def test_an_unmatched_path_is_stored_as_unresolved_never_raw(controller, monkeypatch):
    """A raw path can carry ids, names or tokens; only a matched route template is stored (#21684)."""
    monkeypatch.setattr(config.telemetry, "enabled", True)
    app = FastAPI()
    app.add_middleware(AnalyticsMiddleware, analytics_controller=controller)
    await _get(app, "/api/customers/jane.doe/token/abc123")
    await eventually(lambda: controller.track_api_call.await_count == 1)
    assert controller.track_api_call.await_args.args[0] == "GET unresolved"


def test_the_opt_out_is_rechecked_when_the_request_completes(monkeypatch):
    """A request that entered opted-in but finishes after the opt-out schedules no record."""
    controller = AsyncMock()
    middleware = AnalyticsMiddleware(FastAPI(), analytics_controller=controller)
    monkeypatch.setattr("middleware.analytics_middleware.get_telemetry_settings", lambda: {"enabled": False})
    request = MagicMock()
    middleware._track(request, "/api/ping", 0.01, 200)
    assert not middleware._background_tasks


@pytest.mark.parametrize("raw,expected", [("100000000000000000000", 1_000_000), ("5", 100), ("2500", 2500)])
def test_the_ring_size_setting_is_clamped(monkeypatch, raw, expected):
    from api import analytics_controller as module
    from autobot_shared.env_utils import env_int_clamped

    monkeypatch.setenv("AUTOBOT_API_CALL_PATTERNS_MAX", raw)
    value = env_int_clamped("AUTOBOT_API_CALL_PATTERNS_MAX", 10000, *module.API_CALL_PATTERNS_BOUNDS)
    assert value == expected
    assert module.deque(maxlen=value).maxlen == expected  # no OverflowError
