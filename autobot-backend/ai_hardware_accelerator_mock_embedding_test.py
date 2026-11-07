"""The hardware accelerator must reject marked mock embeddings."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("mock", [True, False])
async def test_npu_embedding_response_rejects_mock(monkeypatch, mock):
    import ai_hardware_accelerator as module

    @asynccontextmanager
    async def response():
        yield SimpleNamespace(
            status=200,
            json=AsyncMock(return_value={"status": "completed", "result": {"embedding": [1.0], "mock": mock}}),
        )

    monkeypatch.setattr(module, "get_http_client", lambda: SimpleNamespace(post=AsyncMock(return_value=response())))
    accelerator = module.AIHardwareAccelerator.__new__(module.AIHardwareAccelerator)
    accelerator.npu_worker_url = "http://worker"
    accelerator._get_optimal_npu_model = MagicMock(return_value="model")
    task = SimpleNamespace(task_type="embedding_generation", input_data={}, priority=1, timeout_seconds=1)
    if mock:
        with pytest.raises(RuntimeError, match="mock embedding"):
            await accelerator._process_on_npu(task)
    else:
        assert (await accelerator._process_on_npu(task))["embedding"] == [1.0]
