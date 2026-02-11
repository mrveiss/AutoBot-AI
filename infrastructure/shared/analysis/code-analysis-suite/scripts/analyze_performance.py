#!/usr/bin/env python3
"""
Analyze AutoBot codebase for performance issues, memory leaks, and processing inefficiencies
"""

import asyncio
import json
from pathlib import Path

import logging

logger = logging.getLogger(__name__)



async def _analyze_performance_issues_block_1():
    """Critical issues (Memory leaks and blocking calls).

    Helper for analyze_performance_issues (Issue #825).
    """
    # Critical issues (Memory leaks and blocking calls)
    critical_issues = [
        item
        for item in results["performance_details"]
        if item["severity"] == "critical"
    ]
    if critical_issues:
        logger.error("🚨 **Critical Performance Issues:**")
        for issue in critical_issues[:10]:  # Show top 10
            logger.info(f"   - {issue['file']}:{issue['line']} - {issue['type']}")
            logger.info(f"     💡 {issue['description']}")
            logger.info(f"     🔧 Suggestion: {issue['suggestion']}")
            logger.info("")


async def _analyze_performance_issues_block_5():
    """High priority issues.

    Helper for analyze_performance_issues (Issue #825).
    """
    # High priority issues
    high_issues = [
        item for item in results["performance_details"] if item["severity"] == "high"
    ]
    if high_issues:
        logger.warning("⚠️  **High Priority Performance Issues:**")
        for issue in high_issues[:5]:  # Show top 5
            logger.info(f"   - {issue['file']}:{issue['line']} - {issue['type']}")
            logger.info(f"     {issue['description']}")
        logger.info("")


async def _analyze_performance_issues_block_2():
    """Memory leak specific analysis.

    Helper for analyze_performance_issues (Issue #825).
    """
    # Memory leak specific analysis
    memory_issues = [
        item
        for item in results["performance_details"]
        if item["type"] == "memory_leaks"
    ]
    if memory_issues:
        logger.info("💾 **Memory Leak Analysis:**")
        logger.info(f"   Found {len(memory_issues)} potential memory leaks:")
        for issue in memory_issues[:5]:
            logger.info(f"   - {issue['file']}:{issue['line']}")
            logger.info("     Code: %s", issue['code_snippet'].split()[0] if issue['code_snippet'] else 'N/A')
        logger.info("")


async def _analyze_performance_issues_block_3():
    """Blocking call analysis.

    Helper for analyze_performance_issues (Issue #825).
    """
    # Blocking call analysis
    blocking_issues = [
        item
        for item in results["performance_details"]
        if item["type"] == "blocking_calls"
    ]
    if blocking_issues:
        logger.info("🔒 **Blocking Call Analysis:**")
        logger.info(f"   Found {len(blocking_issues)} blocking calls in async functions:")
        for issue in blocking_issues[:5]:
            logger.info(f"   - {issue['file']}:{issue['line']}")
            logger.info(f"     Function: {issue['function'] or 'N/A'}")
        logger.info("")


async def _analyze_performance_issues_block_4():
    """Database performance issues.

    Helper for analyze_performance_issues (Issue #825).
    """
    # Database performance issues
    db_issues = [
        item for item in results["performance_details"] if "database" in item["type"]
    ]
    if db_issues:
        logger.info("🗄️  **Database Performance Issues:**")
        logger.info(f"   Found {len(db_issues)} database-related performance issues:")
        for issue in db_issues[:3]:
            logger.info(f"   - {issue['file']}:{issue['line']}")
            logger.info(f"     {issue['description']}")
        logger.info("")

