#!/usr/bin/env python3
"""
Simple performance analysis focusing on critical patterns
"""

import re
from pathlib import Path
from typing import Any, Dict, List


class SimplePerformanceAnalyzer:
    """Simple and fast performance analyzer"""

    def __init__(self):
        # Critical patterns only
        self.patterns = {
            "memory_leaks": [
                (
                    r"open\s*\([^)]+\)(?!\s*(?:with|\.close\(\)|as\s+))",
                    "Unclosed file handle",
                ),
                (
                    r"requests\.[a-z]+\([^)]+\)(?!\s*\.close\(\))",
                    "Unclosed HTTP connection",
                ),
            ],
            "blocking_calls": [
                (
                    r"async\s+def\s+[^:]+:.*?time\.sleep\s*\(",
                    "time.sleep in async function",
                ),
                (
                    r"async\s+def\s+[^:]+:.*?requests\.[a-z]+\s*\(",
                    "requests in async function",
                ),
            ],
            "inefficient_loops": [
                (
                    r"for\s+[^:]+:\s*\n\s*for\s+[^:]+:\s*\n\s*for\s+",
                    "Triple nested loop",
                ),
                (r'for\s+[^:]+:.*?\+=\s*[\'"]', "String concatenation in loop"),
            ],
            "database_issues": [
                (r"for\s+[^:]+:.*?\.execute\s*\(", "Query in loop (N+1 problem)"),
                (
                    r"SELECT\s+\*\s+FROM\s+\w+(?!\s+(?:WHERE|LIMIT))",
                    "Unbounded SELECT *",
                ),
            ],
        }

        # Issue #510: Precompile and combine patterns per category at init time
        # Reduces per-file work from O(categories * patterns) to O(categories)
        self._compiled_patterns = {}
        for category, pattern_list in self.patterns.items():
            # Build combined pattern with named groups for description lookup
            combined_parts = []
            self._pattern_descriptions = {}
            for i, (pattern, description) in enumerate(pattern_list):
                group_name = f"{category}_{i}"
                combined_parts.append(f"(?P<{group_name}>{pattern})")
                self._pattern_descriptions[group_name] = description
            combined = "|".join(combined_parts)
            self._compiled_patterns[category] = re.compile(
                combined, re.MULTILINE | re.DOTALL
            )

    def analyze_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Analyze single file for performance issues.

        Issue #510: Optimized O(n³) → O(n²) by using precompiled combined patterns.
        Now iterates: categories × (single regex per category) instead of
        categories × patterns × matches.
        """

        if not file_path.suffix == ".py" or "test" in str(file_path):
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return []

        issues = []
        lines = content.splitlines()

        # Issue #510: Use precompiled combined patterns
        for category, compiled in self._compiled_patterns.items():
            try:
                for match in compiled.finditer(content):
                    line_num = content[: match.start()].count("\n") + 1
                    # Find which pattern matched using lastgroup
                    group_name = match.lastgroup
                    description = self._pattern_descriptions.get(
                        group_name, "Performance issue"
                    )

                    # Get context
                    context = lines[line_num - 1] if line_num <= len(lines) else ""

                    # Skip comments and obvious false positives
                    if "#" in context or "test" in context.lower():
                        continue

                    issues.append(
                        {
                            "file": str(file_path),
                            "line": line_num,
                            "category": category,
                            "description": description,
                            "context": context.strip(),
                            "severity": self._get_severity(category),
                        }
                    )
            except re.error:
                continue

        return issues

    def _get_severity(self, category: str) -> str:
        """Get severity for category"""
        severity_map = {
            "memory_leaks": "critical",
            "blocking_calls": "critical",
            "database_issues": "high",
            "inefficient_loops": "medium",
        }
        return severity_map.get(category, "low")

    def analyze_directory(self, root_path: str = ".") -> Dict[str, Any]:
        """Analyze directory for performance issues"""

        all_issues = []
        python_files = list(Path(root_path).rglob("*.py"))

        # Skip certain directories
        python_files = [
            f
            for f in python_files
            if not any(
                skip in str(f) for skip in ["venv", "__pycache__", ".git", "test_"]
            )
        ]

        print(f"Analyzing {len(python_files)} Python files...")  # noqa: print

        for file_path in python_files:
            issues = self.analyze_file(file_path)
            all_issues.extend(issues)

        # Categorize results
        by_category = {}
        by_severity = {}

        for issue in all_issues:
            category = issue["category"]
            severity = issue["severity"]

            if category not in by_category:
                by_category[category] = []
            by_category[category].append(issue)

            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(issue)

        return {
            "total_issues": len(all_issues),
            "by_category": by_category,
            "by_severity": by_severity,
            "files_analyzed": len(python_files),
            "all_issues": all_issues,
        }


def _print_severity_and_category(results: dict) -> None:
    """Print issues grouped by severity and category. Issue #1183."""
    print("\n=== Issues by Severity ===")  # noqa: print
    for severity in ["critical", "high", "medium", "low"]:
        if severity in results["by_severity"]:
            print(
                f"{severity.title()}: {len(results['by_severity'][severity])} issues"
            )  # noqa: print
    print("\n=== Issues by Category ===")  # noqa: print
    for category, issues in results["by_category"].items():
        print(
            f"{category.replace('_', ' ').title()}: {len(issues)} issues"
        )  # noqa: print


