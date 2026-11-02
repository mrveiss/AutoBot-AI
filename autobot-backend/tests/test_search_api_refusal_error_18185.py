# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18185: an embedding refusal reaches the API response as a failed search with its reason."""

from types import SimpleNamespace

import pytest

from api.search import _convert_metrics_to_api_format


def _metrics(**extra):
    base = dict(
        total_documents_searched=0,
        embedding_generation_time_ms=0,
        similarity_computation_time_ms=0,
        total_search_time_ms=1.0,
        device_used="embedding_unavailable",
        hardware_utilization={},
    )
    return SimpleNamespace(**base, **extra)


def test_refused_search_metrics_carry_the_error():
    data = _convert_metrics_to_api_format(_metrics(error="embedding model 'm' unavailable: no vector returned"))
    assert data["error"].endswith("no vector returned")


def test_successful_search_response_is_unchanged():
    assert "error" not in _convert_metrics_to_api_format(_metrics(error=None))


async def _call_semantic(metrics):
    from unittest.mock import AsyncMock, patch

    from api import search as mod
    from api.schemas_knowledge import NPUSearchRequest

    engine = SimpleNamespace(search=AsyncMock(return_value=([], metrics)))
    with patch.object(mod, "get_npu_search_engine", AsyncMock(return_value=engine)):
        return await mod.semantic_search(NPUSearchRequest(query="q"))


@pytest.mark.asyncio
async def test_refusal_is_a_503_with_the_reason_not_an_empty_200():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _call_semantic(_metrics(error="embedding model 'm' unavailable: no vector returned"))
    assert exc.value.status_code == 503 and "unavailable" in exc.value.detail


@pytest.mark.asyncio
async def test_success_response_is_unchanged():
    resp = await _call_semantic(_metrics(error=None))
    assert resp.total_results == 0 and "error" not in resp.metrics