async def analyze_performance_issues():
    """Analyze codebase for performance and memory issues"""

    logger.info("🚀 Starting performance and memory leak analysis...")

    analyzer = PerformanceAnalyzer()

    # Run analysis
    results = await analyzer.analyze_performance(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    logger.info("\n=== Performance Analysis Results ===\n")

    # Summary
    logger.info(f"📊 **Analysis Summary:**")
    logger.info(f"   - Total performance issues: {results['total_performance_issues']}")
    logger.error(f"   - Critical issues: {results['critical_issues']}")
    logger.info(f"   - High priority issues: {results['high_priority_issues']}")
    logger.info(f"   - Files with issues: {results['metrics']['files_with_issues']}")
    logger.info("   - Performance debt score: %s", results['metrics']['performance_debt_score'])
    logger.info(f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n")

    # Category breakdown
    logger.info("🏷️  **Issue Categories:**")
    for category, count in results["categories"].items():
        logger.info(f"   - {category.replace('_', ' ').title()}: {count} issues")
    logger.info("")

    await _analyze_performance_issues_block_1()

    await _analyze_performance_issues_block_5()

    await _analyze_performance_issues_block_2()

    await _analyze_performance_issues_block_3()

    await _analyze_performance_issues_block_4()

    # Save detailed report
    report_path = Path("performance_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"📋 Detailed report saved to: {report_path}")

    # Generate optimization recommendations
    await generate_performance_fixes(results)

    return results



async def _generate_performance_fixes_block_4():
    """Memory leak fixes.

    Helper for generate_performance_fixes (Issue #825).
    """
    # Memory leak fixes
    logger.info("**1. Memory Leak Prevention:**")
    logger.info("```python")
    logger.error("# ❌ Bad - Resource leak")
    logger.info("f = open('file.txt', 'r')")
    logger.info("data = f.read()")
    logger.info("")
    logger.info("# ✅ Good - Proper resource management")
    logger.info("with open('file.txt', 'r') as f:")
    logger.info("    data = f.read()")
    logger.info("```")
    logger.info("")


async def _generate_performance_fixes_block_2():
    """Async/await fixes.

    Helper for generate_performance_fixes (Issue #825).
    """
    # Async/await fixes
    logger.info("**2. Async Function Optimization:**")
    logger.info("```python")
    logger.error("# ❌ Bad - Blocking call in async function")
    logger.info("async def fetch_data():")
    logger.info("    time.sleep(1)  # Blocks event loop")
    logger.info("    return requests.get(url)  # Blocking")
    logger.info("")
    logger.info("# ✅ Good - Non-blocking async operations")
    logger.info("async def fetch_data():")
    logger.info("    await asyncio.sleep(1)  # Non-blocking")
    logger.info("    async with aiohttp.ClientSession() as session:")
    logger.info("        async with session.get(url) as response:")
    logger.info("            return await response.text()")
    logger.info("```")
    logger.info("")


async def _generate_performance_fixes_block_3():
    """Database optimization.

    Helper for generate_performance_fixes (Issue #825).
    """
    # Database optimization
    logger.info("**3. Database Query Optimization:**")
    logger.info("```python")
    logger.error("# ❌ Bad - N+1 query problem")
    logger.info("for user in users:")
    logger.info("    profile = db.query(Profile).filter(Profile.user_id == user.id).first()")
    logger.info("")
    logger.info("# ✅ Good - Bulk query")
    logger.info("user_ids = [user.id for user in users]")
    logger.info("profiles = db.query(Profile).filter(Profile.user_id.in_(user_ids)).all()")
    logger.info("profile_dict = {p.user_id: p for p in profiles}")
    logger.info("```")
    logger.info("")


async def _generate_performance_fixes_block_1():
    """Redis caching patterns.

    Helper for generate_performance_fixes (Issue #825).
    """
    # Redis caching patterns
    logger.info("**5. Efficient Caching Patterns:**")
    logger.info("```python")
    logger.error("# ❌ Bad - No caching, repeated expensive operations")
    logger.info("def get_user_data(user_id):")
    logger.info("    return expensive_database_query(user_id)")
    logger.info("")
    logger.info("# ✅ Good - Redis caching with TTL")
    logger.info("async def get_user_data(user_id):")
    logger.info("    cache_key = f'user:{user_id}'")
    logger.info("    cached = await redis_client.get(cache_key)")
    logger.info("    if cached:")
    logger.info("        return json.loads(cached)")
    logger.info("    ")
    logger.info("    data = expensive_database_query(user_id)")
    logger.info("    await redis_client.setex(cache_key, 300, json.dumps(data))")
    logger.info("    return data")
    logger.info("```")
    logger.info("")

async def generate_performance_fixes(results):
    """Generate specific performance fix recommendations"""

    logger.info("\n=== Performance Optimization Recommendations ===\n")

    recommendations = results["optimization_recommendations"]

    if recommendations:
        logger.info("🔧 **Priority Fixes:**")

        for rec in recommendations:
            logger.info(f"\n**{rec['title']}** ({rec['priority']} priority)")
            logger.info(f"   Description: {rec['description']}")
            logger.info(f"   Affected files: {len(rec['affected_files'])}")

            if rec["code_examples"]:
                for example in rec["code_examples"]:
                    logger.info(f"   \n   Before:")
                    logger.info(f"   ```python")
                    logger.info(f"   {example.get('before', 'N/A')}")
                    logger.info(f"   ```")
                    logger.info(f"   \n   After:")
                    logger.info(f"   ```python")
                    logger.info(f"   {example.get('after', 'N/A')}")
                    logger.info(f"   ```")
        logger.info("")

    # Generate specific common fixes
    logger.info("🛠️  **Common Performance Patterns to Fix:**\n")

    await _generate_performance_fixes_block_4()

    await _generate_performance_fixes_block_2()

    await _generate_performance_fixes_block_3()

    # Loop optimization
    logger.info("**4. Loop Performance Optimization:**")
    logger.info("```python")
    logger.error("# ❌ Bad - Inefficient loop with string concatenation")
    logger.info("result = ''")
    logger.info("for item in large_list:")
    logger.info("    result += str(item)  # Creates new string each time")
    logger.info("")
    logger.info("# ✅ Good - Efficient list comprehension and join")
    logger.info("result = ''.join(str(item) for item in large_list)")
    logger.info("```")
    logger.info("")

    await _generate_performance_fixes_block_1()


async def demonstrate_monitoring_setup():
    """Show how to set up performance monitoring"""

    logger.info("=== Performance Monitoring Setup ===\n")

    logger.info("🔍 **Add Performance Monitoring:**")
    logger.info("")

    logger.info("**1. Memory Usage Monitoring:**")
    logger.info("```python")
    logger.info("import psutil")
    logger.info("import logging")
    logger.info("")
    logger.info("def log_memory_usage(func_name: str):")
    logger.info("    process = psutil.Process()")
    logger.info("    memory_mb = process.memory_info().rss / 1024 / 1024")
    logger.info("    logging.info(f'{func_name}: Memory usage: {memory_mb:.2f} MB')")
    logger.info("```")
    logger.info("")

    logger.info("**2. Execution Time Tracking:**")
    logger.info("```python")
    logger.info("import time")
    logger.info("from functools import wraps")
    logger.info("")
    logger.info("def performance_monitor(func):")
    logger.info("    @wraps(func)")
    logger.info("    async def wrapper(*args, **kwargs):")
    logger.info("        start_time = time.time()")
    logger.info("        result = await func(*args, **kwargs)")
    logger.info("        execution_time = time.time() - start_time")
    logger.info("        ")
    logger.info("        if execution_time > 1.0:  # Log slow operations")
    logger.warning("            logging.warning(f'{func.__name__} took {execution_time:.2f}s')")
    logger.info("        ")
    logger.info("        return result")
    logger.info("    return wrapper")
    logger.info("```")
    logger.info("")

    logger.info("**3. Redis Performance Monitoring:**")
    logger.info("```python")
    logger.info("async def monitor_redis_performance():")
    logger.info("    info = await redis_client.info('memory')")
    logger.info("    used_memory = info['used_memory_human']")
    logger.info("    connected_clients = info['connected_clients']")
    logger.info("    ")
    logger.info(
        "    logging.info(f'Redis memory: {used_memory}, Clients: {connected_clients}')"
    )
    logger.info("```")
    logger.info("")


async def main():
    """Run the performance analysis"""

    # Analyze performance issues
    await analyze_performance_issues()

    # Show monitoring setup
    await demonstrate_monitoring_setup()

    logger.info("\n=== Analysis Complete ===")
    logger.info("Next steps:")
    logger.info("1. Review performance_analysis_report.json for detailed findings")
    logger.error("2. Fix critical memory leaks and blocking calls first")
    logger.info("3. Optimize database queries and loops")
    logger.info("4. Add performance monitoring to track improvements")
    logger.info("5. Set up automated performance testing")


if __name__ == "__main__":
    asyncio.run(main())
