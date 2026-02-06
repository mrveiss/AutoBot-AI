#!/usr/bin/env python3
"""
Analyze AutoBot codebase for performance issues, memory leaks, and processing inefficiencies
"""

import asyncio
import json
from pathlib import Path

from src.performance_analyzer import PerformanceAnalyzer


async def analyze_performance_issues():
    """Analyze codebase for performance and memory issues"""

    print("🚀 Starting performance and memory leak analysis...")

    analyzer = PerformanceAnalyzer()

    # Run analysis
    results = await analyzer.analyze_performance(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    print("\n=== Performance Analysis Results ===\n")

    # Summary
    print(f"📊 **Analysis Summary:**")
    print(f"   - Total performance issues: {results['total_performance_issues']}")
    print(f"   - Critical issues: {results['critical_issues']}")
    print(f"   - High priority issues: {results['high_priority_issues']}")
    print(f"   - Files with issues: {results['metrics']['files_with_issues']}")
    print(
        f"   - Performance debt score: {results['metrics']['performance_debt_score']}"
    )
    print(f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n")

    # Category breakdown
    print("🏷️  **Issue Categories:**")
    for category, count in results["categories"].items():
        print(f"   - {category.replace('_', ' ').title()}: {count} issues")
    print()

    # Critical issues (Memory leaks and blocking calls)
    critical_issues = [
        item
        for item in results["performance_details"]
        if item["severity"] == "critical"
    ]
    if critical_issues:
        print("🚨 **Critical Performance Issues:**")
        for issue in critical_issues[:10]:  # Show top 10
            print(f"   - {issue['file']}:{issue['line']} - {issue['type']}")
            print(f"     💡 {issue['description']}")
            print(f"     🔧 Suggestion: {issue['suggestion']}")
            print()

    # High priority issues
    high_issues = [
        item for item in results["performance_details"] if item["severity"] == "high"
    ]
    if high_issues:
        print("⚠️  **High Priority Performance Issues:**")
        for issue in high_issues[:5]:  # Show top 5
            print(f"   - {issue['file']}:{issue['line']} - {issue['type']}")
            print(f"     {issue['description']}")
        print()

    # Memory leak specific analysis
    memory_issues = [
        item
        for item in results["performance_details"]
        if item["type"] == "memory_leaks"
    ]
    if memory_issues:
        print("💾 **Memory Leak Analysis:**")
        print(f"   Found {len(memory_issues)} potential memory leaks:")
        for issue in memory_issues[:5]:
            print(f"   - {issue['file']}:{issue['line']}")
            print(
                f"     Code: {issue['code_snippet'].split()[0] if issue['code_snippet'] else 'N/A'}"
            )
        print()

    # Blocking call analysis
    blocking_issues = [
        item
        for item in results["performance_details"]
        if item["type"] == "blocking_calls"
    ]
    if blocking_issues:
        print("🔒 **Blocking Call Analysis:**")
        print(f"   Found {len(blocking_issues)} blocking calls in async functions:")
        for issue in blocking_issues[:5]:
            print(f"   - {issue['file']}:{issue['line']}")
            print(f"     Function: {issue['function'] or 'N/A'}")
        print()

    # Database performance issues
    db_issues = [
        item for item in results["performance_details"] if "database" in item["type"]
    ]
    if db_issues:
        print("🗄️  **Database Performance Issues:**")
        print(f"   Found {len(db_issues)} database-related performance issues:")
        for issue in db_issues[:3]:
            print(f"   - {issue['file']}:{issue['line']}")
            print(f"     {issue['description']}")
        print()

    # Save detailed report
    report_path = Path("performance_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"📋 Detailed report saved to: {report_path}")

    # Generate optimization recommendations
    await generate_performance_fixes(results)

    return results


async def generate_performance_fixes(results):
    """Generate specific performance fix recommendations"""

    print("\n=== Performance Optimization Recommendations ===\n")

    recommendations = results["optimization_recommendations"]

    if recommendations:
        print("🔧 **Priority Fixes:**")

        for rec in recommendations:
            print(f"\n**{rec['title']}** ({rec['priority']} priority)")
            print(f"   Description: {rec['description']}")
            print(f"   Affected files: {len(rec['affected_files'])}")

            if rec["code_examples"]:
                for example in rec["code_examples"]:
                    print(f"   \n   Before:")
                    print(f"   ```python")
                    print(f"   {example.get('before', 'N/A')}")
                    print(f"   ```")
                    print(f"   \n   After:")
                    print(f"   ```python")
                    print(f"   {example.get('after', 'N/A')}")
                    print(f"   ```")
        print()

    # Generate specific common fixes
    print("🛠️  **Common Performance Patterns to Fix:**\n")

    # Memory leak fixes
    print("**1. Memory Leak Prevention:**")
    print("```python")
    print("# ❌ Bad - Resource leak")
    print("f = open('file.txt', 'r')")
    print("data = f.read()")
    print()
    print("# ✅ Good - Proper resource management")
    print("with open('file.txt', 'r') as f:")
    print("    data = f.read()")
    print("```")
    print()

    # Async/await fixes
    print("**2. Async Function Optimization:**")
    print("```python")
    print("# ❌ Bad - Blocking call in async function")
    print("async def fetch_data():")
    print("    time.sleep(1)  # Blocks event loop")
    print("    return requests.get(url)  # Blocking")
    print()
    print("# ✅ Good - Non-blocking async operations")
    print("async def fetch_data():")
    print("    await asyncio.sleep(1)  # Non-blocking")
    print("    async with aiohttp.ClientSession() as session:")
    print("        async with session.get(url) as response:")
    print("            return await response.text()")
    print("```")
    print()

    # Database optimization
    print("**3. Database Query Optimization:**")
    print("```python")
    print("# ❌ Bad - N+1 query problem")
    print("for user in users:")
    print("    profile = db.query(Profile).filter(Profile.user_id == user.id).first()")
    print()
    print("# ✅ Good - Bulk query")
    print("user_ids = [user.id for user in users]")
    print("profiles = db.query(Profile).filter(Profile.user_id.in_(user_ids)).all()")
    print("profile_dict = {p.user_id: p for p in profiles}")
    print("```")
    print()

    # Loop optimization
    print("**4. Loop Performance Optimization:**")
    print("```python")
    print("# ❌ Bad - Inefficient loop with string concatenation")
    print("result = ''")
    print("for item in large_list:")
    print("    result += str(item)  # Creates new string each time")
    print()
    print("# ✅ Good - Efficient list comprehension and join")
    print("result = ''.join(str(item) for item in large_list)")
    print("```")
    print()

    # Redis caching patterns
    print("**5. Efficient Caching Patterns:**")
    print("```python")
    print("# ❌ Bad - No caching, repeated expensive operations")
    print("def get_user_data(user_id):")
    print("    return expensive_database_query(user_id)")
    print()
    print("# ✅ Good - Redis caching with TTL")
    print("async def get_user_data(user_id):")
    print("    cache_key = f'user:{user_id}'")
    print("    cached = await redis_client.get(cache_key)")
    print("    if cached:")
    print("        return json.loads(cached)")
    print("    ")
    print("    data = expensive_database_query(user_id)")
    print("    await redis_client.setex(cache_key, 300, json.dumps(data))")
    print("    return data")
    print("```")
    print()


async def demonstrate_monitoring_setup():
    """Show how to set up performance monitoring"""

    print("=== Performance Monitoring Setup ===\n")

    print("🔍 **Add Performance Monitoring:**")
    print()

    print("**1. Memory Usage Monitoring:**")
    print("```python")
    print("import psutil")
    print("import logging")
    print()
    print("def log_memory_usage(func_name: str):")
    print("    process = psutil.Process()")
    print("    memory_mb = process.memory_info().rss / 1024 / 1024")
    print("    logging.info(f'{func_name}: Memory usage: {memory_mb:.2f} MB')")
    print("```")
    print()

    print("**2. Execution Time Tracking:**")
    print("```python")
    print("import time")
    print("from functools import wraps")
    print()
    print("def performance_monitor(func):")
    print("    @wraps(func)")
    print("    async def wrapper(*args, **kwargs):")
    print("        start_time = time.time()")
    print("        result = await func(*args, **kwargs)")
    print("        execution_time = time.time() - start_time")
    print("        ")
    print("        if execution_time > 1.0:  # Log slow operations")
    print("            logging.warning(f'{func.__name__} took {execution_time:.2f}s')")
    print("        ")
    print("        return result")
    print("    return wrapper")
    print("```")
    print()

    print("**3. Redis Performance Monitoring:**")
    print("```python")
    print("async def monitor_redis_performance():")
    print("    info = await redis_client.info('memory')")
    print("    used_memory = info['used_memory_human']")
    print("    connected_clients = info['connected_clients']")
    print("    ")
    print(
        "    logging.info(f'Redis memory: {used_memory}, Clients: {connected_clients}')"
    )
    print("```")
    print()


async def main():
    """Run the performance analysis"""

    # Analyze performance issues
    await analyze_performance_issues()

    # Show monitoring setup
    await demonstrate_monitoring_setup()

    print("\n=== Analysis Complete ===")
    print("Next steps:")
    print("1. Review performance_analysis_report.json for detailed findings")
    print("2. Fix critical memory leaks and blocking calls first")
    print("3. Optimize database queries and loops")
    print("4. Add performance monitoring to track improvements")
    print("5. Set up automated performance testing")


if __name__ == "__main__":
    asyncio.run(main())
