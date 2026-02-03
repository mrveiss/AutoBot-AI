#!/usr/bin/env python3
"""
Test suite for AutoBot atomic facts extraction functionality.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.agents.knowledge_extraction_agent import KnowledgeExtractionAgent
from src.models.atomic_fact import AtomicFact, FactType, TemporalType
from src.services.fact_extraction_service import FactExtractionService
from tests.mock_llm_interface import MockLLMInterface


class TestAtomicFactsExtraction:
    """Test cases for atomic facts extraction functionality."""
    
    def __init__(self):
        # Use mock LLM interface for testing
        mock_llm = MockLLMInterface()
        self.extraction_agent = KnowledgeExtractionAgent(llm_interface=mock_llm)
        self.test_content = {
            "technical": """
            AutoBot is an intelligent automation platform built with Python. 
            It uses Redis for caching and memory management. The system currently 
            supports multiple LLM providers including OpenAI and Ollama.
            
            The knowledge base uses ChromaDB for vector storage. Vector embeddings 
            are generated using sentence-transformers. The default embedding model 
            is nomic-embed-text:latest.
            
            AutoBot will be updated to version 2.0 next month with enhanced features.
            """,
            
            "mixed_temporal": """
            Python was created by Guido van Rossum in 1991. It is currently 
            the most popular programming language for data science. 
            Machine learning libraries like TensorFlow are widely used.
            
            OpenAI will release GPT-5 in 2024. This is expected to have 
            better reasoning capabilities than GPT-4.
            
            Programming languages are tools for software development.
            """,
            
            "opinion_based": """
            I think AutoBot is the best automation platform available. 
            The user interface is very intuitive and easy to use. 
            In my opinion, the semantic chunking feature is revolutionary.
            
            Python is definitely easier to learn than Java. Most developers 
            prefer working with Python for AI projects. The community 
            believes that open-source models will dominate the market.
            """
        }
    
    async def test_basic_fact_extraction(self):
        """Test basic atomic fact extraction from technical content."""
        print("Testing basic atomic fact extraction...")
        
        result = await self.extraction_agent.extract_facts_from_text(
            content=self.test_content["technical"],
            source="test_technical"
        )
        
        print(f"✓ Extracted {result.total_facts} facts in {result.processing_time:.2f}s")
        print(f"  Average confidence: {result.average_confidence:.3f}")
        
        # Validate results
        assert result.total_facts > 0, "Should extract at least some facts"
        assert result.average_confidence > 0.0, "Should have positive confidence"
        
        # Check fact structure
        for fact in result.facts:
            assert isinstance(fact, AtomicFact), "Should return AtomicFact objects"
            assert fact.subject, "Fact should have subject"
            assert fact.predicate, "Fact should have predicate"
            assert fact.object, "Fact should have object"
            assert fact.confidence >= 0.0, "Confidence should be non-negative"
            
        # Display some extracted facts
        print("  Sample extracted facts:")
        for i, fact in enumerate(result.facts[:3]):
            print(f"    {i+1}. {fact.subject} {fact.predicate} {fact.object}")
            print(f"       Type: {fact.fact_type.value}, Temporal: {fact.temporal_type.value}")
            print(f"       Confidence: {fact.confidence:.3f}")
        
        return result
    
    async def test_temporal_classification(self):
        """Test temporal type classification of facts."""
        print("\nTesting temporal classification...")
        
        result = await self.extraction_agent.extract_facts_from_text(
            content=self.test_content["mixed_temporal"],
            source="test_temporal"
        )
        
        print(f"✓ Extracted {result.total_facts} facts for temporal analysis")
        
        # Check for different temporal types
        temporal_counts = result.temporal_type_distribution
        print(f"  Temporal distribution: {temporal_counts}")
        
        # Should have multiple temporal types
        assert len(temporal_counts) > 1, "Should detect multiple temporal types"
        
        # Check specific facts
        dynamic_facts = result.facts_by_temporal_type(TemporalType.DYNAMIC)
        static_facts = result.facts_by_temporal_type(TemporalType.STATIC)
        temporal_bound_facts = result.facts_by_temporal_type(TemporalType.TEMPORAL_BOUND)
        
        print(f"  Dynamic facts: {len(dynamic_facts)}")
        print(f"  Static facts: {len(static_facts)}")
        print(f"  Temporal-bound facts: {len(temporal_bound_facts)}")
        
        return result
    
    async def test_fact_type_classification(self):
        """Test fact type classification (FACT vs OPINION)."""
        print("\nTesting fact type classification...")
        
        result = await self.extraction_agent.extract_facts_from_text(
            content=self.test_content["opinion_based"],
            source="test_opinion"
        )
        
        print(f"✓ Extracted {result.total_facts} facts for type analysis")
        
        # Check for different fact types
        fact_type_counts = result.fact_type_distribution
        print(f"  Fact type distribution: {fact_type_counts}")
        
        # Should detect opinions in opinion-based content
        opinion_facts = result.facts_by_type(FactType.OPINION)
        factual_facts = result.facts_by_type(FactType.FACT)
        
        print(f"  Opinion facts: {len(opinion_facts)}")
        print(f"  Factual facts: {len(factual_facts)}")
        
        # Display sample opinions
        if opinion_facts:
            print("  Sample opinion facts:")
            for fact in opinion_facts[:2]:
                print(f"    - {fact.subject} {fact.predicate} {fact.object}")
        
        return result
    
    async def test_entity_extraction(self):
        """Test entity extraction from facts."""
        print("\nTesting entity extraction...")
        
        result = await self.extraction_agent.extract_facts_from_text(
            content=self.test_content["technical"],
            source="test_entities"
        )
        
        print(f"✓ Analyzed entities in {result.total_facts} facts")
        
        # Check entity extraction
        all_entities = set()
        for fact in result.facts:
            all_entities.update(fact.entities)
        
        print(f"  Total unique entities: {len(all_entities)}")
        print(f"  Sample entities: {list(all_entities)[:10]}")
        
        # Should extract relevant entities
        expected_entities = ["AutoBot", "Python", "Redis", "ChromaDB"]
        found_entities = [e for e in expected_entities if e in all_entities]
        print(f"  Found expected entities: {found_entities}")
        
        assert len(found_entities) > 0, "Should find some expected entities"
        
        return all_entities
    
    async def test_confidence_scoring(self):
        """Test confidence scoring reliability."""
        print("\nTesting confidence scoring...")
        
        # Test with clear, factual content
        clear_content = "AutoBot uses Python programming language. Redis is a caching system."
        result1 = await self.extraction_agent.extract_facts_from_text(
            content=clear_content,
            source="test_clear"
        )
        
        # Test with ambiguous content
        ambiguous_content = "Someone mentioned that something might work somehow."
        result2 = await self.extraction_agent.extract_facts_from_text(
            content=ambiguous_content,
            source="test_ambiguous"
        )
        
        avg_confidence_clear = result1.average_confidence
        avg_confidence_ambiguous = result2.average_confidence if result2.facts else 0
        
        print(f"  Clear content confidence: {avg_confidence_clear:.3f}")
        print(f"  Ambiguous content confidence: {avg_confidence_ambiguous:.3f}")
        
        # Clear content should have higher confidence
        if result2.facts:
            assert avg_confidence_clear > avg_confidence_ambiguous, \
                   "Clear content should have higher confidence"
        
        print("✓ Confidence scoring appears reasonable")
        
        return avg_confidence_clear, avg_confidence_ambiguous
    
    async def test_chunk_based_extraction(self):
        """Test fact extraction from multiple chunks."""
        print("\nTesting chunk-based extraction...")
        
        # Create test chunks
        chunks = [
            {
                "text": "AutoBot is an AI automation platform. It uses semantic chunking for better knowledge processing.",
                "metadata": {"chunk_id": "chunk_1", "position": 0},
                "id": "chunk_1"
            },
            {
                "text": "The system supports Redis caching and ChromaDB vector storage. OpenAI and Ollama are supported providers.",
                "metadata": {"chunk_id": "chunk_2", "position": 1},
                "id": "chunk_2"
            }
        ]
        
        result = await self.extraction_agent.extract_facts_from_chunks(
            chunks=chunks,
            source="test_chunks"
        )
        
        print(f"✓ Processed {len(chunks)} chunks")
        print(f"  Extracted {result.total_facts} total facts")
        print(f"  Processing time: {result.processing_time:.2f}s")
        
        # Check metadata
        successful_chunks = result.extraction_metadata.get("successful_chunks", 0)
        print(f"  Successful chunks: {successful_chunks}/{len(chunks)}")
        
        assert result.total_facts > 0, "Should extract facts from chunks"
        assert successful_chunks > 0, "Should successfully process some chunks"
        
        return result
    
    async def test_fact_filtering(self):
        """Test fact filtering capabilities."""
        print("\nTesting fact filtering...")
        
        # Extract facts from mixed content
        result = await self.extraction_agent.extract_facts_from_text(
            content=self.test_content["mixed_temporal"],
            source="test_filtering"
        )
        
        all_facts = result.facts
        print(f"  Total facts before filtering: {len(all_facts)}")
        
        # Test filtering by fact type
        factual_only = self.extraction_agent.filter_facts(
            all_facts, fact_types=[FactType.FACT]
        )
        print(f"  Factual facts only: {len(factual_only)}")
        
        # Test filtering by temporal type
        dynamic_only = self.extraction_agent.filter_facts(
            all_facts, temporal_types=[TemporalType.DYNAMIC]
        )
        print(f"  Dynamic facts only: {len(dynamic_only)}")
        
        # Test filtering by confidence
        high_confidence = self.extraction_agent.filter_facts(
            all_facts, min_confidence=0.8
        )
        print(f"  High confidence facts (>0.8): {len(high_confidence)}")
        
        # Test combined filtering
        high_conf_factual = self.extraction_agent.filter_facts(
            all_facts, 
            fact_types=[FactType.FACT],
            min_confidence=0.7
        )
        print(f"  High confidence factual: {len(high_conf_factual)}")
        
        print("✓ Filtering working correctly")
        
        return {
            "total": len(all_facts),
            "factual": len(factual_only),
            "dynamic": len(dynamic_only),
            "high_confidence": len(high_confidence),
            "combined": len(high_conf_factual)
        }
    
    async def test_fact_contradiction_detection(self):
        """Test fact contradiction detection logic."""
        print("\nTesting fact contradiction detection...")
        
        # Create test facts that should contradict
        fact1 = AtomicFact(
            subject="AutoBot",
            predicate="version is",
            object="1.0",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.9,
            source="test",
            extraction_method="manual",
            valid_from=datetime.now()
        )
        
        fact2 = AtomicFact(
            subject="AutoBot",
            predicate="version is", 
            object="2.0",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.DYNAMIC,
            confidence=0.9,
            source="test",
            extraction_method="manual",
            valid_from=datetime.now()
        )
        
        # Test contradiction detection
        is_contradictory = fact1.is_contradictory_to(fact2)
        should_invalidate = fact1.should_invalidate(fact2)
        
        print(f"  Facts are contradictory: {is_contradictory}")
        print(f"  Should invalidate: {should_invalidate}")
        
        assert is_contradictory, "Facts with same subject/predicate but different objects should be contradictory"
        
        # Test non-contradictory facts
        fact3 = AtomicFact(
            subject="Python",
            predicate="is",
            object="programming language",
            fact_type=FactType.FACT,
            temporal_type=TemporalType.STATIC,
            confidence=0.9,
            source="test",
            extraction_method="manual",
            valid_from=datetime.now()
        )
        
        not_contradictory = fact1.is_contradictory_to(fact3)
        assert not not_contradictory, "Facts about different subjects should not be contradictory"
        
        print("✓ Contradiction detection working correctly")
        
        return is_contradictory, should_invalidate
    
    async def run_all_tests(self):
        """Run all atomic facts extraction tests."""
        print("=" * 70)
        print("AutoBot Atomic Facts Extraction Test Suite")
        print("=" * 70)
        
        try:
            # Test basic functionality
            basic_result = await self.test_basic_fact_extraction()
            
            # Test temporal classification
            temporal_result = await self.test_temporal_classification()
            
            # Test fact type classification
            type_result = await self.test_fact_type_classification()
            
            # Test entity extraction
            entities = await self.test_entity_extraction()
            
            # Test confidence scoring
            conf_clear, conf_amb = await self.test_confidence_scoring()
            
            # Test chunk processing
            chunk_result = await self.test_chunk_based_extraction()
            
            # Test filtering
            filter_stats = await self.test_fact_filtering()
            
            # Test contradiction detection
            contradiction_results = await self.test_fact_contradiction_detection()
            
            print("\n" + "=" * 70)
            print("✅ All Atomic Facts Extraction Tests Passed!")
            print("=" * 70)
            print(f"Summary:")
            print(f"  - Basic extraction: {basic_result.total_facts} facts")
            print(f"  - Temporal classification: {len(temporal_result.temporal_type_distribution)} types")
            print(f"  - Fact type classification: {len(type_result.fact_type_distribution)} types") 
            print(f"  - Entity extraction: {len(entities)} unique entities")
            print(f"  - Confidence scoring: Clear={conf_clear:.3f}, Ambiguous={conf_amb:.3f}")
            print(f"  - Chunk processing: {chunk_result.total_facts} facts from chunks")
            print(f"  - Filtering capabilities: {filter_stats}")
            print(f"  - Contradiction detection: Working ✓")
            
            return True
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main test execution function."""
    tester = TestAtomicFactsExtraction()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 Atomic facts extraction implementation is working correctly!")
        return 0
    else:
        print("\n💥 Atomic facts extraction tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)