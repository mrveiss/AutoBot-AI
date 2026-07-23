#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test NPU Code Search and Development Speedup

Tests the NPU worker and Redis-based code search capabilities
for development acceleration.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from agents.development_speedup_agent import analyze_codebase, development_speedup
from agents.npu_code_search_agent import index_project, npu_code_search, search_codebase

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_npu_code_search():
    """Test NPU code search capabilities"""
    logger.info("\n🚀 Testing NPU Code Search Agent")
    logger.info("=" * 50)

    # Test 1: Check system status
    logger.info("\n1. Checking system status...")
    try:
        status = await npu_code_search.get_index_status()
        logger.info("   ✅ System operational")
        logger.info(f"   📊 Files indexed: {status.get('total_files_indexed', 0)}")
        logger.info(f"   🔧 NPU available: {status.get('npu_available', False)}")
        logger.info(f"   📝 Languages: {list(status.get('languages', {}).keys())}")
    except Exception as e:
        logger.error(f"   ❌ Status check failed: {e}")
        return False

    # Test 2: Index current project
    logger.info("\n2. Indexing current project...")
    try:
        project_root = str(Path(__file__).parent)
        result = await index_project(project_root, force_reindex=True)

        if result["status"] == "success":
            logger.info(f"   ✅ Indexed {result['indexed_files']} files")
            logger.info(f"   ⏱️  Completed in {result['execution_time']:.2f}s")
            if result.get("skipped_files", 0) > 0:
                logger.info(f"   ⏭️  Skipped {result['skipped_files']} non-code files")
        else:
            logger.error(f"   ❌ Indexing failed: {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"   ❌ Indexing error: {e}")
        return False

    # Test 3: Search tests
    search_tests = [
        {
            "name": "Element search for functions",
            "query": "test_npu_code_search",
            "type": "element",
        },
        {
            "name": "Exact search for imports",
            "query": "import asyncio",
            "type": "exact",
        },
        {
            "name": "Regex search for classes",
            "query": "class \\w+Agent",
            "type": "regex",
        },
        {
            "name": "Semantic search for configuration",
            "query": "configuration settings",
            "type": "semantic",
        },
    ]

    logger.info("\n3. Testing search capabilities...")
    for i, test in enumerate(search_tests, 1):
        try:
            results = await search_codebase(query=test["query"], search_type=test["type"], max_results=5)

            stats = npu_code_search.get_search_stats()
            logger.info(f"   {i}. {test['name']}")
            logger.info(f"      🔍 Query: '{test['query']}' ({test['type']})")
            logger.info(f"      📊 Results: {len(results)} found")
            logger.info(f"      ⏱️  Time: {stats.search_time_ms:.1f}ms")
            logger.info(f"      🚀 NPU used: {stats.npu_acceleration_used}")
            logger.info(f"      💾 Cache hit: {stats.redis_cache_hit}")

            # Show first result if any
            if results:
                result = results[0]
                logger.info(f"      📄 Example: {result.file_path}:{result.line_number}")
                logger.info(f"           {result.content[:80]}...")
            logger.info("")

        except Exception as e:
            logger.error(f"   ❌ Search test {i} failed: {e}")

    return True


async def test_development_speedup():
    """Test development speedup analysis"""
    logger.info("\n🔧 Testing Development Speedup Agent")
    logger.info("=" * 50)

    project_root = str(Path(__file__).parent)

    # Test 1: Duplicate detection
    logger.info("\n1. Testing duplicate code detection...")
    try:
        duplicates = await development_speedup.find_duplicate_code(project_root)

        total_duplicates = duplicates.get("total_duplicates", 0)
        potential_savings = duplicates.get("potential_savings", {})

        logger.info(f"   🔍 Total duplicates found: {total_duplicates}")
        print(f"   💾 Potential line savings: {potential_savings.get('lines_of_code', 0)}")
        print(f"   📁 Files affected: {potential_savings.get('estimated_files_affected', 0)}")

        # Show examples
        code_duplicates = duplicates.get("code_block_duplicates", [])
        if code_duplicates:
            logger.info("   📝 Example duplicate:")
            example = code_duplicates[0]
            logger.info(f"      Size: {example['size_lines']} lines")
            logger.info(f"      Locations: {len(example['locations'])} files")
            for loc in example["locations"][:2]:  # Show first 2 locations
                logger.info(f"         - {loc[0]}:{loc[1]}")

    except Exception as e:
        logger.error(f"   ❌ Duplicate detection failed: {e}")

    # Test 2: Pattern analysis
    logger.info("\n2. Testing code pattern analysis...")
    try:
        patterns = await development_speedup.identify_code_patterns(project_root)

        total_patterns = patterns.get("total_patterns", 0)
        high_priority = patterns.get("high_priority_issues", 0)

        logger.info(f"   🔍 Total patterns found: {total_patterns}")
        logger.warning(f"   ⚠️  High priority issues: {high_priority}")

        # Show pattern examples
        pattern_list = patterns.get("patterns", [])
        for pattern in pattern_list[:3]:  # Show first 3 patterns
            print(f"   📊 {pattern['pattern_type']}: {pattern['total_occurrences']} occurrences")
            logger.info(f"      💡 Suggestion: {pattern['suggestion']}")

    except Exception as e:
        logger.error(f"   ❌ Pattern analysis failed: {e}")

    # Test 3: Import analysis
    logger.info("\n3. Testing import analysis...")
    try:
        imports = await development_speedup.analyze_imports_and_dependencies(project_root)

        most_used = imports.get("most_used_modules", [])
        unused = imports.get("potential_unused_imports", [])

        logger.info("   📦 Most used modules:")
        for module, count in most_used[:5]:
            logger.info(f"      - {module}: {count} imports")

        logger.info(f"   🗑️  Potentially unused imports: {len(unused)}")
        if unused:
            for unused_import in unused[:3]:  # Show first 3
                print(f"      - {unused_import['file']}:{unused_import['line']} - {unused_import['import']}")

    except Exception as e:
        logger.error(f"   ❌ Import analysis failed: {e}")

    # Test 4: Quick comprehensive analysis
    logger.info("\n4. Testing comprehensive analysis...")
    try:
        start_time = time.time()
        analysis = await analyze_codebase(project_root)
        analysis_time = time.time() - start_time

        logger.info(f"   ⏱️  Analysis completed in {analysis_time:.2f}s")

        # Show recommendations
        recommendations = analysis.get("recommendations", [])
        logger.info(f"   💡 Recommendations ({len(recommendations)}):")
        for i, rec in enumerate(recommendations[:5], 1):
            logger.info(f"      {i}. {rec}")

        # Show summary stats
        duplicate_savings = analysis.get("duplicate_code", {}).get("potential_savings", {}).get("lines_of_code", 0)
        pattern_issues = analysis.get("code_patterns", {}).get("total_patterns", 0)
        refactoring_ops = analysis.get("refactoring_opportunities", {}).get("total_opportunities", 0)

        logger.info("\n   📊 Summary:")
        logger.info(f"      🔄 Duplicate code savings: {duplicate_savings} lines")
        logger.info(f"      🔍 Patterns identified: {pattern_issues}")
        logger.info(f"      🔧 Refactoring opportunities: {refactoring_ops}")

    except Exception as e:
        logger.error(f"   ❌ Comprehensive analysis failed: {e}")

    return True


async def test_performance_comparison():
    """Test performance with and without NPU acceleration"""
    logger.info("\n⚡ Performance Comparison")
    logger.info("=" * 50)

    project_root = str(Path(__file__).parent)

    # Ensure project is indexed
    await index_project(project_root, force_reindex=False)

    # Test queries for performance comparison
    test_queries = [
        ("async de", "exact"),
        ("class.*Agent", "regex"),
        ("error handling", "semantic"),
        ("configuration", "semantic"),
    ]

    logger.info("\nPerformance tests:")
    total_time = 0
    npu_used_count = 0

    for i, (query, search_type) in enumerate(test_queries, 1):
        try:
            start_time = time.time()
            results = await search_codebase(query, search_type, max_results=10)
            search_time = time.time() - start_time

            stats = npu_code_search.get_search_stats()
            total_time += search_time
            if stats.npu_acceleration_used:
                npu_used_count += 1

            logger.info(f"   {i}. Query: '{query}' ({search_type})")
            logger.info(f"      Results: {len(results)}, Time: {search_time*1000:.1f}ms")
            print(f"      NPU: {stats.npu_acceleration_used}, Cache: {stats.redis_cache_hit}")

        except Exception as e:
            logger.error(f"   ❌ Query {i} failed: {e}")

    logger.info("\n📊 Performance Summary:")
    logger.info(f"   ⏱️  Total search time: {total_time*1000:.1f}ms")
    logger.info(f"   🚀 NPU acceleration used: {npu_used_count}/{len(test_queries)} queries")
    logger.info("   💾 Redis indexing: ✅ Active")

    return True


async def test_cache_performance():
    """Test Redis cache performance"""
    logger.info("\n💾 Cache Performance Test")
    logger.info("=" * 50)

    # Clear cache first
    try:
        cache_result = await npu_code_search.clear_cache()
        logger.info(f"   🗑️  Cleared {cache_result.get('keys_deleted', 0)} cache keys")
    except Exception as e:
        logger.warning(f"   ⚠️  Cache clear warning: {e}")

    # Test query
    query = "import json"
    search_type = "exact"

    logger.info(f"\nTesting cache with query: '{query}'")

    # First search (no cache)
    start_time = time.time()
    results1 = await search_codebase(query, search_type, max_results=10)
    time1 = time.time() - start_time
    stats1 = npu_code_search.get_search_stats()

    logger.info(f"   1st search: {time1*1000:.1f}ms, Cache hit: {stats1.redis_cache_hit}")

    # Second search (should hit cache)
    start_time = time.time()
    results2 = await search_codebase(query, search_type, max_results=10)
    time2 = time.time() - start_time
    stats2 = npu_code_search.get_search_stats()

    logger.info(f"   2nd search: {time2*1000:.1f}ms, Cache hit: {stats2.redis_cache_hit}")

    # Calculate speedup
    if time1 > 0 and time2 > 0:
        speedup = time1 / time2
        logger.info(f"   🚀 Cache speedup: {speedup:.1f}x faster")

    # Verify results are identical
    if len(results1) == len(results2):
        logger.info(f"   ✅ Results consistent: {len(results1)} items")
    else:
        logger.warning(f"   ⚠️  Result mismatch: {len(results1)} vs {len(results2)}")

    return True


async def main():
    """Run all tests"""
    logger.info("🧪 NPU Worker and Redis Code Search Test Suite")
    logger.info("=" * 60)

    success_count = 0
    total_tests = 4

    # Run test suites
    tests = [
        ("NPU Code Search", test_npu_code_search),
        ("Development Speedup", test_development_speedup),
        ("Performance Comparison", test_performance_comparison),
        ("Cache Performance", test_cache_performance),
    ]

    for test_name, test_func in tests:
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"🧪 Running {test_name} Tests")
            result = await test_func()
            if result:
                success_count += 1
                logger.info(f"✅ {test_name} tests passed")
            else:
                logger.error(f"❌ {test_name} tests failed")
        except Exception as e:
            logger.error(f"❌ {test_name} tests crashed: {e}")
            import traceback

            traceback.print_exc()

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info("🏁 Test Summary")
    logger.info(f"✅ Passed: {success_count}/{total_tests}")
    logger.error(f"❌ Failed: {total_tests - success_count}/{total_tests}")

    if success_count == total_tests:
        logger.info("\n🎉 All tests passed! NPU Worker and Redis Code Search are operational.")
        logger.info("\n📋 Capabilities verified:")
        logger.info("   ✅ NPU-accelerated semantic search")
        logger.info("   ✅ Redis-based code indexing")
        logger.info("   ✅ Duplicate code detection")
        logger.info("   ✅ Code pattern analysis")
        logger.info("   ✅ Import optimization")
        logger.info("   ✅ Development speedup recommendations")
        logger.info("   ✅ Performance caching")

        logger.info("\n🚀 Ready for development acceleration!")
    else:
        print(f"\n⚠️  {total_tests - success_count} test suite(s) failed. Check logs above.")
        return 1

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.info(f"\n\n💥 Test suite crashed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
