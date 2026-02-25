#!/usr/bin/env python3
"""
Analyze AutoBot codebase for performance issues, memory leaks, and processing inefficiencies
"""

import asyncio
import json
from pathlib import Path

from performance_analyzer import PerformanceAnalyzer


def _print_perf_summary(results: dict) -> None:
    """Print performance analysis summary and category breakdown. Issue #1183."""
    print("\n=== Performance Analysis Results ===\n")  # noqa: print
    m = results["metrics"]
    print("📊 **Analysis Summary:**")  # noqa: print
    print(
        f"   - Total performance issues: {results['total_performance_issues']}"
    )  # noqa: print
    print(f"   - Critical issues: {results['critical_issues']}")  # noqa: print
    print(
        f"   - High priority issues: {results['high_priority_issues']}"
    )  # noqa: print
    print(f"   - Files with issues: {m['files_with_issues']}")  # noqa: print
    print(f"   - Performance debt score: {m['performance_debt_score']}")  # noqa: print
    print(
        f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n"
    )  # noqa: print
    print("🏷️  **Issue Categories:**")  # noqa: print
    for category, count in results["categories"].items():
        print(
            f"   - {category.replace('_', ' ').title()}: {count} issues"
        )  # noqa: print
    print()  # noqa: print


def _print_critical_and_high_issues(details: list) -> None:
    """Print critical and high-priority performance issues. Issue #1183."""
    critical = [i for i in details if i["severity"] == "critical"]
    if critical:
        print("🚨 **Critical Performance Issues:**")  # noqa: print
        for issue in critical[:10]:
            print(
                f"   - {issue['file']}:{issue['line']} - {issue['type']}"
            )  # noqa: print
            print(f"     💡 {issue['description']}")  # noqa: print
            print(f"     🔧 Suggestion: {issue['suggestion']}")  # noqa: print
            print()  # noqa: print
    high = [i for i in details if i["severity"] == "high"]
    if high:
        print("⚠️  **High Priority Performance Issues:**")  # noqa: print
        for issue in high[:5]:
            print(
                f"   - {issue['file']}:{issue['line']} - {issue['type']}"
            )  # noqa: print
            print(f"     {issue['description']}")  # noqa: print
        print()  # noqa: print


def _print_memory_blocking_db_issues(details: list) -> None:
    """Print memory leak, blocking call, and database issue breakdowns. Issue #1183."""
    memory = [i for i in details if i["type"] == "memory_leaks"]
    if memory:
        print("💾 **Memory Leak Analysis:**")  # noqa: print
        print(f"   Found {len(memory)} potential memory leaks:")  # noqa: print
        for issue in memory[:5]:
            snippet = (
                issue["code_snippet"].split()[0] if issue["code_snippet"] else "N/A"
            )
            print(f"   - {issue['file']}:{issue['line']}")  # noqa: print
            print(f"     Code: {snippet}")  # noqa: print
        print()  # noqa: print
    blocking = [i for i in details if i["type"] == "blocking_calls"]
    if blocking:
        print("🔒 **Blocking Call Analysis:**")  # noqa: print
        print(
            f"   Found {len(blocking)} blocking calls in async functions:"
        )  # noqa: print
        for issue in blocking[:5]:
            print(f"   - {issue['file']}:{issue['line']}")  # noqa: print
            print(f"     Function: {issue['function'] or 'N/A'}")  # noqa: print
        print()  # noqa: print
    db = [i for i in details if "database" in i["type"]]
    if db:
        print("🗄️  **Database Performance Issues:**")  # noqa: print
        print(f"   Found {len(db)} database-related performance issues:")  # noqa: print
        for issue in db[:3]:
            print(f"   - {issue['file']}:{issue['line']}")  # noqa: print
            print(f"     {issue['description']}")  # noqa: print
        print()  # noqa: print


async def analyze_performance_issues():
    """Analyze codebase for performance and memory issues"""
    print("🚀 Starting performance and memory leak analysis...")  # noqa: print
    analyzer = PerformanceAnalyzer()
    results = await analyzer.analyze_performance(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )
    _print_perf_summary(results)
    details = results["performance_details"]
    _print_critical_and_high_issues(details)
    _print_memory_blocking_db_issues(details)
    report_path = Path("performance_analysis_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"📋 Detailed report saved to: {report_path}")  # noqa: print
    await generate_performance_fixes(results)
    return results


def _print_common_fix_patterns() -> None:
    """Print 5 common performance fix code examples. Issue #1183."""
    print("🛠️  **Common Performance Patterns to Fix:**\n")  # noqa: print
    print("**1. Memory Leak Prevention:**\n```python")  # noqa: print
    print(
        "# ❌ Bad - Resource leak\nf = open('file.txt', 'r')\ndata = f.read()\n"
    )  # noqa: print
    print(
        "# ✅ Good - Proper resource management\nwith open('file.txt', 'r') as f:\n    data = f.read()\n```\n"
    )  # noqa: print
    print("**2. Async Function Optimization:**\n```python")  # noqa: print
    print(
        "# ❌ Bad - Blocking call in async function\nasync def fetch_data():\n    time.sleep(1)  # Blocks event loop\n    return requests.get(url)  # Blocking\n"
    )  # noqa: print
    print(
        "# ✅ Good - Non-blocking async operations\nasync def fetch_data():\n    await asyncio.sleep(1)\n    async with aiohttp.ClientSession() as session:\n        async with session.get(url) as response:\n            return await response.text()\n```\n"
    )  # noqa: print
    print("**3. Database Query Optimization:**\n```python")  # noqa: print
    print(
        "# ❌ Bad - N+1 query problem\nfor user in users:\n    profile = db.query(Profile).filter(Profile.user_id == user.id).first()\n"
    )  # noqa: print
    print(
        "# ✅ Good - Bulk query\nuser_ids = [user.id for user in users]\nprofiles = db.query(Profile).filter(Profile.user_id.in_(user_ids)).all()\nprofile_dict = {p.user_id: p for p in profiles}\n```\n"
    )  # noqa: print
    print("**4. Loop Performance Optimization:**\n```python")  # noqa: print
    print(
        "# ❌ Bad - Inefficient loop\nresult = ''\nfor item in large_list:\n    result += str(item)\n"
    )  # noqa: print
    print(
        "# ✅ Good - List comprehension and join\nresult = ''.join(str(item) for item in large_list)\n```\n"
    )  # noqa: print
    print("**5. Efficient Caching Patterns:**\n```python")  # noqa: print
    print(
        "# ❌ Bad - No caching\ndef get_user_data(user_id):\n    return expensive_database_query(user_id)\n"
    )  # noqa: print
    print(
        "# ✅ Good - Redis caching with TTL\nasync def get_user_data(user_id):\n    cache_key = f'user:{user_id}'\n    cached = await redis_client.get(cache_key)\n    if cached:\n        return json.loads(cached)\n    data = expensive_database_query(user_id)\n    await redis_client.setex(cache_key, 300, json.dumps(data))\n    return data\n```\n"
    )  # noqa: print


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
            for example in rec.get("code_examples", []):
                print("   \n   Before:\n   ```python")  # noqa: print
                print(f"   {example.get('before', 'N/A')}")  # noqa: print
                print("   ```\n   \n   After:\n   ```python")  # noqa: print
                print(f"   {example.get('after', 'N/A')}")  # noqa: print
                print("   ```")  # noqa: print
        print()  # noqa: print
    _print_common_fix_patterns()


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
