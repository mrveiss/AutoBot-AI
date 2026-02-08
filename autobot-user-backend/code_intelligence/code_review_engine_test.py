# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the Code Review Engine (Issue #225).

Tests the AI-powered code review automation functionality including:
- Pattern matching and detection
- Diff parsing
- File review
- Score calculation
- Summary generation
"""

import pytest
from code_intelligence.code_review_engine import (
    BUILTIN_PATTERNS,
    CodeReviewEngine,
    DiffFile,
    DiffHunk,
    ReviewCategory,
    ReviewComment,
    ReviewPattern,
    ReviewResult,
    ReviewSeverity,
    get_review_categories,
    get_review_patterns,
    get_review_severities,
    review_file,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def engine():
    """Create a CodeReviewEngine instance."""
    return CodeReviewEngine()


@pytest.fixture
def engine_with_tmp(tmp_path):
    """Create a CodeReviewEngine with temp directory as project root."""
    return CodeReviewEngine(project_root=str(tmp_path))


@pytest.fixture
def sample_python_code():
    """Sample Python code with various issues."""
    return """
import os
from utils import *

password = "secret123"

def process_data(items=[]):
    result = ""
    for item in items:
        result += str(item)
    return result

def test_something():
    x = 1
    y = 2

class MyClass:
    def very_long_function(self):
        if True:
            if True:
                if True:
                    if True:
                        if True:
                            print("deep nesting")

print("debug output")

# TODO: fix this later
"""


@pytest.fixture
def sample_diff():
    """Sample unified diff content."""
    return """diff --git a/example.py b/example.py
new file mode 100644
--- /dev/null
+++ b/example.py
@@ -0,0 +1,10 @@
+import os
+
+password = "mysecret"
+
+def greet(name):
+    print(f"Hello {name}")
+
+if x == None:
+    pass
+
"""


# ============================================================================
# Enum Tests
# ============================================================================


class TestReviewSeverity:
    """Tests for ReviewSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert ReviewSeverity.CRITICAL.value == "critical"
        assert ReviewSeverity.WARNING.value == "warning"
        assert ReviewSeverity.INFO.value == "info"
        assert ReviewSeverity.SUGGESTION.value == "suggestion"

    def test_severity_count(self):
        """Test number of severity levels."""
        assert len(ReviewSeverity) == 4


class TestReviewCategory:
    """Tests for ReviewCategory enum."""

    def test_category_values(self):
        """Test category enum values."""
        assert ReviewCategory.SECURITY.value == "security"
        assert ReviewCategory.PERFORMANCE.value == "performance"
        assert ReviewCategory.STYLE.value == "style"
        assert ReviewCategory.BUG_RISK.value == "bug_risk"
        assert ReviewCategory.MAINTAINABILITY.value == "maintainability"
        assert ReviewCategory.DOCUMENTATION.value == "documentation"
        assert ReviewCategory.TESTING.value == "testing"
        assert ReviewCategory.BEST_PRACTICE.value == "best_practice"

    def test_category_count(self):
        """Test number of categories."""
        assert len(ReviewCategory) == 8


# ============================================================================
# Data Class Tests
# ============================================================================


class TestReviewPattern:
    """Tests for ReviewPattern dataclass."""

    def test_pattern_creation(self):
        """Test creating a review pattern."""
        pattern = ReviewPattern(
            id="TEST001",
            name="Test Pattern",
            category=ReviewCategory.TESTING,
            severity=ReviewSeverity.INFO,
            pattern=r"test_\w+",
            message="Test message",
            suggestion="Test suggestion",
        )
        assert pattern.id == "TEST001"
        assert pattern.name == "Test Pattern"
        assert pattern.category == ReviewCategory.TESTING
        assert pattern.severity == ReviewSeverity.INFO
        assert pattern.pattern == r"test_\w+"
        assert pattern.message == "Test message"
        assert pattern.suggestion == "Test suggestion"

    def test_pattern_to_dict(self):
        """Test pattern conversion to dictionary."""
        pattern = ReviewPattern(
            id="TEST001",
            name="Test Pattern",
            category=ReviewCategory.TESTING,
            severity=ReviewSeverity.INFO,
            pattern=r"test",
            message="Test message",
        )
        result = pattern.to_dict()
        assert result["id"] == "TEST001"
        assert result["category"] == "testing"
        assert result["severity"] == "info"
        assert result["has_pattern"] is True

    def test_pattern_without_regex(self):
        """Test pattern with programmatic check (no regex)."""
        pattern = ReviewPattern(
            id="PROG001",
            name="Programmatic Check",
            category=ReviewCategory.STYLE,
            severity=ReviewSeverity.WARNING,
            pattern=None,
            message="Checked programmatically",
        )
        result = pattern.to_dict()
        assert result["has_pattern"] is False


