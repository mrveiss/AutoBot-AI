# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for ApiRequestsMetricsRecorder and ApiRequestCounterMiddleware — Issue #10778.

Covers:
- Recorder increments with correct label values.
- status_class bucketing (2xx / 4xx / 5xx / 3xx).
- Middleware increments the counter on a request (FastAPI test app).
- Middleware uses the matched route template, not raw path.
- Middleware does not propagate metric recording failures.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from prometheus_client import CollectorRegistry
from starlette.testclient import TestClient

# Ensure the slm-backend package is importable
_slm_root = Path(__file__).parent.parent
sys.path.insert(0, str(_slm_root))

# ---------------------------------------------------------------------------
# Stub monitoring.prometheus_metrics so the middleware's LAZY runtime import
# `from monitoring.prometheus_metrics import get_metrics_manager` (inside
# _record_request) resolves without the full manager; patch it there per-test.
# ---------------------------------------------------------------------------
_fake_prom_metrics = types.ModuleType("monitoring.prometheus_metrics")
_stub_get_metrics_manager = MagicMock()
_fake_prom_metrics.get_metrics_manager = _stub_get_metrics_manager
sys.modules["monitoring.prometheus_metrics"] = _fake_prom_metrics
sys.modules.setdefault("monitoring", types.ModuleType("monitoring"))
# Expose as an attribute too so patch("monitoring.prometheus_metrics.…") resolves
# (mock.patch uses getattr on the package, not sys.modules).
sys.modules["monitoring"].prometheus_metrics = _fake_prom_metrics

# ---------------------------------------------------------------------------
# Stub autobot_shared before loading the shared recorder.
# ---------------------------------------------------------------------------
_shared = types.ModuleType("autobot_shared")
sys.modules.setdefault("autobot_shared", _shared)
for _name in [
    "autobot_shared.monitoring",
    "autobot_shared.monitoring.metrics",
    "autobot_shared.monitoring.prometheus_metrics",
]:
    sys.modules.setdefault(_name, types.ModuleType(_name))

# ---------------------------------------------------------------------------
# Load ApiRequestsMetricsRecorder from the shared canonical implementation.
# ---------------------------------------------------------------------------
_repo_root = _slm_root.parent


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_base_mod = _load_module(
    "autobot_shared.monitoring.metrics.base",
    _repo_root / "autobot_shared" / "monitoring" / "metrics" / "base.py",
)
_rec_mod = _load_module(
    "autobot_shared.monitoring.metrics.api_requests",
    _repo_root / "autobot_shared" / "monitoring" / "metrics" / "api_requests.py",
)
ApiRequestsMetricsRecorder = _rec_mod.ApiRequestsMetricsRecorder

# ---------------------------------------------------------------------------
# Now import the middleware (monitoring.prometheus_metrics stub already active).
# ---------------------------------------------------------------------------
from middleware.api_request_counter import ApiRequestCounterMiddleware  # noqa: E402

# ---------------------------------------------------------------------------
# Part 1: Unit tests for ApiRequestsMetricsRecorder
# ---------------------------------------------------------------------------


class TestApiRequestsMetricsRecorder:
    """Unit tests for the Prometheus counter recorder."""

    def _make_recorder(self) -> ApiRequestsMetricsRecorder:
        return ApiRequestsMetricsRecorder(CollectorRegistry())

    def test_counter_registered(self):
        """The counter metric is registered on the provided registry."""
        recorder = self._make_recorder()
        assert recorder.requests_total is not None

    def test_record_request_increments_counter(self):
        """record_request increments the counter by 1."""
        recorder = self._make_recorder()
        recorder.record_request("GET", "/api/health", 200)
        value = recorder.requests_total.labels(method="GET", endpoint="/api/health", status_class="2xx")._value.get()
        assert value == 1.0

    def test_record_request_multiple_increments(self):
        """Multiple calls accumulate correctly."""
        recorder = self._make_recorder()
        for _ in range(5):
            recorder.record_request("POST", "/api/auth/login", 201)
        value = recorder.requests_total.labels(
            method="POST", endpoint="/api/auth/login", status_class="2xx"
        )._value.get()
        assert value == 5.0

    def test_status_class_4xx(self):
        """404 responses map to status_class='4xx'."""
        recorder = self._make_recorder()
        recorder.record_request("GET", "/api/nodes/missing", 404)
        value = recorder.requests_total.labels(
            method="GET", endpoint="/api/nodes/missing", status_class="4xx"
        )._value.get()
        assert value == 1.0

    def test_status_class_5xx(self):
        """500 responses map to status_class='5xx'."""
        recorder = self._make_recorder()
        recorder.record_request("POST", "/api/services", 500)
        value = recorder.requests_total.labels(method="POST", endpoint="/api/services", status_class="5xx")._value.get()
        assert value == 1.0

    def test_different_methods_tracked_separately(self):
        """GET and POST to the same endpoint maintain independent counts."""
        recorder = self._make_recorder()
        recorder.record_request("GET", "/api/agents", 200)
        recorder.record_request("POST", "/api/agents", 201)
        get_val = recorder.requests_total.labels(method="GET", endpoint="/api/agents", status_class="2xx")._value.get()
        post_val = recorder.requests_total.labels(
            method="POST", endpoint="/api/agents", status_class="2xx"
        )._value.get()
        assert get_val == 1.0
        assert post_val == 1.0

    def test_3xx_status_class(self):
        """3xx responses map to status_class='3xx'."""
        recorder = self._make_recorder()
        recorder.record_request("GET", "/", 301)
        value = recorder.requests_total.labels(method="GET", endpoint="/", status_class="3xx")._value.get()
        assert value == 1.0


