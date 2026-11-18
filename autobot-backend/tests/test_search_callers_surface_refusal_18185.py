# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18185: in-process callers surface an embedding refusal instead of reporting no matches."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.embedding_model import EmbeddingUnavailableError, raise_if_embedding_refused

REFUSED = SimpleNamespace(
    error="embedding model 'm' unavailable: no vector returned", total_search_time_ms=1, device_used="x"
)
OK = SimpleNamespace(error=None, total_search_time_ms=1, device_used="x")


def test_helper_raises_only_on_refusal():
    raise_if_embedding_refused(OK)
    with pytest.raises(EmbeddingUnavailableError):
        raise_if_embedding_refused(REFUSED)


@pytest.mark.asyncio
async def test_vector_search_engine_npu_backend_raises_not_empty():
    from knowledge.vector_search_engine import _NPUBackend

    backend = _NPUBackend()
    backend._engine = MagicMock(search=AsyncMock(return_value=([], REFUSED)))
    with pytest.raises(EmbeddingUnavailableError):
        await backend.search("q", 5, None)
    backend._engine = MagicMock(search=AsyncMock(return_value=([], OK)))
    assert await backend.search("q", 5, None) == []  # a genuine no-match stays empty


def _agent(engine_search=None):
    from agents.npu_code_search_agent import NPUCodeSearchAgent

    agent = NPUCodeSearchAgent.__new__(NPUCodeSearchAgent)
    agent.logger, agent.cache_ttl, agent.search_cache_prefix = MagicMock(), 60, "p:"
    agent.redis_client = MagicMock(get=MagicMock(return_value=None))
    agent._ensure_search_engine_initialized = AsyncMock()
    agent.npu_available = True
    agent.npu_search_engine = MagicMock(search=AsyncMock(return_value=([], engine_search or REFUSED)))
    agent._fallback_word_matching = AsyncMock(side_effect=AssertionError("degraded to word matching"))
    agent._search_exact = AsyncMock(return_value=[])
    return agent


@pytest.mark.asyncio
@pytest.mark.parametrize("search_type", ["semantic", "hybrid"])
async def test_search_code_raises_a_code_index_refusal_not_word_matches_or_empty(search_type):
    from unittest.mock import patch

    agent = _agent()
    no_model = AsyncMock(side_effect=OSError("weights missing"))
    with patch("agents.npu_code_search_agent.get_code_embedding_generator", no_model):
        with pytest.raises(EmbeddingUnavailableError, match="code index model unavailable"):
            await agent.search_code("q", search_type=search_type)
    agent.redis_client.setex.assert_not_called()  # a refusal is never cached as a result


@pytest.mark.asyncio
async def test_search_code_raises_a_kb_tier_refusal_not_word_matches_or_empty():
    agent = _agent()
    agent._search_code_embeddings = AsyncMock(side_effect=RuntimeError("chroma down"))
    with pytest.raises(EmbeddingUnavailableError):
        await agent.search_code("q", search_type="semantic")
    agent._fallback_word_matching.assert_not_awaited()


@pytest.mark.asyncio
async def test_code_search_route_is_a_503_with_the_reason_and_a_400_stays_a_400():
    from unittest.mock import patch

    from fastapi import HTTPException

    from api import code_search as mod
    from api.schemas_code import CodeSearchRequest

    refused = AsyncMock(side_effect=EmbeddingUnavailableError("index 'x': search refused, why"))
    with patch.object(mod, "search_codebase", refused), pytest.raises(HTTPException) as exc:
        await mod.search_code(CodeSearchRequest(query="q"))
    assert exc.value.status_code == 503 and "refused, why" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        await mod.search_code(CodeSearchRequest(query="q", search_type="nope"))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_natural_language_search_route_is_a_503_with_the_reason():
    from unittest.mock import patch

    from fastapi import HTTPException

    from api import code_search
    from api import natural_language_search as mod
    from api.schemas_knowledge import NLSearchRequest

    refused = AsyncMock(side_effect=EmbeddingUnavailableError("index 'x': search refused, why"))
    with patch.object(code_search, "search_codebase", refused), pytest.raises(HTTPException) as exc:
        await mod.natural_language_search(NLSearchRequest(query="where is auth", include_explanations=False))
    assert exc.value.status_code == 503 and "refused, why" in exc.value.detail


@pytest.mark.asyncio
async def test_gpu_backend_refuses_the_unrecorded_hybrid_space_before_embedding():
    from unittest.mock import patch

    from knowledge.vector_search_engine import _GPUBackend

    backend = _GPUBackend()
    backend._hybrid = MagicMock(search=AsyncMock(side_effect=AssertionError("searched")))
    accessor = AsyncMock(side_effect=AssertionError("embedded"))
    with patch("services.npu_client.generate_embedding_with_fallback", accessor):
        with pytest.raises(EmbeddingUnavailableError, match="hybrid_faiss"):
            await backend.search("q", 5, None)


@pytest.mark.asyncio
async def test_connectivity_test_reports_failed_not_success():
    from unittest.mock import patch

    from api import search as mod

    engine = MagicMock(
        npu_worker_url="u", _test_npu_connectivity=AsyncMock(), search=AsyncMock(return_value=([], REFUSED))
    )
    with patch.object(mod, "get_npu_search_engine", AsyncMock(return_value=engine)):
        out = await mod.test_npu_connectivity()
    assert out["connectivity"] == "failed"
    assert out["fallback_available"] is False and out["error"] == mod.REFUSED_SEARCH_ERROR
    assert REFUSED.error not in out["error"]  # the internal reason stays in the log, not the response
