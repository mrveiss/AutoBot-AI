# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the grounding:stats counters (#14981).

record_grounding_stats and record_conflict_resolved are tested directly, in
isolation from the LLM/KB pipeline: what they must prove is that each counter
moves by the right amount for the right event, not that claim extraction or
verification still works. The last two tests prove GroundedAgent is wired to them.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.grounded_agent import GroundedAgent
from services.grounded_agent_models import Claim, ClaimStatus, VerifiedClaim
from services.grounding_stats import record_conflict_resolved, record_grounding_stats
from services.knowledge_grounding_models import VerificationMethod
from tests.fixtures import make_async_redis, make_redis_pipeline

_KEY = "grounding:stats"


@pytest.fixture
def sample_claim():
    """One extracted claim to verify."""
    return Claim(
        claim_text="System latency increased by 15%",
        subject="System latency",
        predicate="increased by",
        object="15%",
        confidence=0.95,
    )


@pytest.fixture
def stats_pipeline():
    """The mock pipeline record_grounding_stats writes through."""
    return make_redis_pipeline()


def _verified(claim: Claim, method: VerificationMethod, confidence: float) -> VerifiedClaim:
    return VerifiedClaim(
        claim=claim,
        kb_status=ClaimStatus.IN_KB,
        confidence=confidence,
        verification_method=method.value,
    )


@pytest.mark.asyncio
async def test_record_grounding_stats_increments_every_counter(stats_pipeline, sample_claim):
    """One event: every counter it touches moves by the exact amount."""
    verified = [
        _verified(sample_claim, VerificationMethod.KB_LOOKUP, 0.9),
        _verified(sample_claim, VerificationMethod.CLAIM_VERIFIER_RAG, 0.7),
    ]

    await record_grounding_stats(
        make_async_redis(pipeline=stats_pipeline),
        claims_extracted=3,
        verified_claims=verified,
        conflicts_created=1,
        overall_confidence=0.8,
    )

    stats_pipeline.hincrby.assert_any_await(_KEY, "total_responses_grounded", 1)
    stats_pipeline.hincrby.assert_any_await(_KEY, "total_claims_extracted", 3)
    stats_pipeline.hincrby.assert_any_await(_KEY, "claims_verified_count", 2)
    stats_pipeline.hincrbyfloat.assert_any_await(_KEY, "confidence_sum", 0.8)
    stats_pipeline.hincrby.assert_any_await(_KEY, "conflicts_created", 1)
    stats_pipeline.hincrby.assert_any_await(_KEY, "claim_source_kb_lookup", 1)
    stats_pipeline.hincrby.assert_any_await(_KEY, "claim_source_claim_verifier_rag", 1)
    stats_pipeline.expire.assert_awaited_once()
    stats_pipeline.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_grounding_stats_omits_a_method_nobody_produced(stats_pipeline, sample_claim):
    """No claim_verifier_rag claim this call -> no write to that counter at all."""
    await record_grounding_stats(
        make_async_redis(pipeline=stats_pipeline),
        claims_extracted=1,
        verified_claims=[_verified(sample_claim, VerificationMethod.KB_LOOKUP, 0.9)],
        conflicts_created=0,
        overall_confidence=0.9,
    )

    written_fields = {call.args[1] for call in stats_pipeline.hincrby.await_args_list}
    assert "claim_source_kb_lookup" in written_fields
    assert "claim_source_claim_verifier_rag" not in written_fields


@pytest.mark.asyncio
async def test_record_grounding_stats_is_a_noop_without_redis():
    """No client (Redis disabled or circuit open) must not raise -- best-effort."""
    result = await record_grounding_stats(
        None, claims_extracted=1, verified_claims=[], conflicts_created=0, overall_confidence=0.0
    )

    assert result is None


@pytest.mark.asyncio
async def test_record_grounding_stats_swallows_a_redis_failure():
    """A stats-write failure must never fail the response the caller is waiting on."""
    redis_client = MagicMock()
    redis_client.pipeline = MagicMock(side_effect=RuntimeError("redis down"))

    await record_grounding_stats(
        redis_client, claims_extracted=1, verified_claims=[], conflicts_created=0, overall_confidence=0.0
    )

    redis_client.pipeline.assert_called_once()


@pytest.mark.asyncio
async def test_record_conflict_resolved_counts_one_and_refreshes_the_ttl():
    """One resolution moves conflicts_resolved by exactly one and keeps the hash alive."""
    redis_client = AsyncMock()

    await record_conflict_resolved(redis_client, "conflict-one")

    redis_client.hincrby.assert_awaited_once_with(_KEY, "conflicts_resolved", 1)
    redis_client.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_conflict_resolved_swallows_a_redis_failure():
    """The resolution is already stored; a counter failure must not undo or raise over it."""
    redis_client = AsyncMock()
    redis_client.hincrby.side_effect = RuntimeError("redis down")

    await record_conflict_resolved(redis_client, "conflict-one")

    redis_client.expire.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_conflict_counts_the_resolution():
    """GroundedAgent.resolve_conflict moves conflicts_resolved when a conflict actually resolves."""
    mock_redis = AsyncMock()
    with patch("services.grounded_agent.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
        result = await GroundedAgent().resolve_conflict("conflict-one", "fact-one", "Correct based on data")

    assert result["resolved"]
    mock_redis.hincrby.assert_awaited_once_with(_KEY, "conflicts_resolved", 1)
    mock_redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_grounded_agent_records_through_the_stats_module():
    """The agent hands its own client and the response's counts to record_grounding_stats."""
    agent = GroundedAgent()
    agent.redis_client = MagicMock()
    with patch("services.grounded_agent.record_grounding_stats", new=AsyncMock()) as recorder:
        await agent._record_grounding_stats(
            claims_extracted=2, verified_claims=[], conflicts_created=1, overall_confidence=0.5
        )

    recorder.assert_awaited_once_with(agent.redis_client, 2, [], 1, 0.5)