# ---------------------------------------------------------------------------
# Part 2: Integration tests for ApiRequestCounterMiddleware
# ---------------------------------------------------------------------------
# Uses FastAPI so that scope["route"] is populated after call_next, which is
# required for route-template resolution (Starlette plain apps do not set it).
# ---------------------------------------------------------------------------


def _make_fastapi_client(recorder: ApiRequestsMetricsRecorder) -> tuple:
    """Build a minimal FastAPI app with the middleware attached."""
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/items/{item_id}")
    async def get_item(item_id: str):
        return {"item_id": item_id}

    @app.get("/api/missing")
    async def missing():
        from fastapi.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse({"error": "not found"}, status_code=404)

    manager = MagicMock()
    manager._api_requests = recorder
    app.add_middleware(ApiRequestCounterMiddleware)
    return TestClient(app, raise_server_exceptions=True), manager


class TestApiRequestCounterMiddleware:
    """Integration tests using a minimal FastAPI app (required for route resolution)."""

    def test_middleware_increments_on_get(self):
        """A successful GET request increments the counter once."""
        recorder = ApiRequestsMetricsRecorder(CollectorRegistry())
        client, manager = _make_fastapi_client(recorder)

        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            return_value=manager,
        ):
            response = client.get("/api/health")

        assert response.status_code == 200
        value = recorder.requests_total.labels(method="GET", endpoint="/api/health", status_class="2xx")._value.get()
        assert value == 1.0

    def test_middleware_uses_route_template_not_raw_path(self):
        """Parameterised URLs resolve to the route template, not individual paths."""
        recorder = ApiRequestsMetricsRecorder(CollectorRegistry())
        client, manager = _make_fastapi_client(recorder)

        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            return_value=manager,
        ):
            client.get("/api/items/abc123")
            client.get("/api/items/xyz789")

        # Both requests must accumulate in the same label series
        value = recorder.requests_total.labels(
            method="GET", endpoint="/api/items/{item_id}", status_class="2xx"
        )._value.get()
        assert value == 2.0

    def test_middleware_records_4xx(self):
        """Handlers that return 4xx are counted with status_class='4xx'."""
        recorder = ApiRequestsMetricsRecorder(CollectorRegistry())
        client, manager = _make_fastapi_client(recorder)

        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            return_value=manager,
        ):
            client.get("/api/missing")

        value = recorder.requests_total.labels(method="GET", endpoint="/api/missing", status_class="4xx")._value.get()
        assert value == 1.0

    def test_middleware_does_not_raise_on_metric_failure(self):
        """A broken recorder must not propagate exceptions to the caller."""
        from fastapi import FastAPI  # noqa: PLC0415

        broken_manager = MagicMock()
        broken_manager._api_requests.record_request.side_effect = RuntimeError("prometheus exploded")

        app = FastAPI()

        @app.get("/api/health")
        async def health():
            return {"ok": True}

        app.add_middleware(ApiRequestCounterMiddleware)
        client = TestClient(app, raise_server_exceptions=True)

        with patch(
            "monitoring.prometheus_metrics.get_metrics_manager",
            return_value=broken_manager,
        ):
            response = client.get("/api/health")

        # Request still completes; metric failure is silently logged
        assert response.status_code == 200
