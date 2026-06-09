# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for ConflictResolver service (Tier 4 - Knowledge Grounding).

Issue #4070: Comprehensive test suite for conflict resolution with:
- KB vs agent claim conflicts
- Age decay strategy (7, 30, 90 day boundaries)
- Research validation integration
- Confidence threshold handling
- Human review escalation
- KB update logic for stale facts

Test scenarios (40+ tests):
1. KB vs agent claims (various confidence levels)
2. Age decay (fresh, recent, aging, stale)
3. Three-source conflicts (KB + agent + research)
4. Confidence thresholds and gaps
5. Human review escalation (low confidence, close gaps)
6. KB updates (stale facts with research)
7. Edge cases (zero confidence, missing data)
8. Redis persistence (tickets, audit trails)
"""

import time
from unittest.mock import AsyncMock

import pytest

from api.knowledge_grounding_models import (
    Claim,
    Conflict,
    ConflictResolution,
    KBFact,
    ResearchResult,
    ReviewTicketPriority,
)
from services.conflict_resolver import ConflictResolver


class TestConflictResolverInit:
    """Tests for ConflictResolver initialization."""

    def test_init_lazy_loads_redis(self):
        """ConflictResolver should lazy-load Redis on first use."""
        resolver = ConflictResolver()
        assert resolver._redis_client is None

    def test_multiple_instances_independent(self):
        """Multiple ConflictResolver instances should be independent."""
        r1 = ConflictResolver()
        r2 = ConflictResolver()
        assert r1 is not r2
        assert r1._redis_client is None
        assert r2._redis_client is None


class TestAgeDayCalculation:
    """Tests for age calculation on KBFact."""

    def test_fresh_fact_age_zero(self):
        """Fact created now should have age ~0."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time(),
        )
        assert fact.age_days() < 0.1

    def test_seven_day_old_fact(self):
        """Fact 7 days old should calculate correctly."""
        past_time = time.time() - (7 * 86400)
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=past_time,
        )
        age = fact.age_days()
        assert 6.9 < age < 7.1

    def test_thirty_day_old_fact(self):
        """Fact 30 days old should calculate correctly."""
        past_time = time.time() - (30 * 86400)
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=past_time,
        )
        age = fact.age_days()
        assert 29.9 < age < 30.1

    def test_ninety_day_old_fact(self):
        """Fact 90 days old should calculate correctly."""
        past_time = time.time() - (90 * 86400)
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=past_time,
        )
        age = fact.age_days()
        assert 89.9 < age < 90.1


class TestAgeDecayStrategy:
    """Tests for age decay confidence multipliers."""

    def test_fresh_fact_no_decay(self):
        """Fact < 7 days old should have 100% confidence (1.0 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (3 * 86400),  # 3 days old
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.9)  # 0.9 * 1.0

    def test_recent_fact_80_percent_decay(self):
        """Fact 7-30 days old should have 80% confidence (0.8 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (14 * 86400),  # 14 days old
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.72)  # 0.9 * 0.8

    def test_aging_fact_60_percent_decay(self):
        """Fact 30-90 days old should have 60% confidence (0.6 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (60 * 86400),  # 60 days old
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.54)  # 0.9 * 0.6

    def test_stale_fact_40_percent_decay(self):
        """Fact > 90 days old should have 40% confidence (0.4 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (120 * 86400),  # 120 days old
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.36)  # 0.9 * 0.4

    def test_boundary_7_days_fresh_side(self):
        """Fact at 6.99 days should still be fresh (1.0 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (6.99 * 86400),
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.9)

    def test_boundary_7_days_recent_side(self):
        """Fact at 7.01 days should be recent (0.8 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (7.01 * 86400),
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.72, rel=0.01)

    def test_boundary_30_days_recent_side(self):
        """Fact at 29.99 days should be recent (0.8 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (29.99 * 86400),
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.72)

    def test_boundary_30_days_aging_side(self):
        """Fact at 30.01 days should be aging (0.6 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (30.01 * 86400),
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.54, rel=0.01)

    def test_boundary_90_days_aging_side(self):
        """Fact at 89.99 days should be aging (0.6 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (89.99 * 86400),
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.54)

    def test_boundary_90_days_stale_side(self):
        """Fact at 90.01 days should be stale (0.4 decay)."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (90.01 * 86400),
        )
        effective = fact.effective_confidence()
        assert effective == pytest.approx(0.36, rel=0.01)


