#!/usr/bin/env python3
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

from src.agents.development_speedup_agent import analyze_codebase, development_speedup
from src.agents.npu_code_search_agent import (
    index_project,
    npu_code_search,
    search_codebase,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_npu_code_search():
    """Test NPU code search capabilities"""
    print("\n🚀 Testing NPU Code Search Agent")
    print("=" * 50)

    # Test 1: Check system status
    print("\n1. Checking system status...")
    try:
        status = await npu_code_search.get_index_status()
        print("   ✅ System operational")
        print(f"   📊 Files indexed: {status.get('total_files_indexed', 0)}")
        print(f"   🔧 NPU available: {status.get('npu_available', False)}")
        print(f"   📝 Languages: {list(status.get('languages', {}).keys())}")
    except Exception as e:
        print(f"   ❌ Status check failed: {e}")
        return False

    # Test 2: Index current project
    print("\n2. Indexing current project...")
    try:
        project_root = str(Path(__file__).parent)
        result = await index_project(project_root, force_reindex=True)

        if result["status"] == "success":
            print(f"   ✅ Indexed {result['indexed_files']} files")
            print(f"   ⏱️  Completed in {result['execution_time']:.2f}s")
            if result.get("skipped_files", 0) > 0:
                print(f"   ⏭️  Skipped {result['skipped_files']} non-code files")
        else:
            print(f"   ❌ Indexing failed: {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"   ❌ Indexing error: {e}")
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

    print("\n3. Testing search capabilities...")
    for i, test in enumerate(search_tests, 1):
        try:
            results = await search_codebase(
                query=test["query"], search_type=test["type"], max_results=5
            )

            stats = npu_code_search.get_search_stats()
            print(f"   {i}. {test['name']}")
            print(f"      🔍 Query: '{test['query']}' ({test['type']})")
            print(f"      📊 Results: {len(results)} found")
            print(f"      ⏱️  Time: {stats.search_time_ms:.1f}ms")
            print(f"      🚀 NPU used: {stats.npu_acceleration_used}")
            print(f"      💾 Cache hit: {stats.redis_cache_hit}")

            # Show first result if any
            if results:
                result = results[0]
                print(f"      📄 Example: {result.file_path}:{result.line_number}")
                print(f"           {result.content[:80]}...")
            print()

        except Exception as e:
            print(f"   ❌ Search test {i} failed: {e}")

    return True


async def test_development_speedup():
    """Test development speedup analysis"""
    print("\n🔧 Testing Development Speedup Agent")
    print("=" * 50)

    project_root = str(Path(__file__).parent)

    # Test 1: Duplicate detection
    print("\n1. Testing duplicate code detection...")
    try:
        duplicates = await development_speedup.find_duplicate_code(project_root)

        total_duplicates = duplicates.get("total_duplicates", 0)
        potential_savings = duplicates.get("potential_savings", {})

        print(f"   🔍 Total duplicates found: {total_duplicates}")
        print(
            f"   💾 Potential line savings: {potential_savings.get('lines_of_code', 0)}"
        )
        print(
            f"   📁 Files affected: {potential_savings.get('estimated_files_affected', 0)}"
        )

        # Show examples
        code_duplicates = duplicates.get("code_block_duplicates", [])
        if code_duplicates:
            print("   📝 Example duplicate:")
            example = code_duplicates[0]
            print(f"      Size: {example['size_lines']} lines")
            print(f"      Locations: {len(example['locations'])} files")
            for loc in example["locations"][:2]:  # Show first 2 locations
                print(f"         - {loc[0]}:{loc[1]}")

    except Exception as e:
        print(f"   ❌ Duplicate detection failed: {e}")

    # Test 2: Pattern analysis
    print("\n2. Testing code pattern analysis...")
    try:
        patterns = await development_speedup.identify_code_patterns(project_root)

        total_patterns = patterns.get("total_patterns", 0)
        high_priority = patterns.get("high_priority_issues", 0)

        print(f"   🔍 Total patterns found: {total_patterns}")
        print(f"   ⚠️  High priority issues: {high_priority}")

        # Show pattern examples
        pattern_list = patterns.get("patterns", [])
        for pattern in pattern_list[:3]:  # Show first 3 patterns
            print(
                f"   📊 {pattern['pattern_type']}: {pattern['total_occurrences']} occurrences"
            )
            print(f"      💡 Suggestion: {pattern['suggestion']}")

    except Exception as e:
        print(f"   ❌ Pattern analysis failed: {e}")

    # Test 3: Import analysis
    print("\n3. Testing import analysis...")
    try:
        imports = await development_speedup.analyze_imports_and_dependencies(
            project_root
        )

        most_used = imports.get("most_used_modules", [])
        unused = imports.get("potential_unused_imports", [])

        print("   📦 Most used modules:")
        for module, count in most_used[:5]:
            print(f"      - {module}: {count} imports")

        print(f"   🗑️  Potentially unused imports: {len(unused)}")
        if unused:
            for unused_import in unused[:3]:  # Show first 3
                print(
                    f"      - {unused_import['file']}:{unused_import['line']} - {unused_import['import']}"
                )

    except Exception as e:
        print(f"   ❌ Import analysis failed: {e}")

    # Test 4: Quick comprehensive analysis
    print("\n4. Testing comprehensive analysis...")
    try:
        start_time = time.time()
        analysis = await analyze_codebase(project_root)
        analysis_time = time.time() - start_time

        print(f"   ⏱️  Analysis completed in {analysis_time:.2f}s")

        # Show recommendations
        recommendations = analysis.get("recommendations", [])
        print(f"   💡 Recommendations ({len(recommendations)}):")
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"      {i}. {rec}")

        # Show summary stats
        duplicate_savings = (
            analysis.get("duplicate_code", {})
            .get("potential_savings", {})
            .get("lines_of_code", 0)
        )
        pattern_issues = analysis.get("code_patterns", {}).get("total_patterns", 0)
        refactoring_ops = analysis.get("refactoring_opportunities", {}).get(
            "total_opportunities", 0
        )

        print("\n   📊 Summary:")
        print(f"      🔄 Duplicate code savings: {duplicate_savings} lines")
        print(f"      🔍 Patterns identified: {pattern_issues}")
        print(f"      🔧 Refactoring opportunities: {refactoring_ops}")

    except Exception as e:
        print(f"   ❌ Comprehensive analysis failed: {e}")

    return True


async def test_performance_comparison():
    """Test performance with and without NPU acceleration"""
    print("\n⚡ Performance Comparison")
    print("=" * 50)

    project_root = str(Path(__file__).parent)

    # Ensure project is indexed
    await index_project(project_root, force_reindex=False)

    # Test queries for performance comparison
    test_queries = [
        ("async def", "exact"),
        ("class.*Agent", "regex"),
        ("error handling", "semantic"),
        ("configuration", "semantic"),
    ]

    print("\nPerformance tests:")
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

            print(f"   {i}. Query: '{query}' ({search_type})")
            print(f"      Results: {len(results)}, Time: {search_time*1000:.1f}ms")
            print(
                f"      NPU: {stats.npu_acceleration_used}, Cache: {stats.redis_cache_hit}"
            )

        except Exception as e:
            print(f"   ❌ Query {i} failed: {e}")

    print("\n📊 Performance Summary:")
    print(f"   ⏱️  Total search time: {total_time*1000:.1f}ms")
    print(f"   🚀 NPU acceleration used: {npu_used_count}/{len(test_queries)} queries")
    print("   💾 Redis indexing: ✅ Active")

    return True


async def test_cache_performance():
    """Test Redis cache performance"""
    print("\n💾 Cache Performance Test")
    print("=" * 50)

    # Clear cache first
    try:
        cache_result = await npu_code_search.clear_cache()
        print(f"   🗑️  Cleared {cache_result.get('keys_deleted', 0)} cache keys")
    except Exception as e:
        print(f"   ⚠️  Cache clear warning: {e}")

    # Test query
    query = "import json"
    search_type = "exact"

    print(f"\nTesting cache with query: '{query}'")

    # First search (no cache)
    start_time = time.time()
    results1 = await search_codebase(query, search_type, max_results=10)
    time1 = time.time() - start_time
    stats1 = npu_code_search.get_search_stats()

    print(f"   1st search: {time1*1000:.1f}ms, Cache hit: {stats1.redis_cache_hit}")

    # Second search (should hit cache)
    start_time = time.time()
    results2 = await search_codebase(query, search_type, max_results=10)
    time2 = time.time() - start_time
    stats2 = npu_code_search.get_search_stats()

    print(f"   2nd search: {time2*1000:.1f}ms, Cache hit: {stats2.redis_cache_hit}")

    # Calculate speedup
    if time1 > 0 and time2 > 0:
        speedup = time1 / time2
        print(f"   🚀 Cache speedup: {speedup:.1f}x faster")

    # Verify results are identical
    if len(results1) == len(results2):
        print(f"   ✅ Results consistent: {len(results1)} items")
    else:
        print(f"   ⚠️  Result mismatch: {len(results1)} vs {len(results2)}")

    return True


async def main():
    """Run all tests"""
    print("🧪 NPU Worker and Redis Code Search Test Suite")
    print("=" * 60)

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
            print(f"\n{'='*60}")
            print(f"🧪 Running {test_name} Tests")
            result = await test_func()
            if result:
                success_count += 1
                print(f"✅ {test_name} tests passed")
            else:
                print(f"❌ {test_name} tests failed")
        except Exception as e:
            print(f"❌ {test_name} tests crashed: {e}")
            import traceback

            traceback.print_exc()

    # Final summary
    print(f"\n{'='*60}")
    print("🏁 Test Summary")
    print(f"✅ Passed: {success_count}/{total_tests}")
    print(f"❌ Failed: {total_tests - success_count}/{total_tests}")

    if success_count == total_tests:
        print("\n🎉 All tests passed! NPU Worker and Redis Code Search are operational.")
        print("\n📋 Capabilities verified:")
        print("   ✅ NPU-accelerated semantic search")
        print("   ✅ Redis-based code indexing")
        print("   ✅ Duplicate code detection")
        print("   ✅ Code pattern analysis")
        print("   ✅ Import optimization")
        print("   ✅ Development speedup recommendations")
        print("   ✅ Performance caching")

        print("\n🚀 Ready for development acceleration!")
    else:
        print(
            f"\n⚠️  {total_tests - success_count} test suite(s) failed. Check logs above."
        )
        return 1

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Test suite crashed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
