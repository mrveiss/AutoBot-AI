"""
Performance and Memory Leak Analyzer using Redis and NPU acceleration
Analyzes codebase for performance bottlenecks, memory leaks, and processing inefficiencies
"""

import ast
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.redis_client import get_redis_client
from config import UnifiedConfig

# Initialize unified config
config = UnifiedConfig()
logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for loop AST types
_LOOP_TYPES = (ast.For, ast.While)


@dataclass
class PerformanceIssue:
    """Represents a performance issue in the codebase"""

    file_path: str
    line_number: int
    function_name: Optional[str]
    issue_type: str  # memory_leak, blocking_call, inefficient_loop, etc.
    description: str
    severity: str  # critical, high, medium, low
    code_snippet: str
    suggestion: str
    estimated_impact: str  # high, medium, low


@dataclass
class PerformanceRecommendation:
    """Performance improvement recommendation"""

    category: str  # memory, async, loops, database, etc.
    title: str
    description: str
    affected_files: List[str]
    priority: str
    code_examples: List[Dict[str, str]]  # before/after examples


class PerformanceAnalyzer:
    """Analyzes code for performance issues and memory leaks"""

    @staticmethod
    def _build_performance_patterns() -> Dict[str, List[str]]:
        """Return the anti-pattern regex map used for performance scanning.

        Issue #1183: Extracted from __init__() to reduce function length.
        """
        return {
            "memory_leaks": [
                r"open\s*\([^)]+\)(?!\s*(?:with|\.close\(\)|as\s+))",
                r"subprocess\.Popen\([^)]+\)(?!\s*(?:\.wait\(\)|\.communicate\(\)|with\s+))",
                r"requests\.(?:get|post|put|delete)\([^)]+\)(?!\s*\.close\(\))",
                r"for\s+[^:]+:\s*\n\s*(?:.*\n)*?\s*[A-Z][a-zA-Z]+\([^)]*\)",
                r"(?:sqlite3|psycopg2|pymongo)\.connect\([^)]+\)(?!\s*(?:with|\.close\(\)|as\s+))",
            ],
            "blocking_calls": [
                r"async\s+def\s+[^:]+:(?:(?:\n|.)*?)(?:time\.sleep|requests\.|urllib\.)",
                r"async\s+def\s+[^:]+:(?:(?:\n|.)*?)subprocess\.(?:run|call|check_output)",
                r"(?:time\.sleep|threading\.Event\(\)\.wait)\s*\(\s*([1-9]\d*)\s*\)",
                r"\.join\(\s*(?:[1-9]\d*|None)\s*\)",
            ],
            "inefficient_loops": [
                r"for\s+[^:]+:\s*\n(?:\s*.*\n)*?\s*for\s+[^:]+:\s*\n(?:\s*.*\n)*?\s*for\s+",
                r'for\s+[^:]+:\s*\n(?:\s*.*\n)*?\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\+=\s*[\'"]',
                r"for\s+[^:]+:\s*\n(?:\s*.*\n)*?\s*[a-zA-Z_][a-zA-Z0-9_]*\.append\(",
                r'for\s+[^:]+:\s*\n(?:\s*.*\n)*?\s*[a-zA-Z_][a-zA-Z0-9_]*\[[\'"][^\'"]*[\'"]\]',
            ],
            "database_issues": [
                r"for\s+[^:]+:\s*\n(?:\s*.*\n)*?\s*(?:cursor\.execute|session\.query|\.filter)",
                r"(?:sqlite3|psycopg2|pymongo)\.connect\([^)]+\)(?!\s*(?:pool|Pool))",
                r"SELECT\s+\*\s+FROM\s+\w+(?!\s+(?:WHERE|LIMIT))",
                r'WHERE\s+[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*[?\'"]\w+[?\'"](?!\s*(?:INDEX|index))',
            ],
            "concurrency_issues": [
                r"(?:threading\.Thread|multiprocessing\.Process)\([^)]*\)(?!\s*\.join\(\))",
                r"(?:global\s+|self\.)[a-zA-Z_][a-zA-Z0-9_]*\s*(?:\+=|\-=|\*=|\/=)",
                r"async\s+def\s+[^:]+:(?:(?:\n|.)*?)[a-zA-Z_][a-zA-Z0-9_]*\([^)]*\)(?!\s*(?:await|\.result\(\)))",
            ],
            "resource_waste": [
                r"(?:logging|logger|log)\.\w+\([^)]*\).*(?:logging|logger|log)\.\w+\([^)]*\)",
                r"(?:len|max|min|sum)\([^)]+\).*(?:len|max|min|sum)\(\1\)",
                r"[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*[^=\n]+(?:\n(?!.*\1).*)*$",
                r"\.read\(\)(?!\s*(?:\.decode|\.split|\.strip))",
            ],
        }

    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Caching keys
        self.PERFORMANCE_KEY = "perf_analysis:issues"
        self.RECOMMENDATIONS_KEY = "perf_analysis:recommendations"

        # Issue #1183: Delegate pattern dict to extracted static method
        self.performance_patterns = self._build_performance_patterns()

        logger.info("Performance Analyzer initialized")

    async def analyze_performance(
        self, root_path: str = ".", patterns: List[str] = None
    ) -> Dict[str, Any]:
        """Analyze codebase for performance issues"""

        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Scanning for performance issues in {root_path}")
        performance_issues = await self._scan_for_performance_issues(
            root_path, patterns
        )
        logger.info(f"Found {len(performance_issues)} potential performance issues")

        # Analyze AST for complex patterns
        logger.info("Performing AST-based performance analysis")
        ast_issues = await self._ast_performance_analysis(root_path, patterns)
        performance_issues.extend(ast_issues)

        # Categorize and prioritize findings
        logger.info("Categorizing and prioritizing issues")
        categorized = await self._categorize_issues(performance_issues)

        # Generate optimization recommendations
        logger.info("Generating optimization recommendations")
        recommendations = await self._generate_optimization_recommendations(categorized)

        # Calculate performance metrics
        metrics = self._calculate_performance_metrics(
            performance_issues, recommendations
        )

        analysis_time = time.time() - start_time

        results = {
            "total_performance_issues": len(performance_issues),
            "categories": {cat: len(issues) for cat, issues in categorized.items()},
            "critical_issues": len(
                [i for i in performance_issues if i.severity == "critical"]
            ),
            "high_priority_issues": len(
                [i for i in performance_issues if i.severity == "high"]
            ),
            "recommendations_count": len(recommendations),
            "analysis_time_seconds": analysis_time,
            "performance_details": [
                self._serialize_performance_issue(i) for i in performance_issues
            ],
            "optimization_recommendations": [
                self._serialize_recommendation(r) for r in recommendations
            ],
            "metrics": metrics,
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Performance analysis complete in {analysis_time:.2f}s")
        return results

    async def _scan_for_performance_issues(
        self, root_path: str, patterns: List[str]
    ) -> List[PerformanceIssue]:
        """Scan files for performance anti-patterns"""

        issues = []
        root = Path(root_path)

        for pattern in patterns:
            pattern_issues = await self._scan_pattern_files(
                root, pattern
            )  # (Issue #315 - extracted)
            issues.extend(pattern_issues)

        return issues

    async def _scan_pattern_files(
        self, root: Path, pattern: str
    ) -> List[PerformanceIssue]:
        """Scan all files matching a pattern (Issue #315 - extracted)"""
        issues = []

        for file_path in root.glob(pattern):
            # Guard clause - skip non-files or files that should be skipped
            if not file_path.is_file() or self._should_skip_file(file_path):
                continue

            try:
                file_issues = await self._scan_file_for_performance_issues(
                    str(file_path)
                )
                issues.extend(file_issues)
            except Exception as e:
                logger.warning(f"Failed to scan {file_path}: {e}")

        return issues

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        skip_patterns = [
            "__pycache__",
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "test_",
            "_test.py",
            ".pyc",
            "env_analysis",
            "performance_analyzer",
            "analyze_",
        ]

        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)

    async def _scan_file_for_performance_issues(
        self, file_path: str
    ) -> List[PerformanceIssue]:
        """Scan a single file for performance issues"""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            return self._scan_file_content_for_patterns(
                file_path, content, lines
            )  # (Issue #315 - extracted)

        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")
            return []

    def _scan_file_content_for_patterns(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """Scan file content for performance patterns (Issue #315 - extracted)"""
        issues = []

        for category, pattern_list in self.performance_patterns.items():
            category_issues = self._scan_category_patterns(
                file_path, content, lines, category, pattern_list
            )
            issues.extend(category_issues)

        return issues

    def _scan_category_patterns(
        self,
        file_path: str,
        content: str,
        lines: List[str],
        category: str,
        pattern_list: List[str],
    ) -> List[PerformanceIssue]:
        """Scan a single category's patterns (Issue #315 - extracted)"""
        issues = []

        for pattern in pattern_list:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1

                issue = self._create_performance_issue(
                    file_path, line_num, match.group(0), category, lines
                )
                if issue:
                    issues.append(issue)

        return issues

    async def _ast_performance_analysis(
        self, root_path: str, patterns: List[str]
    ) -> List[PerformanceIssue]:
        """Perform AST-based performance analysis"""

        issues = []
        root = Path(root_path)

        for pattern in patterns:
            pattern_issues = await self._analyze_ast_pattern_files(
                root, pattern
            )  # (Issue #315 - extracted)
            issues.extend(pattern_issues)

        return issues

    async def _analyze_ast_pattern_files(
        self, root: Path, pattern: str
    ) -> List[PerformanceIssue]:
        """Analyze AST for all files matching a pattern (Issue #315 - extracted)"""
        issues = []

        for file_path in root.glob(pattern):
            # Guard clause - skip non-files or files that should be skipped
            if not file_path.is_file() or self._should_skip_file(file_path):
                continue

            try:
                file_issues = await self._analyze_ast_performance(str(file_path))
                issues.extend(file_issues)
            except Exception as e:
                logger.warning(f"Failed to analyze AST for {file_path}: {e}")

        return issues

    async def _analyze_ast_performance(self, file_path: str) -> List[PerformanceIssue]:
        """Analyze AST for performance patterns"""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            tree = ast.parse(content, filename=file_path)
            return self._walk_ast_nodes(
                tree, file_path, lines
            )  # (Issue #315 - extracted)

        except SyntaxError:
            # Skip files with syntax errors
            return []
        except Exception as e:
            logger.error(f"AST analysis error for {file_path}: {e}")
            return []

    def _walk_ast_nodes(
        self, tree: ast.AST, file_path: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """Walk AST nodes and analyze for performance issues (Issue #315 - extracted)"""
        issues = []

        for node in ast.walk(tree):
            node_issues = self._analyze_ast_node(
                node, file_path, lines
            )  # (Issue #315 - extracted)
            issues.extend(node_issues)

        return issues

    def _analyze_ast_node(
        self, node: ast.AST, file_path: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """Analyze a single AST node for performance patterns (Issue #315 - extracted)"""
        # Detect potential memory leaks
        if isinstance(node, ast.With):
            # Check for proper resource management
            return []

        # Detect inefficient loops
        if isinstance(node, ast.For):
            issue = self._analyze_loop_efficiency(node, file_path, lines)
            return [issue] if issue else []

        # Detect blocking calls in async functions
        if isinstance(node, ast.AsyncFunctionDef):
            return self._analyze_async_function(node, file_path, lines)

        # Detect database query patterns
        if isinstance(node, ast.Call):
            db_issue = self._analyze_database_call(node, file_path, lines)
            return [db_issue] if db_issue else []

        return []

    def _analyze_loop_efficiency(
        self, node: ast.For, file_path: str, lines: List[str]
    ) -> Optional[PerformanceIssue]:
        """Analyze loop for efficiency issues"""

        # Check for nested loops (potential O(n²) or worse)
        nested_loops = 0
        for child in ast.walk(node):
            # Issue #380: Use module-level constant
            if isinstance(child, _LOOP_TYPES) and child != node:
                nested_loops += 1

        if nested_loops >= 2:
            return PerformanceIssue(
                file_path=file_path,
                line_number=node.lineno,
                function_name=self._get_containing_function(node),
                issue_type="inefficient_loop",
                description=f"Deeply nested loop (depth {nested_loops + 1}) - potential O(n^{nested_loops + 1}) complexity",
                severity="high" if nested_loops >= 3 else "medium",
                code_snippet=self._get_code_snippet(lines, node.lineno, 5),
                suggestion="Consider using list comprehensions, vectorized operations, or algorithm optimization",
                estimated_impact="high",
            )

        return None

    def _analyze_async_function(
        self, node: ast.AsyncFunctionDef, file_path: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """Analyze async function for blocking operations"""

        issues = []
        blocking_calls = [
            "time.sleep",
            "requests.",
            "subprocess.run",
            "input(",
            "urllib.",
        ]

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child)

                for blocking_pattern in blocking_calls:
                    if blocking_pattern in call_name:
                        issues.append(
                            PerformanceIssue(
                                file_path=file_path,
                                line_number=child.lineno,
                                function_name=node.name,
                                issue_type="blocking_call",
                                description=f"Blocking call '{call_name}' in async function '{node.name}'",
                                severity="critical",
                                code_snippet=self._get_code_snippet(
                                    lines, child.lineno, 3
                                ),
                                suggestion="Use async equivalent: asyncio.sleep, aiohttp, asyncio.subprocess, etc.",
                                estimated_impact="high",
                            )
                        )

        return issues

    def _analyze_database_call(
        self, node: ast.Call, file_path: str, lines: List[str]
    ) -> Optional[PerformanceIssue]:
        """Analyze database calls for efficiency"""

        call_name = self._get_call_name(node)

        # Check for potential N+1 queries
        if any(
            db_pattern in call_name
            for db_pattern in ["execute", "query", "filter", "get"]
        ):
            # This is a simplified check - in practice, you'd need more context
            if self._is_in_loop_context(node):
                return PerformanceIssue(
                    file_path=file_path,
                    line_number=node.lineno,
                    function_name=self._get_containing_function(node),
                    issue_type="database_n_plus_one",
                    description=f"Potential N+1 query pattern: '{call_name}' in loop",
                    severity="high",
                    code_snippet=self._get_code_snippet(lines, node.lineno, 3),
                    suggestion="Use bulk operations, joins, or prefetch_related to reduce queries",
                    estimated_impact="high",
                )

        return None

    def _create_performance_issue(
        self,
        file_path: str,
        line_num: int,
        code_match: str,
        category: str,
        lines: List[str],
    ) -> Optional[PerformanceIssue]:
        """Create a PerformanceIssue object"""

        # Get context
        snippet = self._get_code_snippet(lines, line_num, 3)

        # Skip false positives
        if self._is_false_positive(code_match, snippet, category):
            return None

        # Determine severity and description
        severity, description, suggestion = self._classify_performance_issue(
            code_match, category, snippet
        )

        return PerformanceIssue(
            file_path=file_path,
            line_number=line_num,
            function_name=None,  # Would need AST analysis to determine
            issue_type=category,
            description=description,
            severity=severity,
            code_snippet=snippet,
            suggestion=suggestion,
            estimated_impact=severity,
        )

    def _classify_performance_issue(
        self, code_match: str, category: str, context: str
    ) -> Tuple[str, str, str]:
        """Classify performance issue severity and provide description/suggestion"""

        classifications = {
            "memory_leaks": {
                "severity": (
                    "critical"
                    if any(leak in code_match for leak in ["open(", "Popen("])
                    else "high"
                ),
                "description": f"Potential memory leak: {category}",
                "suggestion": "Use context managers (with statements) or ensure proper resource cleanup",
            },
            "blocking_calls": {
                "severity": "critical",
                "description": f"Blocking call in async context: {code_match[:50]}",
                "suggestion": "Replace with async equivalent or use asyncio.run_in_executor()",
            },
            "inefficient_loops": {
                "severity": "medium",
                "description": "Inefficient loop pattern detected",
                "suggestion": "Consider list comprehensions, vectorization, or algorithm optimization",
            },
            "database_issues": {
                "severity": "high",
                "description": "Database efficiency issue",
                "suggestion": "Use connection pooling, bulk operations, and proper indexing",
            },
            "concurrency_issues": {
                "severity": "high",
                "description": "Potential race condition or concurrency issue",
                "suggestion": "Add proper synchronization (locks, queues) or use async patterns",
            },
            "resource_waste": {
                "severity": "low",
                "description": "Resource waste detected",
                "suggestion": "Optimize resource usage and eliminate redundant operations",
            },
        }

        info = classifications.get(
            category,
            {
                "severity": "medium",
                "description": f"Performance issue in category: {category}",
                "suggestion": "Review and optimize this code section",
            },
        )

        return info["severity"], info["description"], info["suggestion"]

    def _is_false_positive(self, code_match: str, context: str, category: str) -> bool:
        """Check if this is likely a false positive"""

        # Skip comments and docstrings
        context_clean = context.strip()
        if context_clean.startswith("#") or '"""' in context or "'''" in context:
            return True

        # Skip test files and examples
        if any(word in context.lower() for word in ["test", "example", "demo", "mock"]):
            return True

        return False

    def _get_code_snippet(
        self, lines: List[str], line_num: int, context_lines: int = 2
    ) -> str:
        """Get code snippet with context"""
        start = max(0, line_num - context_lines - 1)
        end = min(len(lines), line_num + context_lines)
        return "\n".join(lines[start:end])

    def _get_call_name(self, node: ast.Call) -> str:
        """Get the name of a function call"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return f"{self._get_call_name(node.func.value)}.{node.func.attr}"
        else:
            return str(node.func)

    def _get_containing_function(self, node: ast.AST) -> Optional[str]:
        """Get the name of the function containing this node"""
        # This would require maintaining parent references in AST
        # Simplified implementation
        return None

    def _is_in_loop_context(self, node: ast.AST) -> bool:
        """Check if node is inside a loop"""
        # This would require parent node tracking
        # Simplified implementation
        return False

    async def _categorize_issues(
        self, performance_issues: List[PerformanceIssue]
    ) -> Dict[str, List[PerformanceIssue]]:
        """Categorize performance issues"""

        categories = {}
        for issue in performance_issues:
            if issue.issue_type not in categories:
                categories[issue.issue_type] = []
            categories[issue.issue_type].append(issue)

        return categories

    async def _generate_optimization_recommendations(
        self, categorized: Dict[str, List[PerformanceIssue]]
    ) -> List[PerformanceRecommendation]:
        """Generate optimization recommendations"""

        recommendations = []

        for category, issues in categorized.items():
            if not issues:
                continue

            # Group similar issues
            high_impact = [i for i in issues if i.severity in ["critical", "high"]]

            if high_impact:
                recommendation = PerformanceRecommendation(
                    category=category,
                    title=f"Optimize {category.replace('_', ' ').title()}",
                    description=f"Found {len(high_impact)} high-impact {category} issues",
                    affected_files=list(set(i.file_path for i in high_impact)),
                    priority="high" if len(high_impact) > 5 else "medium",
                    code_examples=self._generate_code_examples(
                        category, high_impact[:3]
                    ),
                )
                recommendations.append(recommendation)

        return recommendations

    def _generate_code_examples(
        self, category: str, issues: List[PerformanceIssue]
    ) -> List[Dict[str, str]]:
        """Generate before/after code examples"""

        examples = []

        example_templates = {
            "memory_leaks": {
                "before": 'f = open("file.txt", "r", encoding="utf-8")\ndata = f.read()',
                "after": 'with open("file.txt", "r", encoding="utf-8") as f:\n    data = f.read()',
            },
            "blocking_calls": {
                "before": "async def func():\n    time.sleep(1)",
                "after": "async def func():\n    await asyncio.sleep(1)",
            },
            "inefficient_loops": {
                "before": "result = []\nfor item in items:\n    if condition(item):\n        result.append(transform(item))",
                "after": "result = [transform(item) for item in items if condition(item)]",
            },
            "database_issues": {
                "before": "for user in users:\n    profile = db.get_profile(user.id)",
                "after": "profiles = db.get_profiles_bulk([u.id for u in users])",
            },
        }

        template = example_templates.get(category)
        if template:
            examples.append(template)

        return examples

    def _calculate_performance_metrics(
        self,
        issues: List[PerformanceIssue],
        recommendations: List[PerformanceRecommendation],
    ) -> Dict[str, Any]:
        """Calculate performance analysis metrics"""

        severity_counts = {
            "critical": len([i for i in issues if i.severity == "critical"]),
            "high": len([i for i in issues if i.severity == "high"]),
            "medium": len([i for i in issues if i.severity == "medium"]),
            "low": len([i for i in issues if i.severity == "low"]),
        }

        category_counts = {}
        for issue in issues:
            category_counts[issue.issue_type] = (
                category_counts.get(issue.issue_type, 0) + 1
            )

        file_counts = len(set(i.file_path for i in issues))

        return {
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "files_with_issues": file_counts,
            "optimization_potential": len(recommendations),
            "critical_memory_issues": severity_counts["critical"],
            "blocking_call_count": category_counts.get("blocking_calls", 0),
            "performance_debt_score": self._calculate_debt_score(severity_counts),
        }

    def _calculate_debt_score(self, severity_counts: Dict[str, int]) -> int:
        """Calculate technical debt score for performance"""
        weights = {"critical": 10, "high": 5, "medium": 2, "low": 1}
        return sum(
            count * weights[severity] for severity, count in severity_counts.items()
        )

    def _serialize_performance_issue(self, issue: PerformanceIssue) -> Dict[str, Any]:
        """Serialize performance issue for output"""
        return {
            "file": issue.file_path,
            "line": issue.line_number,
            "function": issue.function_name,
            "type": issue.issue_type,
            "description": issue.description,
            "severity": issue.severity,
            "suggestion": issue.suggestion,
            "impact": issue.estimated_impact,
            "code_snippet": issue.code_snippet,
        }

    def _serialize_recommendation(
        self, rec: PerformanceRecommendation
    ) -> Dict[str, Any]:
        """Serialize recommendation for output"""
        return {
            "category": rec.category,
            "title": rec.title,
            "description": rec.description,
            "affected_files": rec.affected_files,
            "priority": rec.priority,
            "code_examples": rec.code_examples,
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.PERFORMANCE_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, 3600, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self):
        """Clear analysis cache"""
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="perf_analysis:*", count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")


async def main():
    """Example usage of performance analyzer"""

    analyzer = PerformanceAnalyzer()

    # Analyze the codebase for performance issues
    results = await analyzer.analyze_performance(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Print summary
    print("\n=== Performance Analysis Results ===")  # noqa: print
    print(  # noqa: print
        f"Total performance issues: {results['total_performance_issues']}"
    )  # noqa: print
    print(f"Critical issues: {results['critical_issues']}")  # noqa: print
    print(f"High priority issues: {results['high_priority_issues']}")  # noqa: print
    print(  # noqa: print
        f"Optimization recommendations: {results['recommendations_count']}"
    )  # noqa: print
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")  # noqa: print

    # Print category breakdown
    print("\n=== Issue Categories ===")  # noqa: print
    for category, count in results["categories"].items():
        print(f"{category}: {count}")  # noqa: print

    # Print top critical issues
    print("\n=== Critical Performance Issues ===")  # noqa: print
    critical_issues = [
        i for i in results["performance_details"] if i["severity"] == "critical"
    ]
    for i, issue in enumerate(critical_issues[:5], 1):
        print(  # noqa: print
            f"\n{i}. {issue['type']} in {issue['file']}:{issue['line']}"
        )  # noqa: print
        print(f"   Description: {issue['description']}")  # noqa: print
        print(f"   Suggestion: {issue['suggestion']}")  # noqa: print

    # Print optimization recommendations
    print("\n=== Optimization Recommendations ===")  # noqa: print
    for i, rec in enumerate(results["optimization_recommendations"][:3], 1):
        print(f"\n{i}. {rec['title']} ({rec['priority']} priority)")  # noqa: print
        print(f"   {rec['description']}")  # noqa: print
        print(f"   Files affected: {len(rec['affected_files'])}")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
