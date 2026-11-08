"""The hardware accelerator must reject marked mock embeddings."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("mock", [True, False])
async def test_npu_embedding_response_rejects_mock(monkeypatch, mock):
    import ai_hardware_accelerator as module
    from services import npu_worker_routing

    monkeypatch.setattr(module, "_ssot_config", SimpleNamespace(npu_worker_host="worker", npu_worker_port=80))
    monkeypatch.setattr(npu_worker_routing, "npu_worker_urls", AsyncMock(return_value=["http://worker"]))
    monkeypatch.setattr(
        npu_worker_routing, "_post_inference", AsyncMock(return_value={"embedding": [1.0], "mock": mock})
    )
    accelerator = module.AIHardwareAccelerator()
    accelerator.npu_worker_url = "http://worker"
    accelerator._get_optimal_npu_model = MagicMock(return_value="model")
    task = SimpleNamespace(task_type="embedding_generation", input_data={}, priority=1, timeout_seconds=1)
    if mock:
        with pytest.raises(RuntimeError, match="mock embedding"):
            await accelerator._process_on_npu(task)
    else:
        assert (await accelerator._process_on_npu(task))["embedding"] == [1.0]


@pytest.mark.asyncio
async def test_npu_embedding_fails_over_after_mock(monkeypatch):
    import ai_hardware_accelerator as module
    from services import npu_worker_routing

    monkeypatch.setattr(module, "_ssot_config", SimpleNamespace(npu_worker_host="worker", npu_worker_port=80))
    monkeypatch.setattr(npu_worker_routing, "npu_worker_urls", AsyncMock(return_value=["http://one", "http://two"]))
    post = AsyncMock(side_effect=[{"mock": True}, {"embedding": [2.0]}])
    monkeypatch.setattr(npu_worker_routing, "_post_inference", post)
    accelerator = module.AIHardwareAccelerator()
    accelerator._get_optimal_npu_model = MagicMock(return_value="model")
    task = SimpleNamespace(task_type="embedding_generation", input_data={}, priority=1, timeout_seconds=1)

    assert (await accelerator._process_on_npu(task))["embedding"] == [2.0]
    assert post.await_count == 2