class TestReviewComment:
    """Tests for ReviewComment dataclass."""

    def test_comment_creation(self):
        """Test creating a review comment."""
        comment = ReviewComment(
            id="SEC001-10",
            file_path="example.py",
            line_number=10,
            severity=ReviewSeverity.CRITICAL,
            category=ReviewCategory.SECURITY,
            message="Security issue found",
            suggestion="Fix it",
            code_snippet='password = "secret"',
            pattern_id="SEC001",
        )
        assert comment.id == "SEC001-10"
        assert comment.file_path == "example.py"
        assert comment.line_number == 10
        assert comment.severity == ReviewSeverity.CRITICAL
        assert comment.pattern_id == "SEC001"

    def test_comment_to_dict(self):
        """Test comment conversion to dictionary."""
        comment = ReviewComment(
            id="TEST-1",
            file_path="test.py",
            line_number=5,
            severity=ReviewSeverity.INFO,
            category=ReviewCategory.TESTING,
            message="Test issue",
        )
        result = comment.to_dict()
        assert result["id"] == "TEST-1"
        assert result["severity"] == "info"
        assert result["category"] == "testing"
        assert result["line_number"] == 5


class TestDiffHunk:
    """Tests for DiffHunk dataclass."""

    def test_hunk_creation(self):
        """Test creating a diff hunk."""
        hunk = DiffHunk(
            old_start=1,
            new_start=1,
            old_count=5,
            new_count=7,
            lines=[
                {"type": "context", "content": "line1"},
                {"type": "add", "content": "new line"},
                {"type": "delete", "content": "old line"},
            ],
        )
        assert hunk.old_start == 1
        assert hunk.new_start == 1
        assert len(hunk.lines) == 3


class TestDiffFile:
    """Tests for DiffFile dataclass."""

    def test_diff_file_creation(self):
        """Test creating a diff file."""
        diff_file = DiffFile(
            path="example.py",
            is_new=True,
            additions=10,
            deletions=0,
        )
        assert diff_file.path == "example.py"
        assert diff_file.is_new is True
        assert diff_file.additions == 10
        assert diff_file.deletions == 0


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_result_creation(self):
        """Test creating a review result."""
        from datetime import datetime

        result = ReviewResult(
            id="review-123",
            timestamp=datetime.now(),
            files_reviewed=5,
            total_comments=10,
            score=85.5,
        )
        assert result.id == "review-123"
        assert result.files_reviewed == 5
        assert result.total_comments == 10
        assert result.score == 85.5

    def test_result_to_dict(self):
        """Test result conversion to dictionary."""
        from datetime import datetime

        result = ReviewResult(
            id="review-456",
            timestamp=datetime.now(),
            files_reviewed=3,
            total_comments=5,
            score=90.0,
        )
        data = result.to_dict()
        assert data["id"] == "review-456"
        assert data["files_reviewed"] == 3
        assert data["score"] == 90.0
        assert "timestamp" in data


# ============================================================================
# Built-in Patterns Tests
# ============================================================================


class TestBuiltinPatterns:
    """Tests for built-in review patterns."""

    def test_builtin_patterns_exist(self):
        """Test that built-in patterns are defined."""
        assert len(BUILTIN_PATTERNS) >= 20

    def test_security_patterns(self):
        """Test security patterns exist."""
        security_patterns = [
            p
            for p in BUILTIN_PATTERNS.values()
            if p.category == ReviewCategory.SECURITY
        ]
        assert len(security_patterns) >= 5

    def test_pattern_ids_unique(self):
        """Test all pattern IDs are unique."""
        ids = list(BUILTIN_PATTERNS.keys())
        assert len(ids) == len(set(ids))

    def test_critical_patterns_exist(self):
        """Test that critical severity patterns exist."""
        critical = [
            p
            for p in BUILTIN_PATTERNS.values()
            if p.severity == ReviewSeverity.CRITICAL
        ]
        assert len(critical) >= 3

    def test_all_categories_covered(self):
        """Test all categories have at least one pattern."""
        categories_with_patterns = set(p.category for p in BUILTIN_PATTERNS.values())
        # At least 6 categories should have patterns
        assert len(categories_with_patterns) >= 6


