# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The MCP search route ANDs a caller filter with the quarantine filter (#18946)."""

from __future__ import annotations

from unittest.mock import create_autospec, patch

import pytest

from api.knowledge_mcp import KnowledgeSearchRequest, mcp_search_knowledge_base
from knowledge.quarantine import with_quarantine
from knowledge_base import KnowledgeBase


@pytest.mark.asyncio
async def test_mcp_route_ands_caller_filter_with_quarantine():
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = []
    with patch("api.knowledge_mcp.get_knowledge_base", return_value=mock_kb):
        await mcp_search_knowledge_base(
            request=KnowledgeSearchRequest(query="q", top_k=5, filters={"category": "docs"}),
            current_user={"user_id": "u"},
        )
    assert mock_kb.search.call_args.kwargs["filters"] == with_quarantine({"category": "docs"})
