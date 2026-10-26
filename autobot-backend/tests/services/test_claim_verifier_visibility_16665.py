# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The claim verifier reads the KB as the calling user (#16665): its RAG leg and verdict cache never cross users."""

from unittest.mock import AsyncMock

import pytest

from knowledge.ownership import KnowledgeOwnership
from services.claim_verifier import ClaimVerifier
from services.knowledge_grounding_models import Claim, ClaimType, KBStatus


@pytest.fixture
def mock_knowledge_base():
    kb = AsyncMock()
    kb.search = AsyncMock()
    kb.ownership_manager = KnowledgeOwnership(None)
    return kb


@pytest.fixture
def claim_verifier(mock_knowledge_base):
    return ClaimVerifier(mock_knowledge_base, AsyncMock())


class TestReadsAreScopedToTheUser:
    """#16665: the RAG leg and the verdict cache never cross users."""

    @pytest.mark.asyncio
    async def test_kb_rag_search_never_uses_another_users_private_fact(self, claim_verifier, mock_knowledge_base):
        mock_knowledge_base.search.return_value = [
            {
                "node_id": "n1",
                "content": "alices private note",
                "score": 0.9,
                "metadata": {"owner_id": "alice", "visibility": "private"},
            }
        ]

        for_bob = await claim_verifier.kb_rag_search("latency", "bob")
        for_alice = await claim_verifier.kb_rag_search("latency", "alice")
        for_nobody = await claim_verifier.kb_rag_search("latency")

        assert for_bob.matches == [] and for_nobody.matches == []
        assert [m.text for m in for_alice.matches] == ["alices private note"]

    @pytest.mark.asyncio
    async def test_a_cached_verdict_is_not_served_to_another_user(self, claim_verifier, mock_knowledge_base):
        mock_knowledge_base.search.return_value = [
            {
                "node_id": "n1",
                "content": "alices private note",
                "score": 0.95,
                "metadata": {"owner_id": "alice", "visibility": "private"},
            }
        ]
        claim = Claim(claim_text="private latency", claim_type=ClaimType.FACTUAL, kb_status=KBStatus.UNKNOWN)

        for_alice = await claim_verifier.verify(claim, "alice")
        for_bob = await claim_verifier.verify(claim, "bob")

        assert for_alice.source_text == "alices private note"
        assert for_bob.source_text != "alices private note"
