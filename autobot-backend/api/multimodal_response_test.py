# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #13259: all 7 multimodal endpoints dropped their
payload.

Each declared response_model=DataResponse[XData] over a flat dict return; the
fix declares the concrete flat *Data model directly (all use
model_config = {"extra": "allow"}, matching the ad-hoc dict shapes these
handlers build).
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.multimodal import router
from auth_middleware import get_current_user


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/multimodal")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "test-user", "role": "admin"}
    return TestClient(app)


class _FakeEmbedding(list):
    """Stand-in for the numpy/torch array accelerated_embedding_generation returns."""

    def tolist(self):
        return list(self)


class TestGenerateEmbeddingResponsePayload:
    def test_returns_the_real_embedding_on_the_wire(self):
        client = _make_client()
        fake_embedding = _FakeEmbedding([0.1, 0.2, 0.3, 0.4])

        with patch(
            "api.multimodal.accelerated_embedding_generation",
            new=AsyncMock(return_value=fake_embedding),
        ):
            response = client.post(
                "/api/multimodal/embeddings/generate",
                json={"content": "hello world", "modality": "text"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["embedding"] == [0.1, 0.2, 0.3, 0.4]
        assert body["dimension"] == 4
        assert body["success"] is True


class TestGetMultimodalStatsResponsePayload:
    def test_returns_the_real_processor_stats_on_the_wire(self):
        client = _make_client()
        mock_engine = AsyncMock()
        mock_engine.get_health_status = AsyncMock(return_value={"status": "ok"})
        mock_processor = MagicMock()
        mock_processor.get_stats.return_value = {"model_availability": {}}

        with (
            patch("api.multimodal.processor", mock_processor),
            patch("api.multimodal._get_gpu_stats", return_value=(False, {})),
            patch("api.multimodal.get_npu_search_engine", new=AsyncMock(return_value=mock_engine)),
        ):
            response = client.get("/api/multimodal/stats")

        assert response.status_code == 200
        body = response.json()
        assert body["system_status"] == "healthy"
        assert body["gpu_available"] is False
        assert body["search_engine_status"]["status"] == "ok"


class TestCombineMultimodalInputsResponsePayload:
    def test_returns_the_real_fusion_result_on_the_wire(self):
        client = _make_client()

        fake_process_result = MagicMock()
        fake_process_result.modality_type.value = "text"
        fake_process_result.confidence = 0.9
        fake_process_result.result_data = {"echo": "hi"}

        fake_fusion_result = MagicMock()
        fake_fusion_result.success = True
        fake_fusion_result.result_data = {"combined": True}
        fake_fusion_result.confidence = 0.85

        mock_processor = MagicMock()
        mock_processor.process = AsyncMock(return_value=fake_process_result)
        mock_processor._process_combined = AsyncMock(return_value=fake_fusion_result)

        with patch("api.multimodal.processor", mock_processor):
            response = client.post(
                "/api/multimodal/fusion/combine",
                data={"text": "hi", "intent": "decision_making"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["fusion_confidence"] == 0.85
        assert body["fusion_result"] == {"combined": True}
        assert body["modalities_combined"] == 1


class TestGetPerformanceStatsResponsePayload:
    def test_returns_the_real_performance_metrics_on_the_wire(self):
        client = _make_client()
        mock_processor = MagicMock()
        mock_processor.performance_monitor.monitor_processing_performance = AsyncMock(
            return_value={"throughput": 42}
        )
        mock_processor.get_stats.return_value = {"total_processed": 100}
        mock_processor.use_amp = True
        mock_processor.device = "cuda:0"
        mock_processor.performance_monitor.batch_sizes = {"text": 8}

        with patch("api.multimodal.processor", mock_processor):
            response = client.get("/api/multimodal/performance/stats")

        assert response.status_code == 200
        body = response.json()
        assert body["performance_metrics"]["throughput"] == 42
        assert body["processor_stats"]["total_processed"] == 100
        assert body["optimization_status"]["mixed_precision_enabled"] is True


class TestOptimizePerformanceResponsePayload:
    def test_returns_the_real_optimization_result_on_the_wire(self):
        client = _make_client()
        mock_processor = MagicMock()
        mock_processor.performance_monitor.optimize_gpu_memory = AsyncMock(
            return_value={"freed_mb": 512}
        )

        with patch("api.multimodal.processor", mock_processor):
            response = client.post("/api/multimodal/performance/optimize")

        assert response.status_code == 200
        body = response.json()
        assert body["optimization_result"]["freed_mb"] == 512
        assert body["message"] == "Performance optimization completed"


class TestGetPerformanceSummaryResponsePayload:
    def test_returns_the_real_summary_on_the_wire(self):
        client = _make_client()
        mock_processor = MagicMock()
        mock_processor.performance_monitor.get_performance_summary.return_value = {
            "avg_latency_ms": 12.3
        }

        with patch("api.multimodal.processor", mock_processor):
            response = client.get("/api/multimodal/performance/summary")

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["avg_latency_ms"] == 12.3


class TestUpdateBatchSizeResponsePayload:
    def test_returns_the_real_old_and_new_batch_size_on_the_wire(self):
        client = _make_client()
        mock_processor = MagicMock()
        mock_processor.performance_monitor.batch_sizes = {"text": 8}

        with patch("api.multimodal.processor", mock_processor):
            response = client.post(
                "/api/multimodal/performance/batch-size",
                params={"modality": "text", "batch_size": 16},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["old_batch_size"] == 8
        assert body["new_batch_size"] == 16
        assert body["modality"] == "text"
