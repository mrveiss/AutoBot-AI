# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One malformed claim item must not drop the good claims in the same LLM response (#14678)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.grounded_agent import GroundedAgent


@pytest.mark.asyncio
async def test_out_of_range_confidence_skips_only_that_item():
    """Before: Claim() raised inside one try, the outer except returned [] for everything."""
    good = {"claim_text": "ok", "subject": "a", "predicate": "b", "object": "c", "confidence": 0.5}
    bad = {"claim_text": "bad", "confidence": 85}
    agent = GroundedAgent()
    agent.llm_service = AsyncMock()
    agent.llm_service.chat = AsyncMock(return_value=MagicMock(content=json.dumps([bad, good])))

    claims = await agent._extract_claims("Q", "A")

    assert [c.claim_text for c in claims] == ["ok"]