# ============================================================================
# Code Review Engine Tests
# ============================================================================


class TestCodeReviewEngine:
    """Tests for CodeReviewEngine class."""

    def test_engine_initialization(self, engine):
        """Test engine initialization."""
        assert engine.project_root is not None
        assert len(engine.patterns) >= 20
        assert engine.context_lines == 2
        assert engine.max_function_lines == 50
        assert engine.max_nesting_depth == 4

    def test_engine_with_custom_root(self, tmp_path):
        """Test engine with custom project root."""
        engine = CodeReviewEngine(project_root=str(tmp_path))
        assert engine.project_root == tmp_path

    def test_engine_with_custom_settings(self):
        """Test engine with custom settings."""
        engine = CodeReviewEngine(
            context_lines=5,
            max_function_lines=100,
            max_nesting_depth=6,
        )
        assert engine.context_lines == 5
        assert engine.max_function_lines == 100
        assert engine.max_nesting_depth == 6

    def test_get_patterns(self, engine):
        """Test getting patterns from engine."""
        patterns = engine.get_patterns()
        assert len(patterns) >= 20
        assert all(isinstance(p, dict) for p in patterns)
        assert all("id" in p for p in patterns)

    def test_add_pattern(self, engine):
        """Test adding a custom pattern."""
        custom = ReviewPattern(
            id="CUSTOM001",
            name="Custom Pattern",
            category=ReviewCategory.STYLE,
            severity=ReviewSeverity.INFO,
            pattern=r"custom_keyword",
            message="Custom message",
        )
        initial_count = len(engine.patterns)
        engine.add_pattern(custom)
        assert len(engine.patterns) == initial_count + 1
        assert "CUSTOM001" in engine.patterns

    def test_remove_pattern(self, engine):
        """Test removing a pattern."""
        # Add then remove
        custom = ReviewPattern(
            id="REMOVE001",
            name="To Remove",
            category=ReviewCategory.STYLE,
            severity=ReviewSeverity.INFO,
            pattern=r"remove",
            message="Will be removed",
        )
        engine.add_pattern(custom)
        assert "REMOVE001" in engine.patterns

        result = engine.remove_pattern("REMOVE001")
        assert result is True
        assert "REMOVE001" not in engine.patterns

    def test_remove_nonexistent_pattern(self, engine):
        """Test removing a pattern that doesn't exist."""
        result = engine.remove_pattern("NONEXISTENT")
        assert result is False


# ============================================================================
# File Review Tests
# ============================================================================


class TestFileReview:
    """Tests for file review functionality."""

    def test_review_file_with_secrets(self, engine_with_tmp, tmp_path):
        """Test detecting hardcoded secrets."""
        code = 'password = "mysecret123"'
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        sec_comments = [c for c in comments if c.pattern_id == "SEC001"]
        assert len(sec_comments) >= 1

    def test_review_file_with_eval(self, engine_with_tmp, tmp_path):
        """Test detecting unsafe eval."""
        code = "result = eval(user_input)"
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        eval_comments = [c for c in comments if c.pattern_id == "SEC003"]
        assert len(eval_comments) >= 1

    def test_review_file_with_mutable_default(self, engine_with_tmp, tmp_path):
        """Test detecting mutable default arguments."""
        code = "def process(items=[]):\n    pass"
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        bug_comments = [c for c in comments if c.pattern_id == "BUG002"]
        assert len(bug_comments) >= 1

    def test_review_file_with_star_import(self, engine_with_tmp, tmp_path):
        """Test detecting star imports."""
        code = "from os import *"
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        star_comments = [c for c in comments if c.pattern_id == "BP004"]
        assert len(star_comments) >= 1

    def test_review_file_with_print(self, engine_with_tmp, tmp_path):
        """Test detecting print statements."""
        code = 'print("debug")'
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        print_comments = [c for c in comments if c.pattern_id == "BP001"]
        assert len(print_comments) >= 1

    def test_review_file_with_todo(self, engine_with_tmp, tmp_path):
        """Test detecting TODO comments."""
        code = "# TODO: implement this"
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        todo_comments = [c for c in comments if c.pattern_id == "BP002"]
        assert len(todo_comments) >= 1

    def test_review_file_with_content(self, engine):
        """Test reviewing file with provided content."""
        code = 'api_key = "abc123secret"'
        comments = engine.review_file("virtual.py", content=code)
        assert len(comments) >= 1

    def test_review_nonexistent_file(self, engine):
        """Test reviewing non-existent file."""
        comments = engine.review_file("/nonexistent/path/file.py")
        assert comments == []