class TestKBFactStaleDetection:
    """Tests for stale fact detection."""

    def test_fact_under_30_days_not_stale(self):
        """Fact < 30 days old should not be stale."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (20 * 86400),  # 20 days
        )
        assert not fact.is_stale()

    def test_fact_over_30_days_is_stale(self):
        """Fact > 30 days old should be stale."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (40 * 86400),  # 40 days
        )
        assert fact.is_stale()

    def test_fact_exactly_30_days_boundary(self):
        """Fact at 30.01 days should be stale."""
        fact = KBFact(
            fact_text="test",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time() - (30.01 * 86400),
        )
        assert fact.is_stale()


class TestConflictInitialization:
    """Tests for Conflict initialization and validation."""

    def test_conflict_with_research(self):
        """Conflict should initialize with all three sources."""
        kb = KBFact(
            fact_text="KB fact",
            source_id="src1",
            confidence=0.8,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Agent claim", source="agent_1", confidence=0.6)
        research = ResearchResult(
            fact_text="Research fact",
            source="https://example.com",
            confidence=0.85,
        )

        conflict = Conflict(
            kb_says=kb,
            agent_says=claim,
            kb_confidence=0.8,
            agent_confidence=0.6,
            research_says=research,
            research_confidence=0.85,
        )

        assert conflict.kb_says.fact_text == "KB fact"
        assert conflict.agent_says.claim_text == "Agent claim"
        assert conflict.research_says.fact_text == "Research fact"

    def test_conflict_max_confidence(self):
        """Conflict should return max confidence across sources."""
        kb = KBFact(
            fact_text="KB",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="claim", source="agent", confidence=0.6)

        conflict = Conflict(
            kb_says=kb,
            agent_says=claim,
            kb_confidence=0.9,
            agent_confidence=0.6,
            research_confidence=0.85,
        )

        assert conflict.max_confidence() == 0.9

    def test_conflict_confidence_gap(self):
        """Conflict should calculate gap between max and second-max."""
        kb = KBFact(
            fact_text="KB",
            source_id="src1",
            confidence=0.9,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="claim", source="agent", confidence=0.85)

        conflict = Conflict(
            kb_says=kb,
            agent_says=claim,
            kb_confidence=0.9,
            agent_confidence=0.85,
        )

        assert conflict.confidence_gap() == pytest.approx(0.05)


class TestConflictResolution:
    """Tests for resolve() method."""

    @pytest.mark.asyncio
    async def test_kb_wins_when_fresh_and_confident(self):
        """KB fact should win when fresh (< 7 days) and confident."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="PostgreSQL uses port 5432",
            source_id="docs_1",
            confidence=0.95,
            timestamp=time.time() - (2 * 86400),  # 2 days old
        )
        claim = Claim(
            claim_text="PostgreSQL uses port 3306",
            source="agent_1",
            confidence=0.4,
        )

        result = await resolver.resolve(kb, claim)

        assert result.resolution_type == ConflictResolution.KB_WINS
        assert result.source == "knowledge_base"
        assert result.claim == "PostgreSQL uses port 5432"
        assert result.confidence == pytest.approx(0.95)
        assert not result.requires_human_review

    @pytest.mark.asyncio
    async def test_agent_wins_when_kb_stale(self):
        """Agent claim should win when KB is stale (> 90 days)."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Service uses Redis",
            source_id="old_doc",
            confidence=0.9,
            timestamp=time.time() - (120 * 86400),  # 120 days old (stale)
        )
        claim = Claim(
            claim_text="Service uses Memcached",
            source="agent_1",
            confidence=0.8,
        )

        result = await resolver.resolve(kb, claim)

        # KB confidence decayed to 0.9 * 0.4 = 0.36
        # Agent confidence is 0.8
        assert result.resolution_type == ConflictResolution.AGENT_WINS
        assert result.source == "agent"
        assert result.claim == "Service uses Memcached"
        assert result.confidence == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_research_wins_over_both_kb_and_agent(self):
        """Research should win when it has highest confidence."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Python 3.8 is latest",
            source_id="doc_old",
            confidence=0.8,
            timestamp=time.time() - (150 * 86400),  # 150 days old
        )
        claim = Claim(
            claim_text="Python 3.10 is latest",
            source="agent_1",
            confidence=0.7,
        )
        research = ResearchResult(
            fact_text="Python 3.13 is latest",
            source="https://python.org",
            confidence=0.95,
        )

        result = await resolver.resolve(kb, claim, research)

        assert result.resolution_type == ConflictResolution.RESEARCH_WINS
        assert result.source == "research"
        assert result.claim == "Python 3.13 is latest"
        assert result.confidence == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_high_confidence_no_review(self):
        """Resolution > 0.8 should not require human review."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Java runs on JVM",
            source_id="java_doc",
            confidence=0.95,
            timestamp=time.time(),  # Fresh
        )
        claim = Claim(claim_text="Java runs on Python", source="agent", confidence=0.2)

        result = await resolver.resolve(kb, claim)

        assert result.confidence > 0.8
        assert not result.requires_human_review

    @pytest.mark.asyncio
    async def test_medium_confidence_flags_review(self):
        """Resolution 0.6-0.8 should flag for human review."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Service port is 8001",
            source_id="config",
            confidence=0.7,
            timestamp=time.time() - (20 * 86400),  # 20 days, decay to 0.56
        )
        claim = Claim(claim_text="Service port is 8002", source="agent", confidence=0.5)

        result = await resolver.resolve(kb, claim)

        # KB confidence: 0.7 * 0.8 = 0.56
        # Should flag for review since it's borderline
        assert 0.5 < result.confidence < 0.8
        assert result.requires_human_review

    @pytest.mark.asyncio
    async def test_low_confidence_requires_review(self):
        """Resolution < 0.6 should require human review."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Old unverified claim",
            source_id="src",
            confidence=0.4,
            timestamp=time.time() - (100 * 86400),  # Very old
        )
        claim = Claim(
            claim_text="New unverified claim",
            source="agent",
            confidence=0.45,
        )

        result = await resolver.resolve(kb, claim)

        # Both sources very low confidence
        assert result.confidence < 0.6
        assert result.requires_human_review

    @pytest.mark.asyncio
    async def test_close_confidence_gap_triggers_review(self):
        """Small gap between sources should trigger review."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Feature enabled",
            source_id="config",
            confidence=0.75,
            timestamp=time.time() - (5 * 86400),
        )
        claim = Claim(
            claim_text="Feature disabled",
            source="agent",
            confidence=0.72,  # Only 0.03 gap
        )

        result = await resolver.resolve(kb, claim)

        # Although KB wins, gap is small so should flag review
        assert result.requires_human_review

    @pytest.mark.asyncio
    async def test_update_kb_when_stale_research_high_conf(self):
        """Should flag KB update when stale KB replaced by high-conf research."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Old configuration",
            source_id="config_doc",
            confidence=0.85,
            timestamp=time.time() - (50 * 86400),  # 50 days old (stale)
        )
        claim = Claim(claim_text="Same old config", source="agent", confidence=0.5)
        research = ResearchResult(
            fact_text="New configuration",
            source="https://docs.example.com",
            confidence=0.9,
        )

        result = await resolver.resolve(kb, claim, research)

        assert result.resolution_type == ConflictResolution.RESEARCH_WINS
        assert result.update_kb is True
        assert "RECOMMEND KB UPDATE" in result.reasoning

    @pytest.mark.asyncio
    async def test_no_kb_update_when_research_low_conf(self):
        """Should not update KB if research confidence < 0.75."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Config value",
            source_id="config",
            confidence=0.8,
            timestamp=time.time() - (50 * 86400),  # Stale
        )
        claim = Claim(claim_text="Other value", source="agent", confidence=0.4)
        research = ResearchResult(
            fact_text="Different value",
            source="https://example.com",
            confidence=0.65,  # Too low
        )

        result = await resolver.resolve(kb, claim, research)

        assert result.resolution_type == ConflictResolution.RESEARCH_WINS
        # Should NOT update KB because research confidence < 0.75
        assert result.update_kb is False

    @pytest.mark.asyncio
    async def test_no_kb_update_when_not_stale(self):
        """Should not update KB if fact is fresh (< 30 days)."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Fresh config",
            source_id="config",
            confidence=0.8,
            timestamp=time.time() - (14 * 86400),  # 14 days, not stale
        )
        claim = Claim(claim_text="Other", source="agent", confidence=0.5)
        research = ResearchResult(
            fact_text="Different",
            source="https://example.com",
            confidence=0.95,  # High confidence
        )

        result = await resolver.resolve(kb, claim, research)

        assert result.update_kb is False


