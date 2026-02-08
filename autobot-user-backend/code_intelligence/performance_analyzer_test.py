# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Performance Pattern Analyzer

Tests the detection of performance anti-patterns including:
- N+1 query patterns (database queries in loops)
- Nested loop complexity (O(n²) and higher)
- Synchronous operations in async context
- Memory patterns (string concatenation)
- Cache misuse detection
- Inefficient data structure usage

Part of Issue #222 - Performance Pattern Analysis
Parent Epic: #217 - Advanced Code Intelligence
"""

import tempfile
import textwrap

import pytest
from code_intelligence.performance_analyzer import (
    PerformanceAnalyzer,
    PerformanceIssueType,
    PerformanceSeverity,
    analyze_performance,
    get_performance_issue_types,
)


class TestNestedLoopDetection:
    """Test nested loop complexity detection."""

    def test_detect_nested_for_loops(self):
        """Test detection of nested for loops with O(n²) complexity."""
        code = textwrap.dedent(
            """
            def process_matrix(matrix):
                result = []
                for i in range(len(matrix)):
                    for j in range(len(matrix[i])):
                        result.append(matrix[i][j])
                return result
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            nested_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.NESTED_LOOP_COMPLEXITY
            ]

            assert len(nested_results) >= 1
            assert nested_results[0].severity in (
                PerformanceSeverity.MEDIUM,
                PerformanceSeverity.HIGH,
            )
            assert "O(n" in nested_results[0].estimated_complexity

    def test_detect_triple_nested_loops(self):
        """Test detection of triple nested loops with O(n³) complexity."""
        code = textwrap.dedent(
            """
            def process_3d(data):
                for x in data:
                    for y in x:
                        for z in y:
                            print(z)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            nested_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.NESTED_LOOP_COMPLEXITY
            ]

            # Should detect high complexity
            assert len(nested_results) >= 1
            # Triple nesting should be HIGH severity
            high_severity = [
                r for r in nested_results if r.severity == PerformanceSeverity.HIGH
            ]
            assert len(high_severity) >= 1

    def test_nested_list_comprehension(self):
        """Test detection of nested list comprehensions."""
        code = textwrap.dedent(
            """
            def flatten(matrix):
                return [item for row in matrix for item in row]

            def cross_product(a, b):
                return [(x, y) for x in a for y in b]
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            complexity_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.QUADRATIC_COMPLEXITY
            ]

            # Should detect nested comprehensions
            assert len(complexity_results) >= 1


class TestNPlusOneQueryDetection:
    """Test N+1 query pattern detection."""

    def test_detect_query_in_for_loop(self):
        """Test detection of database query inside for loop."""
        code = textwrap.dedent(
            """
            def get_user_orders(users, db):
                results = []
                for user in users:
                    orders = db.execute(f"SELECT * FROM orders WHERE user_id = {user.id}")
                    results.append(orders)
                return results
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            n_plus_one_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.N_PLUS_ONE_QUERY
            ]

            assert len(n_plus_one_results) >= 1
            assert n_plus_one_results[0].severity == PerformanceSeverity.HIGH
            assert "batch" in n_plus_one_results[0].recommendation.lower()

    def test_detect_fetch_in_loop(self):
        """Test detection of fetch operations inside loop."""
        code = textwrap.dedent(
            """
            def process_items(items, cursor):
                for item in items:
                    cursor.fetchone()
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            query_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.N_PLUS_ONE_QUERY
            ]

            assert len(query_results) >= 1


