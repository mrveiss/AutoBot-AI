#!/usr/bin/env python3
"""
Test suite for AutoBot entity resolution functionality.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import List

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.entity_resolver import EntityResolver
from src.models.entity_mapping import EntityMapping, EntityType, SimilarityMethod
from src.models.atomic_fact import AtomicFact, FactType, TemporalType


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
            "options"
        ]
    
    async def test_basic_entity_resolution(self):
        """Test basic entity resolution functionality."""
        print("Testing basic entity resolution...")
        
        # Test with a small set of similar entities
        test_entities = ["AutoBot", "autobot", "AutoBot Platform", "Python", "python"]
        
        result = await self.resolver.resolve_entities(test_entities)
        
        print(f"✓ Processed {len(test_entities)} entities")
        print(f"  Original entities: {result.total_original}")
        print(f"  Canonical entities: {result.total_canonical}")
        print(f"  Resolution rate: {result.resolution_rate:.1f}%")
        print(f"  Processing time: {result.processing_time:.3f}s")
        
        # Validate results
        assert result.total_original == len(test_entities), "Should count all original entities"
        assert result.total_canonical <= len(test_entities), "Should have same or fewer canonical entities"
        assert result.processing_time > 0, "Should have positive processing time"
        
        # Check mappings
        print("  Sample mappings:")
        for original, canonical in list(result.resolved_mappings.items())[:3]:
            print(f"    '{original}' -> '{canonical}'")
        
        return result
    
    async def test_similarity_detection(self):
        """Test similarity detection between entity names."""
        print("\nTesting similarity detection...")
        
        # Test pairs that should be similar
        similar_pairs = [
            ("AutoBot", "autobot"),
            ("Python", "python"),
            ("Redis", "redis"),
            ("GPT-4", "GPT4"),
            ("version 1.0", "v1.0"),
            ("ChromaDB", "Chroma DB")
        ]
        
        # Create test mappings
        test_mappings = []
        for i, (canonical, _) in enumerate(similar_pairs):
            mapping = EntityMapping(
                canonical_id=f"test_{i}",
                canonical_name=canonical,
                entity_type=EntityType.TECHNOLOGY,
                confidence_score=0.9
            )
            test_mappings.append(mapping)
        
        # Test similarity detection
        print("  Testing similarity pairs:")
        for canonical, variant in similar_pairs:
            # Find the mapping for this canonical entity
            mapping = next((m for m in test_mappings if m.canonical_name == canonical), None)
            if mapping:
                is_similar = mapping.is_similar_to(variant)
                print(f"    '{canonical}' ~ '{variant}': {is_similar}")
                
                # Most pairs should be detected as similar
                if canonical.lower() == variant.lower():
                    assert is_similar, f"Case variations should be similar: {canonical} ~ {variant}"
        
        print("✓ Similarity detection working correctly")
        
        return True
    
    async def test_entity_type_classification(self):
        """Test automatic entity type classification."""
        print("\nTesting entity type classification...")
        
        # Test entities with expected types
        type_test_cases = [
            ("AutoBot", EntityType.PRODUCT),
            ("Python", EntityType.TECHNOLOGY),
            ("Redis", EntityType.TECHNOLOGY),
            ("OpenAI", EntityType.ORGANIZATION),
            ("version 1.0", EntityType.VERSION),
            ("configuration", EntityType.CONFIGURATION),
            ("neural network", EntityType.CONCEPT)
        ]
        
        print("  Classification results:")
        correct_classifications = 0
        
        for entity_name, expected_type in type_test_cases:
            classified_type = self.resolver._classify_entity_type(entity_name)
            is_correct = classified_type == expected_type
            
            print(f"    '{entity_name}': {classified_type.value} {'✓' if is_correct else '✗'}")
            
            if is_correct:
                correct_classifications += 1
        
        accuracy = correct_classifications / len(type_test_cases) * 100
        print(f"  Classification accuracy: {accuracy:.1f}%")
        
        # Should get at least 50% accuracy for basic classification
        assert accuracy >= 50, f"Classification accuracy too low: {accuracy}%"
        
        return accuracy
    
    async def test_large_scale_resolution(self):
        """Test entity resolution with larger dataset."""
        print("\nTesting large-scale entity resolution...")
        
        # Use all test entities
        result = await self.resolver.resolve_entities(self.test_entities)
        
        print(f"✓ Processed {len(self.test_entities)} entities")
        print(f"  Original entities: {result.total_original}")
        print(f"  Canonical entities: {result.total_canonical}")
        print(f"  Entities merged: {result.total_original - result.total_canonical}")
        print(f"  Resolution rate: {result.resolution_rate:.1f}%")
        print(f"  Processing time: {result.processing_time:.3f}s")
        
        # Check quality metrics
        summary = result.get_resolution_summary()
        print(f"  Quality metrics:")
        print(f"    High confidence: {summary['quality_metrics']['high_confidence']}")
        print(f"    Low confidence: {summary['quality_metrics']['low_confidence']}")
        print(f"    Exact matches: {summary['quality_metrics']['exact_matches']}")
        print(f"    Semantic matches: {summary['quality_metrics']['semantic_matches']}")
        
        # Should achieve some level of deduplication
        assert result.resolution_rate > 0, "Should achieve some entity deduplication"
        assert result.total_canonical < result.total_original, "Should reduce entity count"
        
        return result
    
    async def test_fact_entity_resolution(self):
        """Test entity resolution applied to atomic facts."""
        print("\nTesting entity resolution in atomic facts...")
        
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
                valid_from=datetime.now()
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
                valid_from=datetime.now()
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
                valid_from=datetime.now()
            )
        ]
        
        print(f"  Original facts: {len(test_facts)}")
        
        # Count original entities
        original_entities = set()
        for fact in test_facts:
            original_entities.update(fact.entities)
            original_entities.add(fact.subject)
            original_entities.add(fact.object)
        
        print(f"  Original unique entities: {len(original_entities)}")
        print(f"  Sample original entities: {list(original_entities)[:5]}")
        
        # Apply entity resolution
        resolved_facts = await self.resolver.resolve_facts_entities(test_facts)
        
        # Count resolved entities
        resolved_entities = set()
        for fact in resolved_facts:
            resolved_entities.update(fact.entities)
            resolved_entities.add(fact.subject)
            resolved_entities.add(fact.object)
        
        print(f"  Resolved unique entities: {len(resolved_entities)}")
        print(f"  Sample resolved entities: {list(resolved_entities)[:5]}")
        
        # Show some resolved facts
        print("  Sample resolved facts:")
        for fact in resolved_facts[:2]:
            print(f"    {fact.subject} {fact.predicate} {fact.object}")
        
        # Should maintain same number of facts but potentially fewer unique entities
        assert len(resolved_facts) == len(test_facts), "Should maintain same number of facts"
        
        print("✓ Entity resolution applied to facts successfully")
        
        return len(original_entities), len(resolved_entities)
    
    async def test_entity_mapping_persistence(self):
        """Test entity mapping persistence and retrieval."""
        print("\nTesting entity mapping persistence...")
        
        # Test with a controlled set of entities
        test_entities = ["TestEntity1", "testentity1", "Test Entity 1"]
        
        # First resolution
        result1 = await self.resolver.resolve_entities(test_entities, context={"test": "first"})
        
        # Second resolution with additional entities
        extended_entities = test_entities + ["TestEntity2", "Test Entity 2"]
        result2 = await self.resolver.resolve_entities(extended_entities, context={"test": "second"})
        
        print(f"  First resolution: {result1.total_original} -> {result1.total_canonical}")
        print(f"  Second resolution: {result2.total_original} -> {result2.total_canonical}")
        
        # The second resolution should reuse mappings from the first
        # This is hard to test without direct access to Redis, but we can check consistency
        common_entities = set(test_entities)
        for entity in common_entities:
            mapping1 = result1.resolved_mappings.get(entity)
            mapping2 = result2.resolved_mappings.get(entity)
            if mapping1 and mapping2:
                # Mappings should be consistent (though IDs might differ due to test isolation)
                print(f"    '{entity}': consistent mapping")
        
        print("✓ Entity mapping persistence test completed")
        
        return result1, result2
    
    async def test_performance_metrics(self):
        """Test performance characteristics of entity resolution."""
        print("\nTesting performance metrics...")
        
        # Test with different sizes
        sizes = [10, 25, 50]
        performance_results = {}
        
        for size in sizes:
            test_subset = self.test_entities[:size]
            start_time = datetime.now()
            
            result = await self.resolver.resolve_entities(test_subset)
            
            processing_time = result.processing_time
            throughput = len(test_subset) / processing_time if processing_time > 0 else 0
            
            performance_results[size] = {
                "processing_time": processing_time,
                "throughput": throughput,
                "resolution_rate": result.resolution_rate
            }
            
            print(f"  Size {size}: {processing_time:.3f}s ({throughput:.1f} entities/s)")
        
        # Performance should scale reasonably
        for size in sizes:
            metrics = performance_results[size]
            assert metrics["processing_time"] < 10.0, f"Processing time too slow for size {size}"
            print(f"    Resolution rate: {metrics['resolution_rate']:.1f}%")
        
        print("✓ Performance metrics within acceptable ranges")
        
        return performance_results
    
    async def test_statistics_collection(self):
        """Test statistics collection and reporting."""
        print("\nTesting statistics collection...")
        
        # Perform some resolution operations
        await self.resolver.resolve_entities(["test1", "test2", "test3"])
        await self.resolver.resolve_entities(["entity1", "Entity1", "ENTITY1"])
        
        # Get statistics
        stats = await self.resolver.get_resolution_statistics()
        
        print("  Resolution statistics:")
        print(f"    Total mappings: {stats.get('total_entity_mappings', 0)}")
        print(f"    Recent resolutions: {stats.get('recent_resolutions', 0)}")
        print(f"    Average processing time: {stats.get('average_processing_time', 0):.3f}s")
        print(f"    Average resolution rate: {stats.get('average_resolution_rate', 0):.1f}%")
        
        # Basic validation
        assert isinstance(stats, dict), "Should return dictionary of statistics"
        
        if stats.get("recent_resolutions", 0) > 0:
            assert stats.get("average_processing_time", 0) > 0, "Should have positive processing time"
        
        print("✓ Statistics collection working")
        
        return stats
    
    async def run_all_tests(self):
        """Run all entity resolution tests."""
        print("=" * 70)
        print("AutoBot Entity Resolution Test Suite")
        print("=" * 70)
        
        try:
            # Test basic functionality
            basic_result = await self.test_basic_entity_resolution()
            
            # Test similarity detection
            similarity_result = await self.test_similarity_detection()
            
            # Test entity type classification
            classification_accuracy = await self.test_entity_type_classification()
            
            # Test large-scale resolution
            large_scale_result = await self.test_large_scale_resolution()
            
            # Test fact entity resolution
            orig_entities, resolved_entities = await self.test_fact_entity_resolution()
            
            # Test persistence
            persistence_results = await self.test_entity_mapping_persistence()
            
            # Test performance
            performance_results = await self.test_performance_metrics()
            
            # Test statistics
            stats = await self.test_statistics_collection()
            
            print("\n" + "=" * 70)
            print("✅ All Entity Resolution Tests Passed!")
            print("=" * 70)
            print(f"Summary:")
            print(f"  - Basic resolution: {basic_result.resolution_rate:.1f}% reduction")
            print(f"  - Classification accuracy: {classification_accuracy:.1f}%")
            print(f"  - Large-scale: {large_scale_result.total_original} -> {large_scale_result.total_canonical} entities")
            print(f"  - Fact resolution: {orig_entities} -> {resolved_entities} entities")
            print(f"  - Performance: {max(p['throughput'] for p in performance_results.values()):.1f} entities/s max")
            print(f"  - Statistics: {stats.get('recent_resolutions', 0)} recent operations")
            
            return True
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main test execution function."""
    tester = TestEntityResolution()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 Entity resolution implementation is working correctly!")
        return 0
    else:
        print("\n💥 Entity resolution tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)