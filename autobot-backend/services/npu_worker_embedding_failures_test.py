import asyncio
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

APP_DIR = Path(__file__).resolve().parents[2] / "autobot-npu-worker" / "resources" / "windows-npu-worker" / "app"
_APP_DIR = str(APP_DIR)
# The standalone worker and backend both publish a top-level ``utils`` package.
_WORKER_MODULE_NAMES = {path.stem for path in APP_DIR.glob("*.py")}


def _utils_modules() -> dict[str, ModuleType | None]:
    return {name: module for name, module in sys.modules.items() if name == "utils" or name.startswith("utils.")}


def _clear_utils_modules() -> None:
    for name in tuple(sys.modules):
        if name == "utils" or name.startswith("utils."):
            sys.modules.pop(name)


_backend_worker_modules = {name: sys.modules[name] for name in _WORKER_MODULE_NAMES if name in sys.modules}
_backend_utils_modules = _utils_modules()
_inserted_app_dir = _APP_DIR not in sys.path
if _inserted_app_dir:
    sys.path.insert(0, _APP_DIR)

try:
    for name in _WORKER_MODULE_NAMES:
        sys.modules.pop(name, None)
    _clear_utils_modules()

    import worker_startup as _worker_startup
    from api_schemas import NPUTaskRequest
    from worker_inference import WorkerInferenceMixin
    from worker_routes import WorkerRoutesMixin
    from worker_startup import WorkerStartupMixin
    from worker_state import LRUCache, ThreadSafeStats

    _worker_modules = {name: sys.modules[name] for name in _WORKER_MODULE_NAMES if name in sys.modules}
    _worker_utils_modules = _utils_modules()
finally:
    for name in _WORKER_MODULE_NAMES:
        sys.modules.pop(name, None)
    _clear_utils_modules()
    sys.modules.update(_backend_worker_modules)
    sys.modules.update(_backend_utils_modules)
    if _inserted_app_dir:
        sys.path.remove(_APP_DIR)


@pytest.fixture(autouse=True)
def _worker_import_namespace(request: pytest.FixtureRequest) -> Iterator[None]:
    for fixture_name in ("empty_reachable_provider_key_vault", "fake_session_lease", "reset_feature_flags_singleton"):
        if fixture_name in request.fixturenames:
            request.getfixturevalue(fixture_name)

    backend_worker_modules = {name: sys.modules[name] for name in _WORKER_MODULE_NAMES if name in sys.modules}
    backend_utils_modules = _utils_modules()
    for name in _WORKER_MODULE_NAMES:
        sys.modules.pop(name, None)
    _clear_utils_modules()
    sys.modules.update(_worker_modules)
    sys.modules.update(_worker_utils_modules)
    try:
        yield
    finally:
        for name in _WORKER_MODULE_NAMES:
            sys.modules.pop(name, None)
        _clear_utils_modules()
        sys.modules.update(backend_worker_modules)
        sys.modules.update(backend_utils_modules)


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
    async def _generate_npu_embeddings_with_origin(self, *args):
        raise RuntimeError("model is not loaded")

    async def process_task(self, *args):
        raise RuntimeError("model is not loaded")


def test_embedding_route_returns_5xx_with_failure_reason():
    request = RouteHarness()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(request._handle_embedding_generate(["hello"], "nomic-embed-text", True, "balanced"))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Embedding generation failed"


def test_inference_route_returns_5xx_with_failure_reason():
    request = RouteHarness()
    payload = NPUTaskRequest(task_type="embedding_generation", model_name="nomic-embed-text", input_data={})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(request._handle_inference(payload))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Inference failed"


class HTTPHarness(WorkerInferenceMixin, WorkerRoutesMixin):
    def __init__(self, manager):
        self.app = FastAPI()
        self._model_manager = manager
        self._use_real_inference = True
        self._allow_mock_inference = False
        self.loaded_models = {"model": {}}
        self.embedding_cache = LRUCache()
        self.task_stats = ThreadSafeStats()
        self.npu_optimization = {}
        self.npu_available = False
        self._register_inference_routes()

    async def get_npu_utilization(self):
        return 0