# ============================================================================
# Programmatic Check Tests
# ============================================================================


class TestProgrammaticChecks:
    """Tests for programmatic code checks."""

    def test_long_function_detection(self, engine_with_tmp, tmp_path):
        """Test detection of overly long functions."""
        # Create a function with 60 lines
        lines = ["def long_function():"]
        lines.extend(["    x = 1"] * 60)
        code = "\n".join(lines)

        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        engine = CodeReviewEngine(
            project_root=str(tmp_path),
            max_function_lines=50,
        )
        comments = engine.review_file(str(file_path))
        style_comments = [c for c in comments if c.pattern_id == "STYLE002"]
        assert len(style_comments) >= 1

    def test_deep_nesting_detection(self, engine_with_tmp, tmp_path):
        """Test detection of deeply nested code."""
        code = """
def nested():
    if True:
        if True:
            if True:
                if True:
                    if True:
                        x = 1
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        engine = CodeReviewEngine(
            project_root=str(tmp_path),
            max_nesting_depth=4,
        )
        comments = engine.review_file(str(file_path))
        nesting_comments = [c for c in comments if c.pattern_id == "STYLE003"]
        assert len(nesting_comments) >= 1

    def test_test_without_assertion(self, engine_with_tmp, tmp_path):
        """Test detection of tests without assertions."""
        code = """
def test_something():
    x = 1
    y = 2
"""
        file_path = tmp_path / "test_example.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        test_comments = [c for c in comments if c.pattern_id == "TEST001"]
        assert len(test_comments) >= 1

    def test_test_with_assertion(self, engine_with_tmp, tmp_path):
        """Test that tests with assertions are not flagged."""
        code = """
def test_something():
    x = 1
    assert x == 1
"""
        file_path = tmp_path / "test_example.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        test_comments = [c for c in comments if c.pattern_id == "TEST001"]
        assert len(test_comments) == 0


# ============================================================================
# Diff Parsing Tests
# ============================================================================


class TestDiffParsing:
    """Tests for diff parsing functionality."""

    def test_parse_simple_diff(self, engine):
        """Test parsing a simple diff."""
        diff = """diff --git a/test.py b/test.py
new file mode 100644
--- /dev/null
+++ b/test.py
@@ -0,0 +1,3 @@
+line1
+line2
+line3
"""
        files = engine._parse_diff(diff)
        assert len(files) == 1
        assert files[0].path == "test.py"
        assert files[0].is_new is True
        assert files[0].additions == 3

    def test_parse_modification_diff(self, engine):
        """Test parsing a modification diff."""
        diff = """diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 line1
-old line
+new line
+another line
 line3
"""
        files = engine._parse_diff(diff)
        assert len(files) == 1
        assert files[0].additions == 2
        assert files[0].deletions == 1

    def test_parse_deletion_diff(self, engine):
        """Test parsing a file deletion diff."""
        diff = """diff --git a/deleted.py b/deleted.py
deleted file mode 100644
--- a/deleted.py
+++ /dev/null
@@ -1,3 +0,0 @@
-line1
-line2
-line3
"""
        files = engine._parse_diff(diff)
        assert len(files) == 1
        assert files[0].is_deleted is True

    def test_parse_multiple_files(self, engine):
        """Test parsing diff with multiple files."""
        diff = """diff --git a/file1.py b/file1.py
--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,2 @@
 line1
+new line
diff --git a/file2.py b/file2.py
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,2 @@
 line1
