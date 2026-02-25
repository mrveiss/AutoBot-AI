#!/usr/bin/env python3
"""
Analyze AutoBot codebase for performance issues, memory leaks, and processing inefficiencies
"""

import asyncio
import json
from pathlib import Path

from performance_analyzer import PerformanceAnalyzer


async def analyze_performance_issues():
    """Analyze codebase for performance and memory issues"""

    print("🚀 Starting performance and memory leak analysis...")  # noqa: print

    analyzer = PerformanceAnalyzer()

    # Run analysis
    results = await analyzer.analyze_performance(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    print("\n=== Performance Analysis Results ===\n")  # noqa: print

    # Summary
    print(f"📊 **Analysis Summary:**")  # noqa: print
    print(
        f"   - Total performance issues: {results['total_performance_issues']}"
    )  # noqa: print
    print(f"   - Critical issues: {results['critical_issues']}")  # noqa: print
    print(
        f"   - High priority issues: {results['high_priority_issues']}"
    )  # noqa: print
    print(
        f"   - Files with issues: {results['metrics']['files_with_issues']}"
    )  # noqa: print
    print(  # noqa: print
        f"   - Performance debt score: {results['metrics']['performance_debt_score']}"
    )
    print(
        f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n"
    )  # noqa: print

    # Category breakdown
    print("🏷️  **Issue Categories:**")  # noqa: print
    for category, count in results["categories"].items():
        print(
            f"   - {category.replace('_', ' ').title()}: {count} issues"
        )  # noqa: print
    print()  # noqa: print

    # Critical issues (Memory leaks and blocking calls)
    critical_issues = [
        item
        for item in results["performance_details"]
        if item["severity"] == "critical"
    ]
    if critical_issues:
        print("🚨 **Critical Performance Issues:**")  # noqa: print
        for issue in critical_issues[:10]:  # Show top 10
            print(
                f"   - {issue['file']}:{issue['line']} - {issue['type']}"
            )  # noqa: print
            print(f"     💡 {issue['description']}")  # noqa: print
            print(f"     🔧 Suggestion: {issue['suggestion']}")  # noqa: print
            print()  # noqa: print

    # High priority issues
    high_issues = [
        item for item in results["performance_details"] if item["severity"] == "high"
    ]
    if high_issues:
        print("⚠️  **High Priority Performance Issues:**")  # noqa: print
        for issue in high_issues[:5]:  # Show top 5
            print(
                f"   - {issue['file']}:{issue['line']} - {issue['type']}"
            )  # noqa: print
            print(f"     {issue['description']}")  # noqa: print
        print()  # noqa: print

    # Memory leak specific analysis
    memory_issues = [
        item
        for item in results["performance_details"]
        if item["type"] == "memory_leaks"
    ]
    if memory_issues:
        print("💾 **Memory Leak Analysis:**")  # noqa: print
        print(f"   Found {len(memory_issues)} potential memory leaks:")  # noqa: print
        for issue in memory_issues[:5]:
            print(f"   - {issue['file']}:{issue['line']}")  # noqa: print
            print(  # noqa: print
                f"     Code: {issue['code_snippet'].split()[0] if issue['code_snippet'] else 'N/A'}"
            )
        print()  # noqa: print

    # Blocking call analysis
    blocking_issues = [
        item
        for item in results["performance_details"]
        if item["type"] == "blocking_calls"
    ]
    if blocking_issues:
        print("🔒 **Blocking Call Analysis:**")  # noqa: print
        print(
            f"   Found {len(blocking_issues)} blocking calls in async functions:"
        )  # noqa: print
        for issue in blocking_issues[:5]:
            print(f"   - {issue['file']}:{issue['line']}")  # noqa: print
            print(f"     Function: {issue['function'] or 'N/A'}")  # noqa: print
        print()  # noqa: print

    # Database performance issues
    db_issues = [
        item for item in results["performance_details"] if "database" in item["type"]
    ]
    if db_issues:
        print("🗄️  **Database Performance Issues:**")  # noqa: print
        print(
            f"   Found {len(db_issues)} database-related performance issues:"
        )  # noqa: print
        for issue in db_issues[:3]:
            print(f"   - {issue['file']}:{issue['line']}")  # noqa: print
            print(f"     {issue['description']}")  # noqa: print
        print()  # noqa: print

    # Save detailed report
    report_path = Path("performance_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"📋 Detailed report saved to: {report_path}")  # noqa: print

    # Generate optimization recommendations
    await generate_performance_fixes(results)

    return results


async def generate_performance_fixes(results):
    """Generate specific performance fix recommendations"""

    print("\n=== Performance Optimization Recommendations ===\n")  # noqa: print

    recommendations = results["optimization_recommendations"]

    if recommendations:
        print("🔧 **Priority Fixes:**")  # noqa: print

        for rec in recommendations:
            print(f"\n**{rec['title']}** ({rec['priority']} priority)")  # noqa: print
            print(f"   Description: {rec['description']}")  # noqa: print
            print(f"   Affected files: {len(rec['affected_files'])}")  # noqa: print

            if rec["code_examples"]:
                for example in rec["code_examples"]:
                    print(f"   \n   Before:")  # noqa: print
                    print(f"   ```python")  # noqa: print
                    print(f"   {example.get('before', 'N/A')}")  # noqa: print
                    print(f"   ```")  # noqa: print
                    print(f"   \n   After:")  # noqa: print
                    print(f"   ```python")  # noqa: print
                    print(f"   {example.get('after', 'N/A')}")  # noqa: print
                    print(f"   ```")  # noqa: print
        print()  # noqa: print

    # Generate specific common fixes
    print("🛠️  **Common Performance Patterns to Fix:**\n")  # noqa: print

    # Memory leak fixes
    print("**1. Memory Leak Prevention:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Bad - Resource leak")  # noqa: print
    print("f = open('file.txt', 'r')")  # noqa: print
    print("data = f.read()")  # noqa: print
    print()  # noqa: print
    print("# ✅ Good - Proper resource management")  # noqa: print
    print("with open('file.txt', 'r') as f:")  # noqa: print
    print("    data = f.read()")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Async/await fixes
    print("**2. Async Function Optimization:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Bad - Blocking call in async function")  # noqa: print
    print("async def fetch_data():")  # noqa: print
    print("    time.sleep(1)  # Blocks event loop")  # noqa: print
    print("    return requests.get(url)  # Blocking")  # noqa: print
    print()  # noqa: print
    print("# ✅ Good - Non-blocking async operations")  # noqa: print
    print("async def fetch_data():")  # noqa: print
    print("    await asyncio.sleep(1)  # Non-blocking")  # noqa: print
    print("    async with aiohttp.ClientSession() as session:")  # noqa: print
    print("        async with session.get(url) as response:")  # noqa: print
    print("            return await response.text()")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Database optimization
    print("**3. Database Query Optimization:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Bad - N+1 query problem")  # noqa: print
    print("for user in users:")  # noqa: print
    print(
        "    profile = db.query(Profile).filter(Profile.user_id == user.id).first()"
    )  # noqa: print
    print()  # noqa: print
    print("# ✅ Good - Bulk query")  # noqa: print
    print("user_ids = [user.id for user in users]")  # noqa: print
    print(
        "profiles = db.query(Profile).filter(Profile.user_id.in_(user_ids)).all()"
    )  # noqa: print
    print("profile_dict = {p.user_id: p for p in profiles}")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Loop optimization
    print("**4. Loop Performance Optimization:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Bad - Inefficient loop with string concatenation")  # noqa: print
    print("result = ''")  # noqa: print
    print("for item in large_list:")  # noqa: print
    print("    result += str(item)  # Creates new string each time")  # noqa: print
    print()  # noqa: print
    print("# ✅ Good - Efficient list comprehension and join")  # noqa: print
    print("result = ''.join(str(item) for item in large_list)")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Redis caching patterns
    print("**5. Efficient Caching Patterns:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Bad - No caching, repeated expensive operations")  # noqa: print
    print("def get_user_data(user_id):")  # noqa: print
    print("    return expensive_database_query(user_id)")  # noqa: print
    print()  # noqa: print
    print("# ✅ Good - Redis caching with TTL")  # noqa: print
    print("async def get_user_data(user_id):")  # noqa: print
    print("    cache_key = f'user:{user_id}'")  # noqa: print
    print("    cached = await redis_client.get(cache_key)")  # noqa: print
    print("    if cached:")  # noqa: print
    print("        return json.loads(cached)")  # noqa: print
    print("    ")  # noqa: print
    print("    data = expensive_database_query(user_id)")  # noqa: print
    print(
        "    await redis_client.setex(cache_key, 300, json.dumps(data))"
    )  # noqa: print
    print("    return data")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print


async def demonstrate_monitoring_setup():
    """Show how to set up performance monitoring"""

    print("=== Performance Monitoring Setup ===\n")  # noqa: print

    print("🔍 **Add Performance Monitoring:**")  # noqa: print
    print()  # noqa: print

    print("**1. Memory Usage Monitoring:**")  # noqa: print
    print("```python")  # noqa: print
    print("import psutil")  # noqa: print
    print("import logging")  # noqa: print
    print()  # noqa: print
    print("def log_memory_usage(func_name: str):")  # noqa: print
    print("    process = psutil.Process()")  # noqa: print
    print("    memory_mb = process.memory_info().rss / 1024 / 1024")  # noqa: print
    print(
        "    logging.info(f'{func_name}: Memory usage: {memory_mb:.2f} MB')"
    )  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    print("**2. Execution Time Tracking:**")  # noqa: print
    print("```python")  # noqa: print
    print("import time")  # noqa: print
    print("from functools import wraps")  # noqa: print
    print()  # noqa: print
    print("def performance_monitor(func):")  # noqa: print
    print("    @wraps(func)")  # noqa: print
    print("    async def wrapper(*args, **kwargs):")  # noqa: print
    print("        start_time = time.time()")  # noqa: print
    print("        result = await func(*args, **kwargs)")  # noqa: print
    print("        execution_time = time.time() - start_time")  # noqa: print
    print("        ")  # noqa: print
    print("        if execution_time > 1.0:  # Log slow operations")  # noqa: print
    print(
        "            logging.warning(f'{func.__name__} took {execution_time:.2f}s')"
    )  # noqa: print
    print("        ")  # noqa: print
    print("        return result")  # noqa: print
    print("    return wrapper")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    print("**3. Redis Performance Monitoring:**")  # noqa: print
    print("```python")  # noqa: print
    print("async def monitor_redis_performance():")  # noqa: print
    print("    info = await redis_client.info('memory')")  # noqa: print
    print("    used_memory = info['used_memory_human']")  # noqa: print
    print("    connected_clients = info['connected_clients']")  # noqa: print
    print("    ")  # noqa: print
    print(  # noqa: print
        "    logging.info(f'Redis memory: {used_memory}, Clients: {connected_clients}')"
    )
    print("```")  # noqa: print
    print()  # noqa: print


async def main():
    """Run the performance analysis"""

    # Analyze performance issues
    await analyze_performance_issues()

    # Show monitoring setup
    await demonstrate_monitoring_setup()

    print("\n=== Analysis Complete ===")  # noqa: print
    print("Next steps:")  # noqa: print
    print(
        "1. Review performance_analysis_report.json for detailed findings"
    )  # noqa: print
    print("2. Fix critical memory leaks and blocking calls first")  # noqa: print
    print("3. Optimize database queries and loops")  # noqa: print
    print("4. Add performance monitoring to track improvements")  # noqa: print
    print("5. Set up automated performance testing")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
