import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from api_schemas import NPUTaskRequest
from worker_inference import WorkerInferenceMixin
from worker_routes import WorkerRoutesMixin


class FailingModelManager:
    def generate_embedding(self, text, model_name):
        raise RuntimeError("model is not loaded")


class InferenceHarness(WorkerInferenceMixin):
    _use_real_inference = True
    _model_manager = FailingModelManager()
    _allow_mock_inference = False


def test_real_inference_failure_is_not_replaced_with_mock_vector():
    with pytest.raises(RuntimeError, match="Embedding inference failed.*model is not loaded"):
        InferenceHarness()._generate_embedding("hello", "nomic-embed-text")


def test_unavailable_inference_fails_when_mock_mode_is_disabled():
    harness = InferenceHarness()
    harness._model_manager = None

    with pytest.raises(RuntimeError, match="Embedding inference is unavailable"):
        harness._generate_embedding("hello", "nomic-embed-text")


class RouteHarness(WorkerRoutesMixin):
    async def generate_npu_embeddings(self, *args):
        raise RuntimeError("model is not loaded")

    async def process_task(self, *args):
        raise RuntimeError("model is not loaded")


def test_embedding_route_returns_5xx_with_failure_reason():
    request = RouteHarness()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(request._handle_embedding_generate(["hello"], "nomic-embed-text", True, "balanced"))

    assert exc_info.value.status_code == 500
    assert "model is not loaded" in str(exc_info.value.detail)


def test_inference_route_returns_5xx_with_failure_reason():
    request = RouteHarness()
    payload = NPUTaskRequest(task_type="embedding_generation", model_name="nomic-embed-text", input_data={})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(request._handle_inference(payload))

    assert exc_info.value.status_code == 500
    assert "model is not loaded" in str(exc_info.value.detail)
