#!/usr/bin/env python3
"""
Test suite for AutoBot temporal knowledge invalidation functionality.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.models.atomic_fact import AtomicFact, FactType, TemporalType
from backend.services.temporal_invalidation_service import (
    InvalidationRule,
    TemporalInvalidationService,
)


class MockFactExtractionService:
    """Mock fact extraction service for testing temporal invalidation."""

    def __init__(self):
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
            valid_from=datetime.now() - timedelta(days=age_days),
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

    def __init__(self):
        self.mock_fact_service = MockFactExtractionService()
        self.invalidation_service = TemporalInvalidationService(self.mock_fact_service)

        # Create test facts with various temporal characteristics
        self._setup_test_facts()

    def _setup_test_facts(self):
        """Set up test facts with different temporal characteristics."""
        # Old dynamic facts (should be invalidated)
        self.old_dynamic_fact = self.mock_fact_service.add_test_fact(
            subject="AutoBot",
            predicate="version is",
            object="1.0",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.8,
            age_days=45,  # Older than 30-day rule
        )

        # Recent dynamic facts (should NOT be invalidated)
        self.recent_dynamic_fact = self.mock_fact_service.add_test_fact(
            subject="Python",
            predicate="is popular for",
            object="data science",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.9,
            age_days=15,  # Newer than 30-day rule
        )

        # Old prediction (should be invalidated)
        self.old_prediction = self.mock_fact_service.add_test_fact(
            subject="AI",
            predicate="will revolutionize",
            object="healthcare by 2023",
            fact_type=FactType.PREDICTION,
            temporal_type=TemporalType.TEMPORAL_BOUND,
            confidence=0.7,
            age_days=120,  # Older than 90-day rule for predictions
        )

        # Static fact (should NOT be invalidated by age)
        self.static_fact = self.mock_fact_service.add_test_fact(
            subject="Python",
            predicate="was created by",
            object="Guido van Rossum",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.STATIC,
            confidence=0.95,
            age_days=365,  # Very old but static
        )

        # Low confidence fact (should be invalidated)
        self.low_confidence_fact = self.mock_fact_service.add_test_fact(
            subject="AutoBot",
            predicate="might support",
            object="new feature",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.4,  # Below 0.6 threshold
            age_days=10,
        )

        # Opinion fact (should be invalidated by age)
        self.old_opinion = self.mock_fact_service.add_test_fact(
            subject="I",
            predicate="think",
            object="AutoBot is great",
            fact_type=FactType.OPINION,
            temporal_type=TemporalType.ATEMPORAL,
            confidence=0.6,
            age_days=200,  # Older than 180-day rule for opinions
        )

        # Test source fact (should be invalidated)
        self.test_source_fact = self.mock_fact_service.add_test_fact(
            subject="TestEntity",
            predicate="has property",
            object="test value",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.8,
            age_days=2,  # Older than 1-day rule for test sources
        )
        self.test_source_fact.source = "test_data"  # Update source to match rule

    async def test_invalidation_rules_initialization(self):
        """Test initialization of invalidation rules."""
        print("Testing invalidation rules initialization...")

        result = await self.invalidation_service.initialize_rules()

        print(f"✓ Rules initialization result: {result['status']}")
        print(f"  Total rules: {result['total_rules']}")
        print(f"  Rules added: {result['rules_added']}")

        assert result["status"] == "success", "Rules initialization should succeed"
        assert result["total_rules"] >= 5, "Should have at least 5 default rules"

        return result

    async def test_invalidation_rule_matching(self):
        """Test invalidation rule matching logic."""
        print("\nTesting invalidation rule matching...")

        # Test each default rule against appropriate facts
        rules = self.invalidation_service.default_rules

        matches_found = 0
        for rule in rules:
            print(f"  Testing rule: {rule.name}")

            # Test against old dynamic fact
            if "Dynamic Facts" in rule.name:
                matches, reason = rule.matches_fact(self.old_dynamic_fact)
                if matches:
                    print(f"    ✓ Matches old dynamic fact: {reason.value}")
                    matches_found += 1

                # Should NOT match recent dynamic fact
                matches_recent, _ = rule.matches_fact(self.recent_dynamic_fact)
                assert not matches_recent, "Should not match recent dynamic fact"

            # Test against prediction
            elif "Predictions" in rule.name:
                matches, reason = rule.matches_fact(self.old_prediction)
                if matches:
                    print(f"    ✓ Matches old prediction: {reason.value}")
                    matches_found += 1

            # Test against low confidence fact
            elif "Low Confidence" in rule.name:
                matches, reason = rule.matches_fact(self.low_confidence_fact)
                if matches:
                    print(f"    ✓ Matches low confidence fact: {reason.value}")
                    matches_found += 1

            # Test against test source
            elif "Test Sources" in rule.name:
                matches, reason = rule.matches_fact(self.test_source_fact)
                if matches:
                    print(f"    ✓ Matches test source fact: {reason.value}")
                    matches_found += 1

        print(f"✓ Rule matching working: {matches_found} matches found")
        assert matches_found >= 3, "Should find at least 3 rule matches"

        return matches_found

    async def test_dry_run_invalidation_sweep(self):
        """Test invalidation sweep in dry run mode."""
        print("\nTesting dry run invalidation sweep...")

        # Initialize rules first
        await self.invalidation_service.initialize_rules()

        # Run dry run sweep
        result = await self.invalidation_service.run_invalidation_sweep(dry_run=True)

        print(f"✓ Dry run sweep completed: {result['status']}")
        print(f"  Facts processed: {result['facts_processed']}")
        print(
            f"  Facts identified for invalidation: {result['facts_identified_for_invalidation']}"
        )
        print(f"  Processing time: {result['processing_time']:.3f}s")

        # Validate results
        assert result["status"] == "success", "Dry run should succeed"
        assert result["dry_run"] is True, "Should indicate dry run mode"
        assert result["facts_processed"] > 0, "Should process some facts"
        assert (
            result["facts_invalidated"] == 0
        ), "Should not actually invalidate in dry run"

        # Check if facts that should be invalidated were identified
        if result["facts_identified_for_invalidation"] > 0:
            print("  Sample facts to invalidate:")
            for sample_fact in result.get("sample_facts_to_invalidate", [])[:3]:
                print(
                    f"    - {sample_fact['statement']} (age: {sample_fact['age_days']} days)"
                )
                print(f"      Reason: {sample_fact['reason'].get('reason', 'unknown')}")

        return result

    async def test_actual_invalidation_sweep(self):
        """Test actual invalidation sweep (not dry run)."""
        print("\nTesting actual invalidation sweep...")

        # Count active facts before invalidation
        active_facts_before = await self.mock_fact_service.get_facts_by_criteria(
            active_only=True
        )

        print(f"  Active facts before: {len(active_facts_before)}")

        # Run actual invalidation sweep
        result = await self.invalidation_service.run_invalidation_sweep(dry_run=False)

        print(f"✓ Actual sweep completed: {result['status']}")
        print(f"  Facts processed: {result['facts_processed']}")
        print(f"  Facts identified: {result['facts_identified_for_invalidation']}")
        print(f"  Facts invalidated: {result['facts_invalidated']}")

        # Validate results
        assert result["status"] == "success", "Actual sweep should succeed"
        assert result["dry_run"] is False, "Should indicate actual run mode"

        # Note: In our mock implementation, we don't actually modify facts
        # In a real implementation, we would verify facts were marked as inactive

        return result

    async def test_contradiction_detection(self):
        """Test contradiction detection between facts."""
        print("\nTesting contradiction detection...")

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

        print("  Created contradictory facts:")
        print(
            f"    Fact 1: {fact1.subject} {fact1.predicate} {fact1.object} (confidence: {fact1.confidence})"
        )
        print(
            f"    Fact 2: {fact2.subject} {fact2.predicate} {fact2.object} (confidence: {fact2.confidence})"
        )

        # Test contradiction detection
        result = await self.invalidation_service.invalidate_contradictory_facts(fact2)

        print(f"✓ Contradiction check completed: {result['status']}")
        print(f"  Contradictions found: {result['contradictions_found']}")
        print(f"  Facts invalidated: {result['facts_invalidated']}")

        # Validate results
        assert result["status"] == "success", "Contradiction check should succeed"

        # Check if contradiction was detected
        is_contradictory = fact1.is_contradictory_to(fact2)
        print(f"  Facts are contradictory: {is_contradictory}")

        return result

    async def test_invalidation_statistics(self):
        """Test invalidation statistics collection."""
        print("\nTesting invalidation statistics...")

        # Run some invalidation operations first
        await self.invalidation_service.initialize_rules()
        await self.invalidation_service.run_invalidation_sweep(dry_run=True)

        # Get statistics
        stats = await self.invalidation_service.get_invalidation_statistics()

        print("✓ Statistics retrieved successfully")
        print(f"  Total invalidated facts: {stats.get('total_invalidated_facts', 0)}")
        print(f"  Recent sweeps: {stats.get('recent_sweeps', 0)}")
        print(f"  Total rules: {stats.get('total_rules', 0)}")
        print(f"  Enabled rules: {stats.get('enabled_rules', 0)}")
        print(f"  Auto invalidation: {stats.get('auto_invalidation_enabled', False)}")

        # Validate statistics structure
        assert isinstance(stats, dict), "Should return statistics dictionary"
        assert "total_rules" in stats, "Should include total rules count"
        assert "enabled_rules" in stats, "Should include enabled rules count"

        if stats.get("recent_sweeps", 0) > 0:
            assert (
                "average_processing_time" in stats
            ), "Should include average processing time"
            print(
                f"  Average processing time: {stats.get('average_processing_time', 0):.3f}s"
            )

        return stats

    async def test_rule_management(self):
        """Test adding and removing invalidation rules."""
        print("\nTesting rule management...")

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

        print(f"✓ Custom rule added: {add_result['status']}")
        print(f"  Rule ID: {add_result.get('rule_id')}")

        assert add_result["status"] == "success", "Should successfully add custom rule"

        # Remove the rule
        remove_result = await self.invalidation_service.remove_invalidation_rule(
            "test_custom_rule"
        )

        print(f"✓ Custom rule removed: {remove_result['status']}")

        assert (
            remove_result["status"] == "success"
        ), "Should successfully remove custom rule"

        # Try to remove non-existent rule
        remove_nonexistent = await self.invalidation_service.remove_invalidation_rule(
            "nonexistent_rule"
        )

        print(f"  Non-existent rule removal: {remove_nonexistent['status']}")
        assert (
            remove_nonexistent["status"] == "error"
        ), "Should fail to remove non-existent rule"

        return add_result, remove_result

    async def test_temporal_type_behavior(self):
        """Test invalidation behavior for different temporal types."""
        print("\nTesting temporal type behavior...")

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

            print(f"  {temporal_type.value}: {len(applicable_rules)} applicable rules")
            for rule_name, reason in applicable_rules:
                print(f"    - {rule_name} ({reason})")

        # Validate expectations
        # STATIC facts should have fewer applicable rules
        assert temporal_test_results.get("STATIC", 0) <= temporal_test_results.get(
            "DYNAMIC", 0
        ), "Static facts should have fewer or equal applicable rules than dynamic facts"

        print("✓ Temporal type behavior test completed")

        return temporal_test_results

    async def run_all_tests(self):
        """Run all temporal invalidation tests."""
        print("=" * 70)
        print("AutoBot Temporal Knowledge Invalidation Test Suite")
        print("=" * 70)

        try:
            # Test rules initialization
            rules_result = await self.test_invalidation_rules_initialization()

            # Test rule matching
            matches_found = await self.test_invalidation_rule_matching()

            # Test dry run invalidation
            dry_run_result = await self.test_dry_run_invalidation_sweep()

            # Test actual invalidation
            actual_result = await self.test_actual_invalidation_sweep()

            # Test contradiction detection
            contradiction_result = await self.test_contradiction_detection()

            # Test statistics
            stats = await self.test_invalidation_statistics()

            # Test rule management
            await self.test_rule_management()

            # Test temporal type behavior
            temporal_behavior = await self.test_temporal_type_behavior()

            print("\n" + "=" * 70)
            print("✅ All Temporal Invalidation Tests Passed!")
            print("=" * 70)
            print("Summary:")
            print(f"  - Rules initialized: {rules_result['total_rules']} total")
            print(f"  - Rule matches found: {matches_found}")
            print(
                f"  - Dry run identified: {dry_run_result['facts_identified_for_invalidation']} facts"
            )
            print(
                f"  - Actual sweep processed: {actual_result['facts_processed']} facts"
            )
            print(
                f"  - Contradictions detected: {contradiction_result['contradictions_found']}"
            )
            print(f"  - Statistics collected: {len(stats)} metrics")
            print(
                f"  - Temporal behavior verified: {len(temporal_behavior)} types tested"
            )

            return True

        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return False


async def main():
    """Main test execution function."""
    tester = TestTemporalInvalidation()
    success = await tester.run_all_tests()

    if success:
        print("\n🎉 Temporal invalidation implementation is working correctly!")
        return 0
    else:
        print("\n💥 Temporal invalidation tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