def _print_issues_and_recommendations(results: dict) -> None:
    """Print critical/DB issues and optimization recommendations. Issue #1183."""
    if "critical" in results["by_severity"]:
        print("\n🚨 Critical Issues (Memory Leaks & Blocking Calls):")  # noqa: print
        for issue in results["by_severity"]["critical"][:10]:
            print(f"  - {issue['file']}:{issue['line']}")  # noqa: print
            print(f"    {issue['description']}")  # noqa: print
            print(f"    Code: {issue['context']}")  # noqa: print
            print()  # noqa: print
    if "database_issues" in results["by_category"]:
        print("🗄️ Database Performance Issues:")  # noqa: print
        for issue in results["by_category"]["database_issues"][:5]:
            print(f"  - {issue['file']}:{issue['line']}")  # noqa: print
            print(f"    {issue['description']}")  # noqa: print
            print()  # noqa: print
    print("\n=== Optimization Recommendations ===")  # noqa: print
    cats = results["by_category"]
    if "memory_leaks" in cats:
        print(
            f"1. Fix {len(cats['memory_leaks'])} memory leaks by using 'with' statements"
        )  # noqa: print
    if "blocking_calls" in cats:
        print(
            f"2. Replace {len(cats['blocking_calls'])} blocking calls with async equivalents"
        )  # noqa: print
    if "database_issues" in cats:
        print(
            f"3. Optimize {len(cats['database_issues'])} database operations to avoid N+1 queries"
        )  # noqa: print
    if "inefficient_loops" in cats:
        print(
            f"4. Refactor {len(cats['inefficient_loops'])} inefficient loops using list comprehensions"
        )  # noqa: print
    print("\n=== Quick Fixes ===")  # noqa: print
    print("Replace: time.sleep() → await asyncio.sleep()")  # noqa: print
    print(
        "Replace: requests.get() → async with aiohttp.ClientSession():"
    )  # noqa: print
    print("Replace: open() → with open() as f:")  # noqa: print
    print("Replace: for...+=string → ''.join(list)")  # noqa: print


def main():
    """Run simple performance analysis"""
    print("🚀 Running simple performance analysis...")  # noqa: print
    analyzer = SimplePerformanceAnalyzer()
    results = analyzer.analyze_directory(".")
    print(f"\n=== Performance Analysis Results ===")  # noqa: print
    print(f"Files analyzed: {results['files_analyzed']}")  # noqa: print
    print(f"Total issues found: {results['total_issues']}")  # noqa: print
    _print_severity_and_category(results)
    _print_issues_and_recommendations(results)


if __name__ == "__main__":
    main()