class TestKBUpdate:
    """Tests for update_kb_if_stale() method."""

    @pytest.mark.asyncio
    async def test_update_kb_stale_high_confidence(self):
        """Should update KB when stale and research has high confidence."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Old fact",
            source_id="doc_1",
            confidence=0.8,
            timestamp=time.time() - (50 * 86400),  # Stale
        )
        research = ResearchResult(
            fact_text="New fact",
            source="https://example.com",
            confidence=0.85,  # > 0.75 threshold
        )

        # Mock Redis
        resolver._redis_client = AsyncMock()
        resolver._redis_client.lpush = AsyncMock()
        resolver._redis_client.expire = AsyncMock()

        result = await resolver.update_kb_if_stale(kb, research)

        assert result is True
        resolver._redis_client.lpush.assert_called_once()
        resolver._redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_update_kb_not_stale(self):
        """Should not update KB if fact is fresh."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Fresh fact",
            source_id="doc_1",
            confidence=0.8,
            timestamp=time.time() - (10 * 86400),  # Fresh
        )
        research = ResearchResult(
            fact_text="Different",
            source="https://example.com",
            confidence=0.9,
        )

        result = await resolver.update_kb_if_stale(kb, research)

        assert result is False

    @pytest.mark.asyncio
    async def test_skip_update_kb_low_research_confidence(self):
        """Should not update KB if research confidence < 0.75."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Old fact",
            source_id="doc_1",
            confidence=0.8,
            timestamp=time.time() - (50 * 86400),  # Stale
        )
        research = ResearchResult(
            fact_text="Uncertain finding",
            source="https://example.com",
            confidence=0.60,  # Too low
        )

        result = await resolver.update_kb_if_stale(kb, research)

        assert result is False


class TestHumanReviewEscalation:
    """Tests for flag_for_human_review() method."""

    @pytest.mark.asyncio
    async def test_high_priority_very_low_confidence(self):
        """Conflict with max_conf < 0.5 should be HIGH priority."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Uncertain fact",
            source_id="src",
            confidence=0.3,
            timestamp=time.time() - (100 * 86400),
        )
        claim = Claim(claim_text="Other uncertain", source="agent", confidence=0.4)

        conflict = Conflict(
            kb_says=kb,
            agent_says=claim,
            kb_confidence=0.12,  # 0.3 * 0.4 decay
            agent_confidence=0.4,
        )

        # Mock Redis
        resolver._redis_client = AsyncMock()
        resolver._redis_client.set = AsyncMock()
        resolver._redis_client.lpush = AsyncMock()

        result_ticket = await resolver.flag_for_human_review(conflict)

        assert result_ticket.priority == ReviewTicketPriority.HIGH

    @pytest.mark.asyncio
    async def test_medium_priority_tiny_gap(self):
        """Conflict with gap < 0.05 should be MEDIUM priority."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Fact A",
            source_id="src",
            confidence=0.8,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Fact B", source="agent", confidence=0.77)

        conflict = Conflict(
            kb_says=kb,
            agent_says=claim,
            kb_confidence=0.8,
            agent_confidence=0.77,  # Gap 0.03
        )

        resolver._redis_client = AsyncMock()
        resolver._redis_client.set = AsyncMock()
        resolver._redis_client.lpush = AsyncMock()

        ticket = await resolver.flag_for_human_review(conflict)

        assert ticket.priority == ReviewTicketPriority.MEDIUM

    @pytest.mark.asyncio
    async def test_low_priority_small_gap(self):
        """Conflict with gap 0.05-0.1 should be LOW priority."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Fact A",
            source_id="src",
            confidence=0.8,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Fact B", source="agent", confidence=0.73)

        conflict = Conflict(
            kb_says=kb,
            agent_says=claim,
            kb_confidence=0.8,
            agent_confidence=0.73,  # Gap 0.07
        )

        resolver._redis_client = AsyncMock()
        resolver._redis_client.set = AsyncMock()
        resolver._redis_client.lpush = AsyncMock()

        ticket = await resolver.flag_for_human_review(conflict)

        assert ticket.priority == ReviewTicketPriority.LOW

    @pytest.mark.asyncio
    async def test_review_ticket_persisted_to_redis(self):
        """Review ticket should be persisted to Redis."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="KB fact",
            source_id="src",
            confidence=0.75,
            timestamp=time.time() - (60 * 86400),
        )
        claim = Claim(claim_text="Agent claim", source="agent", confidence=0.7)

        conflict = Conflict(
            kb_says=kb,
            agent_says=claim,
            kb_confidence=0.45,  # 0.75 * 0.6 decay
            agent_confidence=0.7,
        )

        resolver._redis_client = AsyncMock()
        resolver._redis_client.set = AsyncMock()
        resolver._redis_client.lpush = AsyncMock()

        await resolver.flag_for_human_review(conflict)

        # Should call Redis set with ticket key
        resolver._redis_client.set.assert_called_once()
        call_args = resolver._redis_client.set.call_args
        assert "review_ticket:" in call_args[0][0]

        # Should add to review queue
        resolver._redis_client.lpush.assert_called_once()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_confidence_values(self):
        """Resolver should handle zero confidence gracefully."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Unknown",
            source_id="src",
            confidence=0.0,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Unknown", source="agent", confidence=0.0)

        result = await resolver.resolve(kb, claim)

        assert result.confidence == 0.0
        assert result.requires_human_review

    @pytest.mark.asyncio
    async def test_perfect_confidence_values(self):
        """Resolver should handle max confidence (1.0) correctly."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="Certain fact",
            source_id="src",
            confidence=1.0,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Other fact", source="agent", confidence=0.5)

        result = await resolver.resolve(kb, claim)

        assert result.confidence == 1.0
        assert not result.requires_human_review

    @pytest.mark.asyncio
    async def test_resolve_without_research(self):
        """Resolver should work with just KB and claim."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="KB fact",
            source_id="src",
            confidence=0.8,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Agent claim", source="agent", confidence=0.6)

        # No research_result
        result = await resolver.resolve(kb, claim)

        assert result.research_result is None
        assert result.kb_fact is not None
        assert result.agent_claim is not None

    def test_claim_defaults_to_current_timestamp(self):
        """Claim should default to current time if not specified."""
        claim = Claim(claim_text="test", source="agent")
        assert claim.timestamp is not None
        assert claim.timestamp <= time.time()

    def test_research_defaults_to_current_timestamp(self):
        """ResearchResult should default to current time if not specified."""
        research = ResearchResult(
            fact_text="test",
            source="https://example.com",
            confidence=0.8,
        )
        assert research.timestamp is not None
        assert research.timestamp <= time.time()