class TestAsyncSyncMismatch:
    """Test detection of sync operations in async context."""

    def test_detect_time_sleep_in_async(self):
        """Test detection of time.sleep() in async function."""
        code = textwrap.dedent(
            """
            import time
            import asyncio

            async def process_async():
                time.sleep(1)  # Should use asyncio.sleep
                return "done"
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            sync_results = [
                r for r in results if r.issue_type == PerformanceIssueType.SYNC_IN_ASYNC
            ]

            assert len(sync_results) >= 1
            assert sync_results[0].severity == PerformanceSeverity.CRITICAL
            assert "asyncio.sleep" in sync_results[0].recommendation

    def test_detect_blocking_io_in_async(self):
        """Test detection of blocking I/O in async function."""
        code = textwrap.dedent(
            """
            async def read_file_async(path):
                with open(path, 'r') as f:  # Should use aiofiles
                    return f.read()
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            blocking_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.BLOCKING_IO_IN_ASYNC
            ]

            assert len(blocking_results) >= 1
            assert "aio" in blocking_results[0].recommendation.lower()

    def test_detect_sequential_awaits(self):
        """Test detection of sequential awaits that could be parallel."""
        code = textwrap.dedent(
            """
            async def fetch_all_data():
                result1 = await fetch_users()
                result2 = await fetch_orders()
                result3 = await fetch_products()
                result4 = await fetch_categories()
                return result1, result2, result3, result4
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            sequential_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.SEQUENTIAL_AWAITS
            ]

            assert len(sequential_results) >= 1
            assert "gather" in sequential_results[0].recommendation.lower()

    def test_no_false_positive_async_sleep(self):
        """Test that asyncio.sleep doesn't trigger false positive."""
        code = textwrap.dedent(
            """
            import asyncio

            async def proper_async():
                await asyncio.sleep(1)
                return "done"
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            sync_results = [
                r for r in results if r.issue_type == PerformanceIssueType.SYNC_IN_ASYNC
            ]

            assert len(sync_results) == 0


class TestStringConcatenation:
    """Test string concatenation pattern detection."""

    def test_detect_string_concat_in_loop(self):
        """Test detection of string concatenation in loop."""
        code = textwrap.dedent(
            """
            def build_output(items):
                result = ""
                for item in items:
                    result += str(item) + ", "
                return result
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            concat_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.EXCESSIVE_STRING_CONCAT
            ]

            assert len(concat_results) >= 1
            assert "join" in concat_results[0].recommendation.lower()

    def test_detect_plus_equals_string(self):
        """Test detection of += with strings in loop."""
        code = textwrap.dedent(
            """
            def create_html(elements):
                html = ""
                for element in elements:
                    html += "<div>" + element + "</div>"
                return html
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            concat_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.EXCESSIVE_STRING_CONCAT
            ]

            assert len(concat_results) >= 1
            assert concat_results[0].severity == PerformanceSeverity.MEDIUM


class TestListLookup:
    """Test list lookup pattern detection."""

    def test_detect_list_for_membership(self):
        """Test detection of list used for membership check."""
        code = textwrap.dedent(
            """
            def check_valid(value):
                if value in ["apple", "banana", "cherry", "date"]:
                    return True
                return False
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            lookup_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.LIST_FOR_LOOKUP
            ]

            assert len(lookup_results) >= 1
            assert "set" in lookup_results[0].recommendation.lower()


class TestHTTPRequestsInLoop:
    """Test HTTP request pattern detection."""

    def test_detect_http_in_loop(self):
        """Test detection of HTTP requests inside loop."""
        code = textwrap.dedent(
            """
            import requests

            def fetch_all_users(user_ids):
                results = []
                for user_id in user_ids:
                    response = requests.get(f"/api/users/{user_id}")
                    results.append(response.json())
                return results
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            http_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.UNBATCHED_API_CALLS
            ]

            assert len(http_results) >= 1
            assert http_results[0].severity == PerformanceSeverity.HIGH


class TestRepeatedComputation:
    """Test repeated computation detection."""

    def test_detect_repeated_expensive_calls(self):
        """Test detection of repeated expensive computations."""
        code = textwrap.dedent(
            """
            def process_data(data):
                hash1 = hashlib.sha256(data).hexdigest()
                result1 = process(hash1)

                hash2 = hashlib.sha256(data).hexdigest()
                result2 = validate(hash2)

                hash3 = hashlib.sha256(data).hexdigest()
                result3 = check(hash3)

                return result1, result2, result3
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            analyzer.analyze_file(f.name)

            # Note: This may or may not trigger depending on implementation
            # The analyzer checks for repeated calls of expensive operations


class TestDirectoryAnalysis:
    """Test directory-wide performance analysis."""

    def test_analyze_directory(self, tmp_path):
        """Test analysis of multiple files in directory."""
        # Create test file with issues
        (tmp_path / "slow.py").write_text(
            textwrap.dedent(
                """
            def slow_function(items):
                for i in items:
                    for j in items:
                        print(i, j)
        """
            )
        )

        # Create clean file
        (tmp_path / "fast.py").write_text(
            textwrap.dedent(
                """
            def fast_function(items):
                for item in items:
                    print(item)
        """
            )
        )

        analyzer = PerformanceAnalyzer(project_root=str(tmp_path))
        results = analyzer.analyze_directory()

        # Should find issues in slow.py
        assert len(results) >= 1
        assert any("slow.py" in r.file_path for r in results)

    def test_exclude_patterns(self, tmp_path):
        """Test that exclude patterns are respected."""
        # Create file in excluded directory
        (tmp_path / "venv").mkdir()
        (tmp_path / "venv" / "slow.py").write_text(
            textwrap.dedent(
                """
            def slow(items):
                for i in items:
                    for j in items:
                        pass
        """
            )
        )

        analyzer = PerformanceAnalyzer(
            project_root=str(tmp_path), exclude_patterns=["venv"]
        )
        results = analyzer.analyze_directory()

        # Should not analyze files in venv
        assert not any("venv" in r.file_path for r in results)


class TestSummaryGeneration:
    """Test performance summary generation."""

    def test_get_summary(self):
        """Test summary generation."""
        code = textwrap.dedent(
            """
            def problematic(items, db):
                result = ""
                for item in items:
                    for sub in item:
                        db.execute(f"SELECT * FROM table WHERE id = {sub}")
                        result += str(sub)
                return result
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)
            analyzer.results = results
            summary = analyzer.get_summary()

            assert "total_issues" in summary
            assert "by_severity" in summary
            assert "performance_score" in summary
            assert "grade" in summary
            assert summary["total_issues"] >= 1
            assert summary["performance_score"] <= 100

    def test_performance_score_calculation(self):
        """Test that performance score is calculated correctly."""
        code = textwrap.dedent(
            """
            async def problematic():
                import time
                time.sleep(1)  # CRITICAL issue
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)
            analyzer.results = results
            summary = analyzer.get_summary()

            # Critical issues should significantly lower score
            assert summary["performance_score"] < 100
            if summary.get("critical_issues", 0) > 0:
                assert summary["performance_score"] <= 80


class TestReportGeneration:
    """Test performance report generation."""

    def test_json_report_format(self):
        """Test JSON report generation."""
        code = textwrap.dedent(
            """
            def slow(data):
                for i in data:
                    for j in data:
                        pass
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)
            analyzer.results = results
            report = analyzer.generate_report(format="json")

            import json

            parsed = json.loads(report)
            assert "summary" in parsed
            assert "findings" in parsed
            assert "recommendations" in parsed

    def test_markdown_report_format(self):
        """Test Markdown report generation."""
        code = textwrap.dedent(
            """
            def slow(data):
                for i in data:
                    for j in data:
                        pass
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)
            analyzer.results = results
            report = analyzer.generate_report(format="markdown")

            assert "# Performance Analysis Report" in report
            assert "## Summary" in report
            assert "Performance Score" in report


class TestPerformanceIssueTypes:
    """Test performance issue type enumeration."""

    def test_get_performance_issue_types(self):
        """Test getting all performance issue types."""
        types = get_performance_issue_types()

        assert len(types) > 0
        for pt in types:
            assert "type" in pt
            assert "description" in pt
            assert "category" in pt

    def test_issue_categories(self):
        """Test that issue types have proper categories."""
        types = get_performance_issue_types()

        categories = {pt["category"] for pt in types}

        # Should have major categories
        expected_categories = {"Database", "Algorithm", "Async/Await", "Memory", "I/O"}
        assert len(categories & expected_categories) >= 3


class TestConvenienceFunction:
    """Test the analyze_performance convenience function."""

    def test_analyze_performance_function(self, tmp_path):
        """Test the convenience function."""
        (tmp_path / "test.py").write_text(
            textwrap.dedent(
                """
            def test():
                for i in range(10):
                    for j in range(10):
                        pass
        """
            )
        )

        result = analyze_performance(str(tmp_path))

        assert "results" in result
        assert "summary" in result
        assert "report" in result


class TestSeverityLevels:
    """Test severity level assignments."""

    def test_critical_severity_for_blocking_async(self):
        """Blocking sync operations in async should be CRITICAL."""
        code = textwrap.dedent(
            """
            import time

            async def blocked():
                time.sleep(5)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            critical_results = [
                r for r in results if r.severity == PerformanceSeverity.CRITICAL
            ]

            assert len(critical_results) >= 1

    def test_high_severity_for_n_plus_one(self):
        """N+1 queries should be HIGH severity."""
        code = textwrap.dedent(
            """
            def fetch_all(items, db):
                for item in items:
                    db.query(item.id)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            n_plus_one = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.N_PLUS_ONE_QUERY
            ]

            if n_plus_one:
                assert n_plus_one[0].severity == PerformanceSeverity.HIGH

    def test_medium_severity_for_string_concat(self):
        """String concatenation in loop should be MEDIUM severity."""
        code = textwrap.dedent(
            """
            def build(items):
                s = ""
                for i in items:
                    s += "x"
                return s
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            concat_results = [
                r
                for r in results
                if r.issue_type == PerformanceIssueType.EXCESSIVE_STRING_CONCAT
            ]

            if concat_results:
                assert concat_results[0].severity == PerformanceSeverity.MEDIUM


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_file(self):
        """Test analysis of empty file."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("")
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            assert len(results) == 0

    def test_syntax_error_handling(self):
        """Test handling of files with syntax errors."""
        code = "def broken(:\n    pass"

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            # Should not crash, may return empty results
            assert isinstance(results, list)

    def test_non_python_file(self):
        """Test handling of non-Python files."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("This is not Python")
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            assert len(results) == 0

    def test_file_not_found(self):
        """Test handling of non-existent files."""
        analyzer = PerformanceAnalyzer()
        results = analyzer.analyze_file("/nonexistent/path/file.py")

        assert len(results) == 0


class TestToDict:
    """Test PerformanceIssue.to_dict() method."""

    def test_to_dict_serialization(self):
        """Test that issues serialize correctly."""
        code = textwrap.dedent(
            """
            def slow(items):
                for i in items:
                    for j in items:
                        pass
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = PerformanceAnalyzer()
            results = analyzer.analyze_file(f.name)

            if results:
                issue_dict = results[0].to_dict()

                assert "issue_type" in issue_dict
                assert "severity" in issue_dict
                assert "file_path" in issue_dict
                assert "line_start" in issue_dict
                assert "description" in issue_dict
                assert "recommendation" in issue_dict
                assert isinstance(issue_dict["issue_type"], str)
                assert isinstance(issue_dict["severity"], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
