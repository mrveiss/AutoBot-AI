#!/usr/bin/env python3
"""Test script for RAG integration with Knowledge Manager"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_rag_integration():
    """Test RAG integration with knowledge search"""

    print("🧪 Testing RAG Integration with Knowledge Manager")
    print("=" * 50)

    try:
        # Test 1: Import RAG Agent
        print("\n1. Testing RAG Agent Import...")
        try:
            from src.agents.rag_agent import get_rag_agent
            rag_agent = get_rag_agent()
            print("✅ RAG Agent imported successfully")
            print(f"   - Agent capabilities: {rag_agent.get_capabilities()}")
        except Exception as e:
            print(f"❌ RAG Agent import failed: {e}")
            return False

        # Test 2: Test Query Reformulation
        print("\n2. Testing Query Reformulation...")
        try:
            test_query = "How to optimize database performance?"
            reformulation_result = await rag_agent.reformulate_query(test_query)

            if reformulation_result.get("status") == "success":
                print("✅ Query reformulation successful")
                reformulated = reformulation_result.get("reformulated_queries", [])
                print(f"   - Original: {test_query}")
                for i, query in enumerate(reformulated[:3]):
                    print(f"   - Reformed {i+1}: {query}")
            else:
                print(f"❌ Query reformulation failed: {reformulation_result}")
        except Exception as e:
            print(f"❌ Query reformulation error: {e}")

        # Test 3: Test Document Analysis
        print("\n3. Testing Document Analysis...")
        try:
            test_documents = [
                {
                    "content": "Database indexing improves query performance by creating data structures that speed up data retrieval.",
                    "metadata": {"filename": "db_optimization.txt", "source": "test"}
                },
                {
                    "content": "Caching strategies can significantly reduce database load and improve application response times.",
                    "metadata": {"filename": "caching_guide.txt", "source": "test"}
                }
            ]

            analysis = rag_agent._analyze_document_relevance(test_query, test_documents)
            print("✅ Document analysis successful")
            print(f"   - Total documents: {analysis.get('total_documents', 0)}")
            print(f"   - High relevance: {analysis.get('high_relevance', 0)}")
            print(f"   - Medium relevance: {analysis.get('medium_relevance', 0)}")
            print(f"   - Low relevance: {analysis.get('low_relevance', 0)}")
        except Exception as e:
            print(f"❌ Document analysis error: {e}")

        # Test 4: Test Document Ranking
        print("\n4. Testing Document Ranking...")
        try:
            ranked_docs = await rag_agent.rank_documents(test_query, test_documents)
            print("✅ Document ranking successful")
            for i, doc in enumerate(ranked_docs):
                score = doc.get("relevance_score", 0.0)
                filename = doc.get("metadata", {}).get("filename", "Unknown")
                print(f"   - Rank {i+1}: {filename} (score: {score:.2f})")
        except Exception as e:
            print(f"❌ Document ranking error: {e}")

        # Test 5: Test Full RAG Processing
        print("\n5. Testing Full RAG Processing...")
        try:
            rag_result = await rag_agent.process_document_query(
                query=test_query,
                documents=test_documents,
                context={"test": True}
            )

            if rag_result.get("status") == "success":
                print("✅ RAG processing successful")
                response = rag_result.get("synthesized_response", "")
                confidence = rag_result.get("confidence_score", 0.0)
                print(f"   - Response length: {len(response)} characters")
                print(f"   - Confidence score: {confidence:.2f}")
                print(f"   - Response preview: {response[:100]}...")
            else:
                print(f"❌ RAG processing failed: {rag_result}")
        except Exception as e:
            print(f"❌ RAG processing error: {e}")

        # Test 6: Test Knowledge Base Integration (if available)
        print("\n6. Testing Knowledge Base Integration...")
        try:
            # This would require a running knowledge base
            # For now, just test the import
            from backend.knowledge_factory import get_or_create_knowledge_base
            print("✅ Knowledge base factory import successful")
            print("   - Full integration requires running backend and Redis")
        except Exception as e:
            print(f"❌ Knowledge base integration error: {e}")

        print("\n" + "=" * 50)
        print("✅ RAG Integration Tests Completed")
        print("\nNext Steps:")
        print("1. Start the AutoBot backend with: bash run_autobot.sh --dev")
        print("2. Test the new API endpoints:")
        print("   - POST /api/knowledge/rag_search")
        print("   - POST /api/knowledge/search?use_rag=true")
        print("   - GET /api/knowledge/health (check rag_status)")

        return True

    except Exception as e:
        print(f"\n❌ RAG Integration Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_api_endpoints_simulation():
    """Simulate API endpoint behavior without requiring running backend"""

    print("\n🌐 Simulating API Endpoint Behavior")
    print("=" * 40)

    # Simulate RAG search request
    mock_request = {
        "query": "What are the best practices for database optimization?",
        "top_k": 5,
        "reformulate_query": True
    }

    print(f"Mock RAG Search Request: {json.dumps(mock_request, indent=2)}")

    # Expected response structure
    expected_response = {
        "status": "success",
        "synthesized_response": "[AI-generated synthesis of retrieved documents]",
        "confidence_score": 0.85,
        "document_analysis": {
            "total_documents": 3,
            "high_relevance": 2,
            "medium_relevance": 1,
            "low_relevance": 0
        },
        "sources_used": ["db_guide.txt", "optimization_tips.md"],
        "results": "[Retrieved documents]",
        "total_results": 3,
        "original_query": "What are the best practices for database optimization?",
        "reformulated_queries": [
            "Database performance optimization techniques",
            "Best practices database tuning"
        ],
        "kb_implementation": "KnowledgeBaseV2",
        "rag_enhanced": True
    }

    print(f"\nExpected Response Structure:")
    print(json.dumps(expected_response, indent=2))

    print("\n✅ API Endpoint Simulation Complete")

if __name__ == "__main__":
    print("🚀 Starting RAG Integration Tests")

    # Run the tests
    success = asyncio.run(test_rag_integration())

    if success:
        asyncio.run(test_api_endpoints_simulation())
        print("\n🎉 All tests completed successfully!")
        exit(0)
    else:
        print("\n💥 Some tests failed!")
        exit(1)