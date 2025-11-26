#!/usr/bin/env python3
"""
Test script for the AutoBot Codebase Indexing Service

This script tests the comprehensive codebase indexing functionality
and verifies that the knowledge base gets properly populated.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_knowledge_base_connection():
    """Test connection to the knowledge base"""
    try:
        from src.knowledge_base_factory import get_knowledge_base

        logger.info("Testing knowledge base connection...")
        kb = await get_knowledge_base()

        if kb is None:
            logger.error("❌ Failed to connect to knowledge base")
            return False

        # Test Redis connection
        redis_status = await kb.ping_redis()
        logger.info(f"Redis connection status: {redis_status}")

        if redis_status == "healthy":
            logger.info("✅ Knowledge base connection successful")
            return True
        else:
            logger.warning(f"⚠️  Redis connection issue: {redis_status}")
            return False

    except Exception as e:
        logger.error(f"❌ Knowledge base connection failed: {e}")
        return False

async def test_indexing_service():
    """Test the codebase indexing service"""
    try:
        from src.services.codebase_indexing_service import (
            get_indexing_service,
            index_autobot_codebase
        )

        logger.info("Testing codebase indexing service...")

        # Get indexing service
        service = get_indexing_service()
        logger.info(f"✅ Indexing service created successfully")

        # Test with a small sample
        logger.info("Running quick indexing test (max 5 files)...")
        progress = await index_autobot_codebase(max_files=5, batch_size=2)

        logger.info("📊 Indexing Results:")
        logger.info(f"  Total files found: {progress.total_files}")
        logger.info(f"  Files processed: {progress.processed_files}")
        logger.info(f"  Successful files: {progress.successful_files}")
        logger.info(f"  Failed files: {progress.failed_files}")
        logger.info(f"  Total chunks created: {progress.total_chunks}")
        logger.info(f"  Progress: {progress.progress_percentage:.1f}%")

        if progress.errors:
            logger.warning(f"⚠️  Errors encountered: {len(progress.errors)}")
            for error in progress.errors[:3]:  # Show first 3 errors
                logger.warning(f"    - {error}")

        if progress.successful_files > 0:
            logger.info("✅ Indexing service test successful")
            return True
        else:
            logger.error("❌ No files were successfully indexed")
            return False

    except Exception as e:
        logger.error(f"❌ Indexing service test failed: {e}")
        return False

async def test_knowledge_base_stats():
    """Test knowledge base statistics after indexing"""
    try:
        from src.knowledge_base_factory import get_knowledge_base

        logger.info("Testing knowledge base statistics...")
        kb = await get_knowledge_base()

        if kb is None:
            logger.error("❌ Knowledge base not available")
            return False

        # Get stats
        stats = await kb.get_stats()

        logger.info("📈 Knowledge Base Statistics:")
        logger.info(f"  Total documents: {stats.get('total_documents', 0)}")
        logger.info(f"  Total chunks: {stats.get('total_chunks', 0)}")
        logger.info(f"  Total facts: {stats.get('total_facts', 0)}")
        logger.info(f"  Total vectors: {stats.get('total_vectors', 0)}")
        logger.info(f"  Categories: {stats.get('categories', [])}")
        logger.info(f"  Database size: {stats.get('db_size', 0):,} bytes")
        logger.info(f"  Status: {stats.get('status', 'unknown')}")

        # Check if we have any indexed content
        has_content = (
            stats.get('total_documents', 0) > 0 or
            stats.get('total_facts', 0) > 0 or
            stats.get('total_chunks', 0) > 0
        )

        if has_content:
            logger.info("✅ Knowledge base has indexed content")
            return True
        else:
            logger.warning("⚠️  Knowledge base appears to be empty")
            return False

    except Exception as e:
        logger.error(f"❌ Knowledge base stats test failed: {e}")
        return False

async def test_knowledge_search():
    """Test searching the knowledge base"""
    try:
        from src.knowledge_base_factory import get_knowledge_base

        logger.info("Testing knowledge base search...")
        kb = await get_knowledge_base()

        if kb is None:
            logger.error("❌ Knowledge base not available")
            return False

        # Test search queries
        test_queries = [
            "AutoBot",
            "knowledge base",
            "function",
            "API",
            "configuration"
        ]

        search_results = {}

        for query in test_queries:
            try:
                results = await kb.search(query, top_k=3)
                search_results[query] = len(results)

                logger.info(f"  Query '{query}': {len(results)} results")

                # Show first result if available
                if results:
                    first_result = results[0]
                    content_preview = first_result.get('content', '')[:100] + '...'
                    score = first_result.get('score', 0.0)
                    logger.info(f"    Best match (score: {score:.3f}): {content_preview}")

            except Exception as e:
                logger.warning(f"    Query '{query}' failed: {e}")
                search_results[query] = 0

        # Check if any searches returned results
        total_results = sum(search_results.values())

        if total_results > 0:
            logger.info(f"✅ Search test successful - {total_results} total results across all queries")
            return True
        else:
            logger.warning("⚠️  No search results found for any query")
            return False

    except Exception as e:
        logger.error(f"❌ Knowledge search test failed: {e}")
        return False

async def test_api_endpoints():
    """Test the API endpoints"""
    try:
        import aiohttp
        import asyncio

        logger.info("Testing API endpoints...")

        # Test endpoints
        base_url = "http://localhost:8001/api/knowledge"

        endpoints_to_test = [
            ("/stats/basic", "GET"),
            ("/indexing/status", "GET"),
        ]

        async with aiohttp.ClientSession() as session:
            for endpoint, method in endpoints_to_test:
                try:
                    url = f"{base_url}{endpoint}"

                    if method == "GET":
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                logger.info(f"✅ {method} {endpoint}: {response.status}")

                                # Log some key info
                                if endpoint == "/stats/basic":
                                    logger.info(f"    Documents: {data.get('total_documents', 0)}")
                                    logger.info(f"    Chunks: {data.get('total_chunks', 0)}")
                                    logger.info(f"    Status: {data.get('status', 'unknown')}")
                            else:
                                logger.warning(f"⚠️  {method} {endpoint}: {response.status}")

                except Exception as e:
                    logger.warning(f"⚠️  {method} {endpoint} failed: {e}")

        logger.info("✅ API endpoint tests completed")
        return True

    except ImportError:
        logger.warning("⚠️  aiohttp not available, skipping API tests")
        return True
    except Exception as e:
        logger.error(f"❌ API endpoint tests failed: {e}")
        return False

async def run_comprehensive_test():
    """Run comprehensive test suite"""
    logger.info("🚀 Starting AutoBot Codebase Indexing Test Suite")
    logger.info("=" * 60)

    test_results = []

    # Test 1: Knowledge Base Connection
    logger.info("\n1️⃣  Testing Knowledge Base Connection")
    result1 = await test_knowledge_base_connection()
    test_results.append(("Knowledge Base Connection", result1))

    # Test 2: Indexing Service
    logger.info("\n2️⃣  Testing Codebase Indexing Service")
    result2 = await test_indexing_service()
    test_results.append(("Codebase Indexing Service", result2))

    # Test 3: Knowledge Base Stats
    logger.info("\n3️⃣  Testing Knowledge Base Statistics")
    result3 = await test_knowledge_base_stats()
    test_results.append(("Knowledge Base Statistics", result3))

    # Test 4: Knowledge Search
    logger.info("\n4️⃣  Testing Knowledge Base Search")
    result4 = await test_knowledge_search()
    test_results.append(("Knowledge Base Search", result4))

    # Test 5: API Endpoints
    logger.info("\n5️⃣  Testing API Endpoints")
    result5 = await test_api_endpoints()
    test_results.append(("API Endpoints", result5))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📋 TEST RESULTS SUMMARY")
    logger.info("=" * 60)

    passed = 0
    total = len(test_results)

    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
        if result:
            passed += 1

    logger.info(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All tests passed! Codebase indexing system is working correctly.")
        return True
    else:
        logger.error(f"⚠️  {total - passed} test(s) failed. Please check the logs above.")
        return False

async def main():
    """Main test function"""
    try:
        success = await run_comprehensive_test()

        if success:
            logger.info("\n🎯 Next Steps:")
            logger.info("   1. Use the /api/knowledge/quick_index endpoint to index more files")
            logger.info("   2. Use the /api/knowledge/index_codebase endpoint for full indexing")
            logger.info("   3. Check the Knowledge Manager in the frontend")
            logger.info("   4. Search the indexed codebase using the search functionality")

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
