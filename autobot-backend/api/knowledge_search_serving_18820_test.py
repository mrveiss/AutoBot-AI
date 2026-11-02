# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge-search route never returns a rejected or invalid fact (#18820).

``_execute_kb_search`` queries ``VectorSearchEngine`` directly, so it bypasses the check
``KB.search`` applies. The route must apply the same canonical predicate to the engine's hits.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.knowledge_search import _execute_kb_search
from knowledge.vector_search_engine import VectorSearchResult

_METADATA = {
    "ok": {"verification_status": "verified"},
    "rejected": {"verification_status": "rejected"},
    "expired": {"valid_until": "2020-01-01T00:00:00+00:00"},
    "garbage": {"valid_to": "garbage"},
}


@pytest.mark.asyncio
async def test_the_engine_leg_never_returns_a_rejected_or_invalid_fact():
    engine = MagicMock()
    engine.search = AsyncMock(
        return_value=[VectorSearchResult(text=k, score=0.9, metadata=m, source=k) for k, m in _METADATA.items()]
    )

    async def passthrough(results, **_kwargs):
        return results

    with (
        patch("api.knowledge_search.get_vector_search_engine", AsyncMock(return_value=engine)),
        patch("api.knowledge_search.filter_search_results_by_permission", side_effect=passthrough),
    ):
        results = await _execute_kb_search(MagicMock(), "q", 10, "hybrid", "u", None, [], True)

    assert [r["doc_id"] for r in results] == ["ok"]