+new line
"""
        files = engine._parse_diff(diff)
        assert len(files) == 2


# ============================================================================
# Score Calculation Tests
# ============================================================================


class TestScoreCalculation:
    """Tests for score calculation."""

    def test_perfect_score(self, engine):
        """Test score with no issues."""
        score = engine._calculate_score([])
        assert score == 100.0

    def test_score_with_critical(self, engine):
        """Test score with critical issues."""
        comments = [
            ReviewComment(
                id="test",
                file_path="test.py",
                line_number=1,
                severity=ReviewSeverity.CRITICAL,
                category=ReviewCategory.SECURITY,
                message="Critical issue",
            )
        ]
        score = engine._calculate_score(comments)
        assert score == 85.0  # 100 - 15

    def test_score_with_warning(self, engine):
        """Test score with warning issues."""
        comments = [
            ReviewComment(
                id="test",
                file_path="test.py",
                line_number=1,
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.STYLE,
                message="Warning issue",
            )
        ]
        score = engine._calculate_score(comments)
        assert score == 95.0  # 100 - 5

    def test_score_with_multiple_issues(self, engine):
        """Test score with multiple issues."""
        comments = [
            ReviewComment(
                id="test1",
                file_path="test.py",
                line_number=1,
                severity=ReviewSeverity.CRITICAL,
                category=ReviewCategory.SECURITY,
                message="Critical",
            ),
            ReviewComment(
                id="test2",
                file_path="test.py",
                line_number=2,
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.STYLE,
                message="Warning",
            ),
            ReviewComment(
                id="test3",
                file_path="test.py",
                line_number=3,
                severity=ReviewSeverity.INFO,
                category=ReviewCategory.DOCUMENTATION,
                message="Info",
            ),
        ]
        score = engine._calculate_score(comments)
        assert score == 79.0  # 100 - 15 - 5 - 1

    def test_score_minimum_zero(self, engine):
        """Test score doesn't go below zero."""
        comments = [
            ReviewComment(
                id=f"test{i}",
                file_path="test.py",
                line_number=i,
                severity=ReviewSeverity.CRITICAL,
                category=ReviewCategory.SECURITY,
                message="Critical",
            )
            for i in range(10)
        ]
        score = engine._calculate_score(comments)
        assert score == 0  # 100 - 150 = 0 (min)


# ============================================================================
# Summary Generation Tests
# ============================================================================


class TestSummaryGeneration:
    """Tests for summary generation."""

    def test_empty_summary(self, engine):
        """Test summary with no comments."""
        summary = engine._generate_summary([])
        assert summary["critical_count"] == 0
        assert summary["warning_count"] == 0
        assert summary["info_count"] == 0

    def test_summary_by_severity(self, engine):
        """Test summary groups by severity."""
        comments = [
            ReviewComment(
                id="c1",
                file_path="test.py",
                line_number=1,
                severity=ReviewSeverity.CRITICAL,
                category=ReviewCategory.SECURITY,
                message="Critical",
            ),
            ReviewComment(
                id="c2",
                file_path="test.py",
                line_number=2,
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.STYLE,
                message="Warning",
            ),
        ]
        summary = engine._generate_summary(comments)
        assert summary["critical_count"] == 1
        assert summary["warning_count"] == 1

    def test_summary_by_category(self, engine):
        """Test summary groups by category."""
        comments = [
            ReviewComment(
                id="c1",
                file_path="test.py",
                line_number=1,
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.SECURITY,
                message="Security",
            ),
            ReviewComment(
                id="c2",
                file_path="test.py",
                line_number=2,
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.SECURITY,
                message="Security 2",
            ),
        ]
        summary = engine._generate_summary(comments)
        assert summary["by_category"]["security"] == 2

    def test_summary_top_issues(self, engine):
        """Test summary includes top issues."""
        comments = [
            ReviewComment(
                id=f"c{i}",
                file_path="test.py",
                line_number=i,
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.SECURITY,
                message="Issue",
            )
            for i in range(5)
        ]
        summary = engine._generate_summary(comments)
        assert len(summary["top_issues"]) >= 1
        assert summary["top_issues"][0]["category"] == "security"


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_review_file_function(self, tmp_path):
        """Test review_file convenience function."""
        code = 'password = "secret123"'
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        comments = review_file(str(file_path))
        assert len(comments) >= 1

    def test_get_review_patterns_function(self):
        """Test get_review_patterns convenience function."""
        patterns = get_review_patterns()
        assert len(patterns) >= 20
        assert all(isinstance(p, dict) for p in patterns)

    def test_get_review_categories_function(self):
        """Test get_review_categories convenience function."""
        categories = get_review_categories()
        assert len(categories) == 8
        assert all("id" in c for c in categories)
        assert all("name" in c for c in categories)
        assert all("description" in c for c in categories)
        assert all("icon" in c for c in categories)

    def test_get_review_severities_function(self):
        """Test get_review_severities convenience function."""
        severities = get_review_severities()
        assert len(severities) == 4
        assert all("level" in s for s in severities)
        assert all("weight" in s for s in severities)
        assert all("description" in s for s in severities)

        # Check weights are correct
        weights = {s["level"]: s["weight"] for s in severities}
        assert weights["critical"] == 15
        assert weights["warning"] == 5
        assert weights["info"] == 1
        assert weights["suggestion"] == 0.5


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the code review engine."""

    def test_full_file_review(self, tmp_path, sample_python_code):
        """Test full file review with sample code."""
        file_path = tmp_path / "test.py"
        file_path.write_text(sample_python_code)

        engine = CodeReviewEngine(project_root=str(tmp_path))
        comments = engine.review_file(str(file_path))

        # Should detect multiple issues
        assert len(comments) >= 3

        # Check categories detected
        categories = {c.category for c in comments}
        assert (
            ReviewCategory.SECURITY in categories
            or ReviewCategory.BEST_PRACTICE in categories
        )

    def test_review_diff_integration(self, tmp_path, sample_diff):
        """Test diff review integration."""
        # Create the file that would result from the diff
        file_path = tmp_path / "example.py"
        file_path.write_text(
            """import os

