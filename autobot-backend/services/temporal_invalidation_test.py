#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Temporal knowledge invalidation: rules, sweeps, contradictions and statistics.

#14979: this file was a hand-run driver. ``TestTemporalInvalidation`` was named
to be collected but defined ``__init__``, and pytest refuses such a class --
``PytestCollectionWarning``, then it moves on. All eight ``test_*`` methods were
dead text, while every signal a reader had (a ``*_test.py`` name inside a
collected tree, a ``Test*`` class, a clean import) said they ran.

Nothing here needs a live service. ``MockFactExtractionService`` is the only
fact store, and the rule store the service keeps in Redis is an in-process
``fakeredis`` (see ``setup_method``). Beyond the class shape, four things the
driver hid had to be fixed for the methods to mean anything:

* ``test_actual_invalidation_sweep`` depended on ``run_all_tests`` having called
  the dry-run test first. Alone it returned "No invalidation rules available"
  and asserted on the error response.
* Every method ended on ``return <value>``, which would have moved them straight
  into #14920's population once collected.
* Fixture facts were built with a naive ``datetime.now()``, which makes
  ``InvalidationRule.matches_fact`` raise ``TypeError`` against its
  timezone-aware ``now``. The single production producer
  (``agents/knowledge_extraction_agent.py``) passes an aware value, so this was
  the fixture's bug, not the service's.
* Three assertions were conditional on the thing they were checking
  (``if stats["recent_sweeps"] > 0: assert ...``), so they passed when the
  behaviour was absent.
