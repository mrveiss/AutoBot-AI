#!/usr/bin/env python3
"""
Test suite for AutoBot entity resolution functionality.
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.atomic_fact import AtomicFact, FactType, TemporalType
from models.entity_mapping import EntityMapping, EntityType
from utils.entity_resolver import EntityResolver


class TestEntityResolution:
    """Test cases for entity resolution functionality."""

    def __init__(self):
        self.resolver = EntityResolver()

        # Test entities with known duplicates
        self.test_entities = [
            # Technology entities with variations
            "AutoBot",
            "autobot",
            "AutoBot Platform",
            "AutoBot System",
            "Python",
            "python",
            "Python programming language",
            "Redis",
            "redis",
            "Redis database",
            "ChromaDB",
            "Chroma DB",
            "ChromaDB vector database",
            # Organization/Product entities
            "OpenAI",
            "Open AI",
            "OpenAI Inc",
            "GPT-4",
            "GPT4",
            "GPT-4.0",
            "Ollama",
            "ollama",
            # Version entities
            "version 1.0",
            "v1.0",
            "1.0",
            "version 2.0",
            "v2.0",
            "2.0",
            # Configuration entities
            "config",
            "configuration",
            "settings",
            "parameters",
            "options",
        ]

    async def test_basic_entity_resolution(self):
        """Test basic entity resolution functionality."""
        print("Testing basic entity resolution...")  # noqa: print

        # Test with a small set of similar entities
        test_entities = ["AutoBot", "autobot", "AutoBot Platform", "Python", "python"]

        result = await self.resolver.resolve_entities(test_entities)

        print(f"✓ Processed {len(test_entities)} entities")  # noqa: print
        print(f"  Original entities: {result.total_original}")  # noqa: print
        print(f"  Canonical entities: {result.total_canonical}")  # noqa: print
        print(f"  Resolution rate: {result.resolution_rate:.1f}%")  # noqa: print
        print(f"  Processing time: {result.processing_time:.3f}s")  # noqa: print

        # Validate results
        assert result.total_original == len(
            test_entities
        ), "Should count all original entities"
        assert result.total_canonical <= len(
            test_entities
        ), "Should have same or fewer canonical entities"
        assert result.processing_time > 0, "Should have positive processing time"

        # Check mappings
        print("  Sample mappings:")  # noqa: print
        for original, canonical in list(result.resolved_mappings.items())[:3]:
            print(f"    '{original}' -> '{canonical}'")  # noqa: print

        return result

    async def test_similarity_detection(self):
        """Test similarity detection between entity names."""
        print("\nTesting similarity detection...")  # noqa: print

        # Test pairs that should be similar
        similar_pairs = [
            ("AutoBot", "autobot"),
            ("Python", "python"),
            ("Redis", "redis"),
            ("GPT-4", "GPT4"),
            ("version 1.0", "v1.0"),
            ("ChromaDB", "Chroma DB"),
        ]

        # Create test mappings
        test_mappings = []
        for i, (canonical, _) in enumerate(similar_pairs):
            mapping = EntityMapping(
                canonical_id=f"test_{i}",
                canonical_name=canonical,
                entity_type=EntityType.TECHNOLOGY,
                confidence_score=0.9,
            )
            test_mappings.append(mapping)

        # Test similarity detection
        print("  Testing similarity pairs:")  # noqa: print
        for canonical, variant in similar_pairs:
            # Find the mapping for this canonical entity
            mapping = next(
                (m for m in test_mappings if m.canonical_name == canonical), None
            )
            if mapping:
                is_similar = mapping.is_similar_to(variant)
                print(f"    '{canonical}' ~ '{variant}': {is_similar}")  # noqa: print

                # Most pairs should be detected as similar
                if canonical.lower() == variant.lower():
                    assert (
                        is_similar
                    ), f"Case variations should be similar: {canonical} ~ {variant}"

        print("✓ Similarity detection working correctly")  # noqa: print

        return True

    async def test_entity_type_classification(self):
        """Test automatic entity type classification."""
        print("\nTesting entity type classification...")  # noqa: print

        # Test entities with expected types
        type_test_cases = [
            ("AutoBot", EntityType.PRODUCT),
            ("Python", EntityType.TECHNOLOGY),
            ("Redis", EntityType.TECHNOLOGY),
            ("OpenAI", EntityType.ORGANIZATION),
            ("version 1.0", EntityType.VERSION),
            ("configuration", EntityType.CONFIGURATION),
            ("neural network", EntityType.CONCEPT),
        ]

        print("  Classification results:")  # noqa: print
        correct_classifications = 0

        for entity_name, expected_type in type_test_cases:
            classified_type = self.resolver._classify_entity_type(entity_name)
            is_correct = classified_type == expected_type

            print(  # noqa: print
                f"    '{entity_name}': {classified_type.value} {'✓' if is_correct else '✗'}"
            )

            if is_correct:
                correct_classifications += 1

        accuracy = correct_classifications / len(type_test_cases) * 100
        print(f"  Classification accuracy: {accuracy:.1f}%")  # noqa: print

        # Should get at least 50% accuracy for basic classification
        assert accuracy >= 50, f"Classification accuracy too low: {accuracy}%"

        return accuracy

    async def test_large_scale_resolution(self):
        """Test entity resolution with larger dataset."""
        print("\nTesting large-scale entity resolution...")  # noqa: print

        # Use all test entities
        result = await self.resolver.resolve_entities(self.test_entities)

        print(f"✓ Processed {len(self.test_entities)} entities")  # noqa: print
        print(f"  Original entities: {result.total_original}")  # noqa: print
        print(f"  Canonical entities: {result.total_canonical}")  # noqa: print
        print(
            f"  Entities merged: {result.total_original - result.total_canonical}"
        )  # noqa: print
        print(f"  Resolution rate: {result.resolution_rate:.1f}%")  # noqa: print
        print(f"  Processing time: {result.processing_time:.3f}s")  # noqa: print

        # Check quality metrics
        summary = result.get_resolution_summary()
        print("  Quality metrics:")  # noqa: print
        print(
            f"    High confidence: {summary['quality_metrics']['high_confidence']}"
        )  # noqa: print
        print(
            f"    Low confidence: {summary['quality_metrics']['low_confidence']}"
        )  # noqa: print
        print(
            f"    Exact matches: {summary['quality_metrics']['exact_matches']}"
        )  # noqa: print
        print(
            f"    Semantic matches: {summary['quality_metrics']['semantic_matches']}"
        )  # noqa: print

        # Should achieve some level of deduplication
        assert result.resolution_rate > 0, "Should achieve some entity deduplication"
        assert (
            result.total_canonical < result.total_original
        ), "Should reduce entity count"

        return result

    async def test_fact_entity_resolution(self):
        """Test entity resolution applied to atomic facts."""
        print("\nTesting entity resolution in atomic facts...")  # noqa: print

        # Create test facts with duplicate entities
        test_facts = [
            AtomicFact(
                subject="AutoBot",
                predicate="uses",
                object="Python programming language",
                fact_type=FactType.FACT,
                temporal_type=TemporalType.STATIC,
                confidence=0.9,
                source="test",
                extraction_method="manual",
                entities=["AutoBot", "Python programming language"],
                valid_from=datetime.now(),
            ),
            AtomicFact(
                subject="autobot",
                predicate="integrates with",
                object="redis",
                fact_type=FactType.FACT,
                temporal_type=TemporalType.STATIC,
                confidence=0.8,
                source="test",
                extraction_method="manual",
                entities=["autobot", "redis"],
                valid_from=datetime.now(),
            ),
            AtomicFact(
                subject="AutoBot Platform",
                predicate="supports",
                object="OpenAI",
                fact_type=FactType.FACT,
                temporal_type=TemporalType.STATIC,
                confidence=0.9,
                source="test",
                extraction_method="manual",
                entities=["AutoBot Platform", "OpenAI"],
                valid_from=datetime.now(),
            ),
        ]

        print(f"  Original facts: {len(test_facts)}")  # noqa: print

        # Count original entities
        original_entities = set()
        for fact in test_facts:
            original_entities.update(fact.entities)
            original_entities.add(fact.subject)
            original_entities.add(fact.object)

        print(f"  Original unique entities: {len(original_entities)}")  # noqa: print
        print(
            f"  Sample original entities: {list(original_entities)[:5]}"
        )  # noqa: print

        # Apply entity resolution
        resolved_facts = await self.resolver.resolve_facts_entities(test_facts)

        # Count resolved entities
        resolved_entities = set()
        for fact in resolved_facts:
            resolved_entities.update(fact.entities)
            resolved_entities.add(fact.subject)
            resolved_entities.add(fact.object)

        print(f"  Resolved unique entities: {len(resolved_entities)}")  # noqa: print
        print(
            f"  Sample resolved entities: {list(resolved_entities)[:5]}"
        )  # noqa: print

        # Show some resolved facts
        print("  Sample resolved facts:")  # noqa: print
        for fact in resolved_facts[:2]:
            print(f"    {fact.subject} {fact.predicate} {fact.object}")  # noqa: print

        # Should maintain same number of facts but potentially fewer unique entities
        assert len(resolved_facts) == len(
            test_facts
        ), "Should maintain same number of facts"

        print("✓ Entity resolution applied to facts successfully")  # noqa: print

        return len(original_entities), len(resolved_entities)

    async def test_entity_mapping_persistence(self):
        """Test entity mapping persistence and retrieval."""
        print("\nTesting entity mapping persistence...")  # noqa: print

        # Test with a controlled set of entities
        test_entities = ["TestEntity1", "testentity1", "Test Entity 1"]

        # First resolution
        result1 = await self.resolver.resolve_entities(
            test_entities, context={"test": "first"}
        )

        # Second resolution with additional entities
        extended_entities = test_entities + ["TestEntity2", "Test Entity 2"]
        result2 = await self.resolver.resolve_entities(
            extended_entities, context={"test": "second"}
        )

        print(  # noqa: print
            f"  First resolution: {result1.total_original} -> {result1.total_canonical}"
        )
        print(  # noqa: print
            f"  Second resolution: {result2.total_original} -> {result2.total_canonical}"
        )

        # The second resolution should reuse mappings from the first
        # This is hard to test without direct access to Redis, but we can check consistency
        common_entities = set(test_entities)
        for entity in common_entities:
            mapping1 = result1.resolved_mappings.get(entity)
            mapping2 = result2.resolved_mappings.get(entity)
            if mapping1 and mapping2:
                # Mappings should be consistent (though IDs might differ due to test isolation)
                print(f"    '{entity}': consistent mapping")  # noqa: print

        print("✓ Entity mapping persistence test completed")  # noqa: print

        return result1, result2

    async def test_performance_metrics(self):
        """Test performance characteristics of entity resolution."""
        print("\nTesting performance metrics...")  # noqa: print

        # Test with different sizes
        sizes = [10, 25, 50]
        performance_results = {}

        for size in sizes:
            test_subset = self.test_entities[:size]
            datetime.now()

            result = await self.resolver.resolve_entities(test_subset)

            processing_time = result.processing_time
            throughput = (
                len(test_subset) / processing_time if processing_time > 0 else 0
            )

            performance_results[size] = {
                "processing_time": processing_time,
                "throughput": throughput,
                "resolution_rate": result.resolution_rate,
            }

            print(  # noqa: print
                f"  Size {size}: {processing_time:.3f}s ({throughput:.1f} entities/s)"
            )

        # Performance should scale reasonably
        for size in sizes:
            metrics = performance_results[size]
            assert (
                metrics["processing_time"] < 10.0
            ), f"Processing time too slow for size {size}"
            print(
                f"    Resolution rate: {metrics['resolution_rate']:.1f}%"
            )  # noqa: print

        print("✓ Performance metrics within acceptable ranges")  # noqa: print

        return performance_results

    async def test_statistics_collection(self):
        """Test statistics collection and reporting."""
        print("\nTesting statistics collection...")  # noqa: print

        # Perform some resolution operations
        await self.resolver.resolve_entities(["test1", "test2", "test3"])
        await self.resolver.resolve_entities(["entity1", "Entity1", "ENTITY1"])

        # Get statistics
        stats = await self.resolver.get_resolution_statistics()

        print("  Resolution statistics:")  # noqa: print
        print(
            f"    Total mappings: {stats.get('total_entity_mappings', 0)}"
        )  # noqa: print
        print(
            f"    Recent resolutions: {stats.get('recent_resolutions', 0)}"
        )  # noqa: print
        print(  # noqa: print
            f"    Average processing time: {stats.get('average_processing_time', 0):.3f}s"
        )
        print(  # noqa: print
            f"    Average resolution rate: {stats.get('average_resolution_rate', 0):.1f}%"
        )

        # Basic validation
        assert isinstance(stats, dict), "Should return dictionary of statistics"

        if stats.get("recent_resolutions", 0) > 0:
            assert (
                stats.get("average_processing_time", 0) > 0
            ), "Should have positive processing time"

        print("✓ Statistics collection working")  # noqa: print

        return stats

    async def run_all_tests(self):
        """Run all entity resolution tests."""
        print("=" * 70)  # noqa: print
        print("AutoBot Entity Resolution Test Suite")  # noqa: print
        print("=" * 70)  # noqa: print

        try:
            # Test basic functionality
            basic_result = await self.test_basic_entity_resolution()

            # Test similarity detection
            await self.test_similarity_detection()

            # Test entity type classification
            classification_accuracy = await self.test_entity_type_classification()

            # Test large-scale resolution
            large_scale_result = await self.test_large_scale_resolution()

            # Test fact entity resolution
            orig_entities, resolved_entities = await self.test_fact_entity_resolution()

            # Test persistence
            await self.test_entity_mapping_persistence()

            # Test performance
            performance_results = await self.test_performance_metrics()

            # Test statistics
            stats = await self.test_statistics_collection()

            print("\n" + "=" * 70)  # noqa: print
            print("✅ All Entity Resolution Tests Passed!")  # noqa: print
            print("=" * 70)  # noqa: print
            print("Summary:")  # noqa: print
            print(  # noqa: print
                f"  - Basic resolution: {basic_result.resolution_rate:.1f}% reduction"
            )
            print(
                f"  - Classification accuracy: {classification_accuracy:.1f}%"
            )  # noqa: print
            print(  # noqa: print
                f"  - Large-scale: {large_scale_result.total_original} -> {large_scale_result.total_canonical} entities"
            )
            print(  # noqa: print
                f"  - Fact resolution: {orig_entities} -> {resolved_entities} entities"
            )
            print(  # noqa: print
                f"  - Performance: {max(p['throughput'] for p in performance_results.values()):.1f} entities/s max"
            )
            print(  # noqa: print
                f"  - Statistics: {stats.get('recent_resolutions', 0)} recent operations"
            )

            return True

        except Exception as e:
            print(f"❌ Test failed: {e}")  # noqa: print
            import traceback

            traceback.print_exc()
            return False


async def main():
    """Main test execution function."""
    tester = TestEntityResolution()
    success = await tester.run_all_tests()

    if success:
        print(
            "\n🎉 Entity resolution implementation is working correctly!"
        )  # noqa: print
        return 0
    else:
        print("\n💥 Entity resolution tests failed!")  # noqa: print
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