@pytest.mark.parametrize("error", [KeyError("missing model"), RuntimeError("private inference failure")])
@pytest.mark.parametrize("endpoint", ["/inference", "/embedding/generate"])
def test_failures_reach_http_without_exposing_details(endpoint, error):
    class Manager:
        def generate_embedding(self, text, model_name):
            raise error

    worker = HTTPHarness(Manager())
    payload = (
        {"task_type": "embedding_generation", "model_name": "model", "input_data": {"text": "hello"}}
        if endpoint == "/inference"
        else ["hello"]
    )
    response = TestClient(worker.app).post(endpoint, json=payload, params={"model_name": "model"})
    assert response.status_code == 500
    assert "private" not in response.text and "missing model" not in response.text
    assert "embedding" not in response.json()


def test_mock_status_survives_cache_and_crosses_both_endpoints():
    worker = HTTPHarness(None)
    worker._allow_mock_inference = True
    client = TestClient(worker.app)
    first = client.post("/embedding/generate", json=["hello"], params={"model_name": "model"}).json()
    second = client.post(
        "/inference", json={"task_type": "embedding_generation", "model_name": "model", "input_data": {"text": "hello"}}
    ).json()
    assert first["mock"] is True
    assert second["result"]["mock"] is True
    assert second["result"]["cache_hit"] is True


def test_mixed_batch_marks_cached_mock_and_new_real_embedding():
    worker = HTTPHarness(None)
    worker._allow_mock_inference = True
    client = TestClient(worker.app)
    client.post("/embedding/generate", json=["cached"], params={"model_name": "model"})

    class Manager:
        def generate_embedding(self, text, model_name):
            return [1.0, 0.0]

    worker._model_manager = Manager()
    response = client.post("/embedding/generate", json=["cached", "real"], params={"model_name": "model"})
    assert response.status_code == 200
    assert response.json()["mock"] is True
    real = client.post("/embedding/generate", json=["real"], params={"model_name": "model"}).json()
    assert real["mock"] is False
    assert real["embeddings"] == [[1.0, 0.0]]


def test_failed_preload_is_unhealthy_until_a_model_loads(monkeypatch):
    class Worker(WorkerStartupMixin, WorkerRoutesMixin):
        def __init__(self):
            self.app = FastAPI()
            self._preload_failed = False
            self._allow_mock_inference = False
            self.loaded_models = {}
            self.task_stats = ThreadSafeStats()
            self.worker_id = "test"
            self.npu_available = False
            self.npu_optimization = {}
            self.pairing_status = {}
            self._register_health_routes()

        async def get_npu_metrics(self):
            return {}

        async def load_and_optimize_model(self, name, optimization_level):
            raise RuntimeError("load failed")

    monkeypatch.setattr(_worker_startup, "config", {"models": {"chat": {"preload": True, "name": "model"}}})
    worker = Worker()
    client = TestClient(worker.app)
    assert client.get("/health").status_code == 200
    asyncio.run(worker.load_default_models())
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    worker.loaded_models["model"] = {}
    assert client.get("/health").json()["status"] == "healthy"


@pytest.mark.parametrize("manager_available", [False, True])
def test_failed_embedding_preload_aborts_startup(monkeypatch, manager_available):
    class Worker(WorkerStartupMixin):
        def __init__(self):
            self.worker_id = None
            self.pairing_status = {}
            self._display_network_info = MagicMock()
            self.initialize_redis = AsyncMock()
            self.initialize_npu = AsyncMock()
            self._models_lock = asyncio.Lock()
            self.loaded_models = {}
            self._use_real_inference = manager_available
            self._model_manager = MagicMock(load_model=AsyncMock(return_value=False)) if manager_available else None
            self._allow_mock_inference = False

    monkeypatch.setattr(_worker_startup, "config", {"models": {"embedding": {"preload": True, "name": "model"}}})
    worker = Worker()
    with pytest.raises(RuntimeError, match="Real inference is unavailable for model"):
        asyncio.run(worker.initialize())
    assert worker.loaded_models == {}
