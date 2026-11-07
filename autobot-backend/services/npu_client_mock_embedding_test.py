"""Mock NPU embeddings must not be returned to backend callers."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("mock", [True, False])
async def test_mock_embeddings_are_rejected(monkeypatch, mock):
    from services import npu_client

    @asynccontextmanager
    async def post(*args, **kwargs):
        response = MagicMock(status=200)
        response.json = AsyncMock(return_value={"embeddings": [[1.0]], "mock": mock})
        yield response

    client = npu_client.NPUClient("http://worker")
    client._get_session = AsyncMock(return_value=MagicMock(post=post))
    monkeypatch.setattr(npu_client, "assert_egress_policy", AsyncMock())
    result = await client.generate_embeddings(["text"], "model")
    if mock:
        assert result is None
    else:
        assert result.embeddings == [[1.0]]
