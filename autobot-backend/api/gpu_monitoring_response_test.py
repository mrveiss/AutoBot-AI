# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #13259: all 5 GPU monitoring endpoints dropped their
payload.

Each declared response_model=DataResponse[XResponse] over a flat
{"success", <payload key>} dict; the fix declares the concrete XResponse
model directly. Field-value assertions guard against the regression -- these
endpoints always returned 200 even while `data` was silently null.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.gpu_monitoring import router
from auth_middleware import check_admin_permission


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/gpu")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


def _available_optimizer() -> MagicMock:
    optimizer = MagicMock()
    optimizer.gpu_available = True
    return optimizer


class TestGetGpuEfficiencyResponsePayload:
    def test_returns_the_real_efficiency_metrics_on_the_wire(self):
        client = _make_client()
        with (
            patch("utils.gpu_acceleration_optimizer.gpu_optimizer", _available_optimizer()),
            patch(
                "utils.gpu_acceleration_optimizer.monitor_gpu_efficiency",
                new=AsyncMock(return_value={"utilization_pct": 73.5}),
            ),
        ):
            response = client.get("/api/gpu/efficiency")

        assert response.status_code == 200
        body = response.json()
        assert body["efficiency"]["utilization_pct"] == 73.5
        assert body["success"] is True


class TestGetGpuCapabilitiesResponsePayload:
    def test_returns_the_real_capabilities_on_the_wire(self):
        client = _make_client()
        with patch(
            "utils.gpu_acceleration_optimizer.get_gpu_capabilities",
            return_value={"tensor_cores": True, "memory_gb": 24},
        ):
            response = client.get("/api/gpu/capabilities")

        assert response.status_code == 200
        body = response.json()
        assert body["capabilities"]["memory_gb"] == 24
        assert body["capabilities"]["tensor_cores"] is True


class TestRunGpuBenchmarkResponsePayload:
    def test_returns_the_real_benchmark_result_on_the_wire(self):
        client = _make_client()
        with (
            patch("utils.gpu_acceleration_optimizer.gpu_optimizer", _available_optimizer()),
            patch(
                "utils.gpu_acceleration_optimizer.benchmark_gpu",
                new=AsyncMock(return_value={"compute_score": 987}),
            ),
        ):
            response = client.post("/api/gpu/benchmark")

        assert response.status_code == 200
        body = response.json()
        assert body["benchmark"]["compute_score"] == 987


class TestOptimizeGpuMultimodalResponsePayload:
    def test_returns_the_real_optimization_result_on_the_wire(self):
        from utils.gpu_optimization.types import GPUOptimizationResult

        client = _make_client()
        fake_result = GPUOptimizationResult(
            success=True,
            optimization_type="multimodal_workload",
            performance_improvement=12.5,
            memory_savings_mb=256.0,
            throughput_improvement=8.0,
            latency_reduction_ms=3.0,
            recommendations=[],
            warnings=[],
            applied_optimizations=["mixed_precision", "batch_tuning"],
        )

        with (
            patch("utils.gpu_acceleration_optimizer.gpu_optimizer", _available_optimizer()),
            patch(
                "utils.gpu_acceleration_optimizer.optimize_gpu_for_multimodal",
                new=AsyncMock(return_value=fake_result),
            ),
        ):
            response = client.post("/api/gpu/optimize")

        assert response.status_code == 200
        body = response.json()
        assert body["optimization"]["performance_improvement"] == 12.5
        assert body["optimization"]["applied_optimizations"] == ["mixed_precision", "batch_tuning"]


class TestUpdateGpuConfigResponsePayload:
    def test_returns_the_actually_updated_keys_on_the_wire(self):
        client = _make_client()
        with (
            patch("utils.gpu_acceleration_optimizer.gpu_optimizer", _available_optimizer()),
            patch(
                "utils.gpu_acceleration_optimizer.update_gpu_config",
                new=AsyncMock(return_value=True),
            ),
        ):
            response = client.patch(
                "/api/gpu/config",
                json={"updates": {"batch_size": 32, "mixed_precision": True}},
            )

        assert response.status_code == 200
        body = response.json()
        assert sorted(body["updated_keys"]) == ["batch_size", "mixed_precision"]
        assert body["success"] is True