password = "mysecret"

def greet(name):
    print(f"Hello {name}")

if x == None:
    pass
"""
        )

        engine = CodeReviewEngine(project_root=str(tmp_path))
        result = engine.review_diff(sample_diff)

        assert isinstance(result, ReviewResult)
        assert result.files_reviewed >= 0

    def test_context_in_comments(self, tmp_path):
        """Test that context is included in comments."""
        code = """line1
line2
password = "secret123"
line4
line5
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        engine = CodeReviewEngine(project_root=str(tmp_path), context_lines=2)
        comments = engine.review_file(str(file_path))

        # Find the password comment
        pw_comments = [c for c in comments if c.pattern_id == "SEC001"]
        if pw_comments:
            comment = pw_comments[0]
            # Context should be captured
            assert len(comment.context_before) <= 2
            assert len(comment.context_after) <= 2


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(self, engine_with_tmp, tmp_path):
        """Test reviewing an empty file."""
        file_path = tmp_path / "empty.py"
        file_path.write_text("")

        comments = engine_with_tmp.review_file(str(file_path))
        assert comments == []

    def test_binary_file_handling(self, engine_with_tmp, tmp_path):
        """Test handling of non-text files."""
        file_path = tmp_path / "binary.py"
        file_path.write_bytes(b"\x00\x01\x02\x03")

        # Should not crash
        comments = engine_with_tmp.review_file(str(file_path))
        assert isinstance(comments, list)

    def test_invalid_pattern_regex(self):
        """Test handling of invalid regex in pattern."""
        engine = CodeReviewEngine()
        bad_pattern = ReviewPattern(
            id="BAD001",
            name="Bad Pattern",
            category=ReviewCategory.STYLE,
            severity=ReviewSeverity.INFO,
            pattern=r"[invalid(regex",
            message="Bad regex",
        )
        # Should not crash, just log warning
        engine.add_pattern(bad_pattern)
        assert "BAD001" in engine.patterns

    def test_unicode_content(self, engine_with_tmp, tmp_path):
        """Test handling of unicode content."""
        code = '# 日本語コメント\npassword = "秘密"'
        file_path = tmp_path / "unicode.py"
        file_path.write_text(code, encoding="utf-8")

        comments = engine_with_tmp.review_file(str(file_path))
        # Should handle unicode without crashing
        assert isinstance(comments, list)

    def test_very_long_lines(self, engine_with_tmp, tmp_path):
        """Test handling of very long lines."""
        code = "x = " + '"a' * 10000 + '"'
        file_path = tmp_path / "long.py"
        file_path.write_text(code)

        comments = engine_with_tmp.review_file(str(file_path))
        assert isinstance(comments, list)

    def test_empty_diff(self, engine):
        """Test reviewing an empty diff."""
        result = engine.review_diff("")
        assert result.files_reviewed == 0
        assert result.score == 100.0
