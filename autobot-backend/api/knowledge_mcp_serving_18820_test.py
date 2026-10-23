# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The MCP knowledge-search tool leaves the serving check to ``KB.search`` (#18820).

``KB.search`` withholds rejected and invalid facts for every caller (see
``knowledge/search_serving_modes_18820_test.py``). This route must therefore not opt out, and
must AND the caller's filter with the quarantine filter (#18946), never substitute it.
"""

from __future__ import annotations

from unittest.mock import create_autospec, patch

import pytest

from api.knowledge_mcp import KnowledgeSearchRequest, mcp_search_knowledge_base
from knowledge_base import KnowledgeBase


@pytest.mark.asyncio
@pytest.mark.parametrize("filters", [{"category": "docs"}, None], ids=["caller-filter", "default-filter"])
async def test_mcp_search_does_not_opt_out_of_the_serving_check(filters):
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [{"content": "kept", "score": 0.9, "metadata": {}}]

    with patch("api.knowledge_mcp.get_knowledge_base", return_value=mock_kb):
        response = await mcp_search_knowledge_base(
            request=KnowledgeSearchRequest(query="redis", top_k=5, filters=filters),
            current_user={"user_id": "test-user"},
        )

    assert "include_unservable" not in mock_kb.search.call_args.kwargs
    assert [r["content"] for r in response["results"]] == ["kept"]
