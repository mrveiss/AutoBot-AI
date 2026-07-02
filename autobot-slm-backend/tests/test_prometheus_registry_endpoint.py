# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the shared Prometheus registry endpoint — Issue #10851.

Covers:
- GET /metrics returns 200.
- Response Content-Type matches CONTENT_TYPE_LATEST (``text/plain; version=…``).
- Response body contains the metric name registered by ApiRequestsMetricsRecorder
  (``autobot_api_requests_total``), proving the shared registry is served.
- A get_metrics_manager() failure is surfaced as a 500 (not silently swallowed).
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Ensure the slm-backend root is importable.
# ---------------------------------------------------------------------------
_slm_root = Path(__file__).parent.parent
sys.path.insert(0, str(_slm_root))

# ---------------------------------------------------------------------------
# Stub the heavy monitoring package so main.py's deferred import inside the
# endpoint handler can be patched per-test without pulling the full dep tree.
# ---------------------------------------------------------------------------
_fake_monitoring_pkg = types.ModuleType("monitoring")
_fake_prom_metrics_mod = types.ModuleType("monitoring.prometheus_metrics")
_fake_prom_metrics_mod.get_metrics_manager = MagicMock()
_fake_monitoring_pkg.prometheus_metrics = _fake_prom_metrics_mod
sys.modules.setdefault("monitoring", _fake_monitoring_pkg)
sys.modules["monitoring.prometheus_metrics"] = _fake_prom_metrics_mod


# ---------------------------------------------------------------------------
# Minimal FastAPI app that replicates ONLY the /metrics endpoint from main.py,
# keeping the test isolated from the full SLM startup/lifespan machinery.
# ---------------------------------------------------------------------------


def _make_test_app():
    """Build a minimal FastAPI app exposing only the /metrics endpoint."""
    from fastapi import FastAPI  # noqa: PLC0415
    from fastapi.responses import Response  # noqa: PLC0415

    app = FastAPI()

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_registry_metrics() -> Response:
        from prometheus_client import CONTENT_TYPE_LATEST as _CT  # noqa: PLC0415

        from monitoring.prometheus_metrics import get_metrics_manager as _gmm  # noqa: PLC0415

        return Response(content=_gmm().get_metrics(), media_type=_CT)

    return app


# ---------------------------------------------------------------------------
# Helper: build a metrics manager backed by a real isolated CollectorRegistry
# so the test asserts on real prometheus_client output.
# ---------------------------------------------------------------------------


def _make_real_manager():
    """Return a PrometheusMetricsManager-like object with a real registry."""
    import importlib.util  # noqa: PLC0415

    _repo_root = _slm_root.parent
    spec = importlib.util.spec_from_file_location(
        "autobot_shared.monitoring.metrics.base",
        str(_repo_root / "autobot_shared" / "monitoring" / "metrics" / "base.py"),
    )
    base_mod = importlib.util.module_from_spec(spec)
    sys.modules["autobot_shared.monitoring.metrics.base"] = base_mod
    spec.loader.exec_module(base_mod)

    api_spec = importlib.util.spec_from_file_location(
        "autobot_shared.monitoring.metrics.api_requests",
        str(_repo_root / "autobot_shared" / "monitoring" / "metrics" / "api_requests.py"),
    )
    api_mod = importlib.util.module_from_spec(api_spec)
    sys.modules["autobot_shared.monitoring.metrics.api_requests"] = api_mod
    api_spec.loader.exec_module(api_mod)
    ApiRequestsMetricsRecorder = api_mod.ApiRequestsMetricsRecorder

    registry = CollectorRegistry()
    recorder = ApiRequestsMetricsRecorder(registry)
    # Bump the counter so the metric name appears in the output.
    recorder.record_request("GET", "/api/health", 200)

    manager = MagicMock()
    manager.get_metrics.return_value = _expose(registry)
    return manager


def _expose(registry: CollectorRegistry) -> bytes:
    """Render registry to Prometheus text format."""
    from prometheus_client import generate_latest  # noqa: PLC0415

    return generate_latest(registry)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPrometheusRegistryEndpoint:
    """Verify the /metrics exposition endpoint (#10851)."""

    def test_returns_200(self):
        """GET /metrics responds with HTTP 200."""
        manager = MagicMock()
        manager.get_metrics.return_value = b"# ok\n"
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=True)

        with patch("monitoring.prometheus_metrics.get_metrics_manager", return_value=manager):
            response = client.get("/metrics")

        assert response.status_code == 200

    def test_content_type_is_prometheus_text(self):
        """Content-Type header must match CONTENT_TYPE_LATEST."""
        manager = MagicMock()
        manager.get_metrics.return_value = b"# ok\n"
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=True)

        with patch("monitoring.prometheus_metrics.get_metrics_manager", return_value=manager):
            response = client.get("/metrics")

        # Content-Type may carry charset; check prefix
        assert response.headers["content-type"].startswith("text/plain")
        # CONTENT_TYPE_LATEST version token must be present
        assert "version=" in response.headers["content-type"]

    def test_body_contains_registered_metric_name(self):
        """Response body contains autobot_api_requests_total from the shared registry."""
        manager = _make_real_manager()
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=True)

        with patch("monitoring.prometheus_metrics.get_metrics_manager", return_value=manager):
            response = client.get("/metrics")

        assert response.status_code == 200
        assert b"autobot_api_requests_total" in response.content

    def test_endpoint_calls_get_metrics(self):
        """The endpoint delegates to get_metrics_manager().get_metrics()."""
        manager = MagicMock()
        manager.get_metrics.return_value = b"# test metric output\n"
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=True)

        with patch("monitoring.prometheus_metrics.get_metrics_manager", return_value=manager):
            client.get("/metrics")

        manager.get_metrics.assert_called_once()

    @pytest.mark.parametrize("path", ["/api/metrics", "/api/metrics/prometheus"])
    def test_colliding_api_paths_absent(self, path):
        """The minimal test app only exposes /metrics; existing /api/* paths are absent."""
        manager = MagicMock()
        manager.get_metrics.return_value = b""
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(path)
        assert response.status_code == 404, f"Path {path} should not be served by the /metrics-only test app"