"""

from datetime import datetime, timedelta, timezone

import fakeredis.aioredis as fakeredis_async

from models.atomic_fact import AtomicFact, FactType, TemporalType
from services.temporal_invalidation_service import (
    InvalidationReason,
    InvalidationRule,
    TemporalInvalidationService,
)


class MockFactExtractionService:
    """Mock fact extraction service for testing temporal invalidation."""

    def __init__(self) -> None:
        self.facts_db = []
        self.next_fact_id = 1

    def add_test_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        fact_type: FactType = FactType.FACT,
        temporal_type: TemporalType = TemporalType.DYNAMIC,
        confidence: float = 0.8,
        age_days: int = 0,
        active: bool = True,
    ) -> AtomicFact:
        """Add a test fact to the mock database."""
        fact = AtomicFact(
            subject=subject,
            predicate=predicate,
            object=object,
            fact_type=fact_type,
            temporal_type=temporal_type,
            confidence=confidence,
            source="test",
            extraction_method="manual",
            entities=[subject, object],
            valid_from=datetime.now(tz=timezone.utc) - timedelta(days=age_days),
            is_active=active,
            fact_id=f"test_fact_{self.next_fact_id}",
        )
        self.next_fact_id += 1
        self.facts_db.append(fact)
        return fact

    async def get_facts_by_criteria(
        self,
        source=None,
        fact_type=None,
        temporal_type=None,
        min_confidence=None,
        active_only=True,
        limit=1000,
    ):
        """Mock implementation of get_facts_by_criteria."""
        filtered_facts = []

        for fact in self.facts_db:
            # Apply filters
            if active_only and not fact.is_active:
                continue
            if source and fact.source != source:
                continue
            if fact_type and fact.fact_type != fact_type:
                continue
            if temporal_type and fact.temporal_type != temporal_type:
                continue
            if min_confidence and fact.confidence < min_confidence:
                continue

            filtered_facts.append(fact)

            if len(filtered_facts) >= limit:
                break

        return filtered_facts


class TestTemporalInvalidation:
    """Test cases for temporal knowledge invalidation functionality."""

    def setup_method(self) -> None:
        self.mock_fact_service = MockFactExtractionService()
        self.invalidation_service = TemporalInvalidationService(self.mock_fact_service)
        # The service keeps its rule set, its invalidated-fact set and its sweep
        # history in Redis, and the backend conftest replaces
        # `autobot_shared.redis_client` with a socket-free stand-in whose
        # `get_async_redis_client()` returns None (#14932). Without a store the
        # service answers `{"error": "Redis client not available"}` and five of
        # these eight tests assert nothing about invalidation. Injecting the
        # in-process fake -- the same one `services/workflow_redis_backfill_test.py`
        # and `llm_shared/tests/test_provider_degradation.py` use -- makes them
        # exercise the real rule store rather than skip.
        # `_ensure_redis` only reaches for a client when this is still None.
        self.invalidation_service.redis_client = fakeredis_async.FakeRedis(
            server=fakeredis_async.FakeServer(), decode_responses=True
        )

        # Create test facts with various temporal characteristics
        self._setup_test_facts()

    # One row per fixture fact, so the table is readable as a table and the
    # thresholds each row is chosen to sit either side of stay next to the value
    # that decides it. The attribute name is first because the tests below reach
    # for these by name.
    _FIXTURE_FACTS = (
        # attribute, subject, predicate, object, fact_type, temporal_type, confidence, age_days
        ("old_dynamic_fact", "AutoBot", "version is", "1.0", FactType.FACT, TemporalType.DYNAMIC, 0.8, 45),
        # 15 days: inside the 30-day dynamic rule, so it must NOT match.
        (
            "recent_dynamic_fact",
            "Python",
            "is popular for",
            "data science",
            FactType.FACT,
            TemporalType.DYNAMIC,
            0.9,
            15,
        ),
        # 120 days: past the 90-day rule for predictions.
        (
            "old_prediction",
            "AI",
            "will revolutionize",
            "healthcare by 2023",
            FactType.PREDICTION,
            TemporalType.TEMPORAL_BOUND,
            0.7,
            120,
        ),
        # A year old and still valid, because STATIC is exempt from age rules.
        ("static_fact", "Python", "was created by", "Guido van Rossum", FactType.FACT, TemporalType.STATIC, 0.95, 365),
        # 0.4 confidence, below the 0.6 threshold.
        (
            "low_confidence_fact",
            "AutoBot",
            "might support",
            "new feature",
            FactType.FACT,
            TemporalType.DYNAMIC,
            0.4,
            10,
        ),
        # 200 days: past the 180-day rule for opinions.
        ("old_opinion", "I", "think", "AutoBot is great", FactType.OPINION, TemporalType.ATEMPORAL, 0.6, 200),
        # 2 days: past the 1-day rule for test sources.
        ("test_source_fact", "TestEntity", "has property", "test value", FactType.FACT, TemporalType.DYNAMIC, 0.8, 2),
    )

    def _setup_test_facts(self) -> None:
        """Build the fixture facts, one per row of ``_FIXTURE_FACTS``."""
        for attribute, subject, predicate, obj, fact_type, temporal_type, confidence, age_days in self._FIXTURE_FACTS:
            setattr(
                self,
                attribute,
                self.mock_fact_service.add_test_fact(
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    fact_type=fact_type,
                    temporal_type=temporal_type,
                    confidence=confidence,
                    age_days=age_days,
                ),
            )
        # `add_test_fact` hard-codes source="test"; the test-source rule matches
        # on the pattern "test", so this is set explicitly to say so out loud.
        self.test_source_fact.source = "test_data"

    def _assert_rule_matches(self, rule, fact, expected_reason) -> None:
        """The rule matches this fact, and cites the reason it is meant to cite.

        Asserting the reason and not merely the match is what separates the
        rules: three of the fixtures are old enough to trip an age limit before
        the rule's own condition is ever consulted, so a bare `assert matches`
        stays green with `min_confidence` and `source_patterns` disabled.
        """
        matches, reason = rule.matches_fact(fact)
        assert matches, f"{rule.name} should match {fact.subject} {fact.predicate} {fact.object}"
        assert reason is expected_reason, f"{rule.name}: expected {expected_reason}, got {reason}"

    def _fresh_fact(self, subject: str, predicate: str, obj: str, confidence: float = 0.8) -> AtomicFact:
        """A same-day fact, too young for any age rule to claim it."""
        return self.mock_fact_service.add_test_fact(
            subject=subject,
            predicate=predicate,
            object=obj,
            temporal_type=TemporalType.DYNAMIC,
            confidence=confidence,
            age_days=0,
        )

    async def test_invalidation_rules_initialization(self):
        """Test initialization of invalidation rules."""

        result = await self.invalidation_service.initialize_rules()

        assert result["status"] == "success", "Rules initialization should succeed"
        assert result["total_rules"] >= 5, "Should have at least 5 default rules"

    async def test_invalidation_rule_matching(self):
        """Each default rule matches the fixture written for it, for the stated reason."""
        checked = 0
        for rule in self.invalidation_service.default_rules:
            if "Dynamic Facts" in rule.name:
                self._assert_rule_matches(rule, self.old_dynamic_fact, InvalidationReason.TEMPORAL_EXPIRY)
                matches_recent, _ = rule.matches_fact(self.recent_dynamic_fact)
                assert not matches_recent, f"{rule.name} should not match a 15-day-old dynamic fact"

            elif "Predictions" in rule.name:
                self._assert_rule_matches(rule, self.old_prediction, InvalidationReason.TEMPORAL_EXPIRY)

            elif "Low Confidence" in rule.name:
                self._assert_rule_matches(rule, self.low_confidence_fact, InvalidationReason.TEMPORAL_EXPIRY)
                fresh = self._fresh_fact("AutoBot", "might support", "another new feature", confidence=0.4)
                self._assert_rule_matches(rule, fresh, InvalidationReason.CONFIDENCE_THRESHOLD)

            elif "Test Sources" in rule.name:
                self._assert_rule_matches(rule, self.test_source_fact, InvalidationReason.TEMPORAL_EXPIRY)
                fresh = self._fresh_fact("TestEntity", "has property", "fresh test value")
                fresh.source = "test_data"
                self._assert_rule_matches(rule, fresh, InvalidationReason.SOURCE_OUTDATED)

            else:
                continue
            checked += 1

        assert checked >= 4, f"only {checked} of the default rules were exercised"

    async def test_dry_run_invalidation_sweep(self):
        """Test invalidation sweep in dry run mode."""

        # Initialize rules first
        await self.invalidation_service.initialize_rules()

        # Run dry run sweep
        result = await self.invalidation_service.run_invalidation_sweep(dry_run=True)

        # Validate results
        assert result["status"] == "success", "Dry run should succeed"
        assert result["dry_run"] is True, "Should indicate dry run mode"
        assert result["facts_processed"] > 0, "Should process some facts"
        assert result["facts_invalidated"] == 0, "Should not actually invalidate in dry run"

        # The fixtures deliberately include facts every default rule should
        # catch, so a dry run that identifies none is a broken sweep, not an
        # empty one -- and a count with no samples behind it is a number the
        # caller cannot act on.
        identified = result["facts_identified_for_invalidation"]
        assert identified > 0, "The fixture facts should be identified for invalidation"
        samples = result.get("sample_facts_to_invalidate", [])
        assert samples, "An identified fact must be reported with its sample"
        for sample in samples:
            assert sample["statement"], "Every sample names the fact it would invalidate"
            assert sample["reason"], "Every sample carries the rule that matched"

    async def test_actual_invalidation_sweep(self):
        """A non-dry-run sweep reports every processed fact and invalidates the stale ones."""
        # The rule store is per-test, so the rules have to exist before the
        # sweep looks for them. In the hand-run driver this test only ever
        # succeeded because `run_all_tests` had called the dry-run test first
        # against a shared Redis -- run alone, it returned "No invalidation
        # rules available" and nobody could see it.
        await self.invalidation_service.initialize_rules()

        active_facts_before = await self.mock_fact_service.get_facts_by_criteria(active_only=True)
        assert active_facts_before, "The fixtures must start active for the sweep to have subjects"

        result = await self.invalidation_service.run_invalidation_sweep(dry_run=False)

        assert result["status"] == "success", "Actual sweep should succeed"
        assert result["dry_run"] is False, "Should indicate actual run mode"
        assert result["facts_processed"] == len(active_facts_before), "Every active fact must be examined"
        assert result["facts_invalidated"] > 0, "A real sweep must invalidate the facts it identifies"

    async def test_contradiction_detection(self):
        """Test contradiction detection between facts."""

        # Create contradictory facts
        fact1 = self.mock_fact_service.add_test_fact(
            subject="AutoBot",
            predicate="version is",
            object="1.0",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.7,
        )

        fact2 = self.mock_fact_service.add_test_fact(
            subject="AutoBot",
            predicate="version is",
            object="2.0",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.9,  # Higher confidence
        )

        # Test contradiction detection
        result = await self.invalidation_service.invalidate_contradictory_facts(fact2)

        assert result["status"] == "success", "Contradiction check should succeed"
        assert fact1.is_contradictory_to(fact2), "Two different values for the same subject/predicate contradict"
        assert result["contradictions_found"] >= 1, "The superseded fact must be found"

    async def test_invalidation_statistics(self):
        """Test invalidation statistics collection."""

        # Run some invalidation operations first
        await self.invalidation_service.initialize_rules()
        await self.invalidation_service.run_invalidation_sweep(dry_run=True)

        # Get statistics
        stats = await self.invalidation_service.get_invalidation_statistics()

        # Validate statistics structure
        assert isinstance(stats, dict), "Should return statistics dictionary"
        assert "total_rules" in stats, "Should include total rules count"
        assert "enabled_rules" in stats, "Should include enabled rules count"

        # A sweep just ran, so the history behind these numbers is not empty --
        # the original made this conditional on the very thing it was checking.
        assert stats["recent_sweeps"] > 0, "The sweep above must appear in the history"
        assert "average_processing_time" in stats, "Should include average processing time"

    async def test_rule_management(self):
        """Test adding and removing invalidation rules."""

        # Create a custom rule
        custom_rule = InvalidationRule(
            rule_id="test_custom_rule",
            name="Test Custom Rule",
            temporal_types=[TemporalType.DYNAMIC],
            max_age_days=5,
            min_confidence=0.9,
            enabled=True,
        )

        # Add the rule
        add_result = await self.invalidation_service.add_invalidation_rule(custom_rule)

        assert add_result["status"] == "success", "Should successfully add custom rule"

        # Remove the rule
        remove_result = await self.invalidation_service.remove_invalidation_rule("test_custom_rule")

        assert remove_result["status"] == "success", "Should successfully remove custom rule"

        # Try to remove non-existent rule
        remove_nonexistent = await self.invalidation_service.remove_invalidation_rule("nonexistent_rule")

        assert remove_nonexistent["status"] == "error", "Should fail to remove non-existent rule"

    async def test_temporal_type_behavior(self):
        """Test invalidation behavior for different temporal types."""

        temporal_test_results = {}

        # Test each temporal type
        for temporal_type in TemporalType:
            test_fact = self.mock_fact_service.add_test_fact(
                subject="TestEntity",
                predicate="has property",
                object=f"value for {temporal_type.value}",
                fact_type=FactType.FACT,
                temporal_type=temporal_type,
                confidence=0.8,
                age_days=50,  # Old enough to trigger most rules
            )

            # Check which rules would apply
            applicable_rules = []
            for rule in self.invalidation_service.default_rules:
                matches, reason = rule.matches_fact(test_fact)
                if matches:
                    applicable_rules.append((rule.name, reason.value))

            temporal_test_results[temporal_type.value] = len(applicable_rules)

        # Validate expectations
        # STATIC facts should have fewer applicable rules
        assert temporal_test_results.get("STATIC", 0) <= temporal_test_results.get(
            "DYNAMIC", 0
        ), "Static facts should have fewer or equal applicable rules than dynamic facts"