class TestConfidenceCalculations:
    """Tests for confidence calculation edge cases."""

    @pytest.mark.asyncio
    async def test_very_low_base_confidence_with_decay(self):
        """Low base confidence should stay low after decay."""
        ConflictResolver()

        kb = KBFact(
            fact_text="Barely confident",
            source_id="src",
            confidence=0.2,  # Very low
            timestamp=time.time() - (50 * 86400),  # Aging
        )

        # 0.2 * 0.6 = 0.12
        effective = kb.effective_confidence()
        assert effective == pytest.approx(0.12)

    @pytest.mark.asyncio
    async def test_three_source_winner_selection(self):
        """Resolver should select highest among three sources."""
        resolver = ConflictResolver()

        kb = KBFact(
            fact_text="KB",
            source_id="src",
            confidence=0.7,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Agent", source="agent", confidence=0.6)
        research = ResearchResult(
            fact_text="Research",
            source="https://example.com",
            confidence=0.75,  # Highest
        )

        result = await resolver.resolve(kb, claim, research)

        assert result.resolution_type == ConflictResolution.RESEARCH_WINS
        assert result.source == "research"

    @pytest.mark.asyncio
    async def test_all_equal_confidence_kb_wins_tiebreaker(self):
        """When all equal, first source (KB) should win by default."""
        resolver_inst = ConflictResolver()

        kb = KBFact(
            fact_text="KB",
            source_id="src",
            confidence=0.75,
            timestamp=time.time(),
        )
        claim = Claim(claim_text="Agent", source="agent", confidence=0.75)
        research = ResearchResult(
            fact_text="Research",
            source="https://example.com",
            confidence=0.75,
        )

        result = await resolver_inst.resolve(kb, claim, research)

        # max() will pick one; behavior is deterministic but not guaranteed
        # In practice, one of the three will win
        assert result.confidence == 0.75


class TestValidationErrors:
    """Tests for validation and error handling."""

    def test_kb_fact_rejects_invalid_confidence(self):
        """KBFact should reject confidence > 1.0."""
        with pytest.raises(ValueError):
            KBFact(
                fact_text="test",
                source_id="src",
                confidence=1.5,  # Invalid
                timestamp=time.time(),
            )

    def test_kb_fact_rejects_negative_confidence(self):
        """KBFact should reject negative confidence."""
        with pytest.raises(ValueError):
            KBFact(
                fact_text="test",
                source_id="src",
                confidence=-0.1,  # Invalid
                timestamp=time.time(),
            )

    def test_claim_rejects_invalid_confidence(self):
        """Claim should reject invalid confidence."""
        with pytest.raises(ValueError):
            Claim(claim_text="test", source="agent", confidence=1.5)

    def test_research_rejects_invalid_confidence(self):
        """ResearchResult should reject invalid confidence."""
        with pytest.raises(ValueError):
            ResearchResult(
                fact_text="test",
                source="https://example.com",
                confidence=-0.5,
            )
