# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Technical Debt Detection Patterns.

Tests the detection of technical debt markers (TODO, FIXME, BUG, HACK, XXX, DEPRECATED)
ensuring that:
1. Valid markers with colons are detected (e.g., "# TODO: fix this")
2. Section headers without colons are NOT falsely detected (e.g., "# Bug risk patterns")

Issue #617: Fix 5 Technical Debt BUG Comments (All High Severity)
"""

import pytest

from backend.api.codebase_analytics.analyzers import _detect_technical_debt_in_line


class TestTechnicalDebtPatterns:
    """Test technical debt marker detection patterns."""

    def test_valid_todo_with_colon_detected(self):
        """Test that TODO: comments are properly detected."""
        line = "    # TODO: implement error handling"
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "todo"
        assert debt_items[0]["severity"] == "low"
        assert "implement error handling" in debt_items[0]["description"]

    def test_valid_fixme_with_colon_detected(self):
        """Test that FIXME: comments are properly detected."""
        line = "# FIXME: this needs to be refactored"
        debt_items, problem_items = _detect_technical_debt_in_line(10, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "fixme"
        assert debt_items[0]["severity"] == "medium"

    def test_valid_bug_with_colon_detected(self):
        """Test that BUG: comments are properly detected."""
        line = "# BUG: race condition in async handler"
        debt_items, problem_items = _detect_technical_debt_in_line(5, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "bug"
        assert debt_items[0]["severity"] == "high"
        assert "race condition" in debt_items[0]["description"]

    def test_valid_hack_with_colon_detected(self):
        """Test that HACK: comments are properly detected."""
        line = "# HACK: temporary workaround until API is fixed"
        debt_items, problem_items = _detect_technical_debt_in_line(20, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "hack"
        assert debt_items[0]["severity"] == "high"

    def test_valid_xxx_with_colon_detected(self):
        """Test that XXX: comments are properly detected."""
        line = "# XXX: needs review before production"
        debt_items, problem_items = _detect_technical_debt_in_line(15, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "xxx"
        assert debt_items[0]["severity"] == "medium"

    def test_valid_deprecated_with_colon_detected(self):
        """Test that DEPRECATED: comments are properly detected."""
        line = "# DEPRECATED: use new_function() instead"
        debt_items, problem_items = _detect_technical_debt_in_line(30, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "deprecated"
        assert debt_items[0]["severity"] == "medium"


class TestFalsePositivePrevention:
    """Test that section headers are NOT falsely detected as technical debt.

    Issue #617: These were the 5 false positives that were being detected:
    1. backend/api/analytics_code_review.py:156 - "# Bug risk patterns"
    2. src/code_intelligence/code_review_engine.py:266 - "# Bug Risk patterns"
    3. src/code_intelligence/__init__.py:340 - "# Bug prediction (Issue #224)"
    4. src/code_intelligence/bug_predictor.py:237 - "# Bug Predictor Class"
    5. src/chat_history/analysis.py:148 - "# Bug mention patterns"
    """

    def test_bug_risk_patterns_not_detected(self):
        """Test that '# Bug risk patterns' section header is NOT detected."""
        line = "    # Bug risk patterns"
        debt_items, problem_items = _detect_technical_debt_in_line(156, line, "test.py")

        assert (
            len(debt_items) == 0
        ), "Section header should not be detected as tech debt"
        assert len(problem_items) == 0

    def test_bug_prediction_comment_not_detected(self):
        """Test that '# Bug prediction (Issue #224)' is NOT detected."""
        line = "    # Bug prediction (Issue #224)"
        debt_items, problem_items = _detect_technical_debt_in_line(340, line, "test.py")

        assert (
            len(debt_items) == 0
        ), "Issue reference should not be detected as tech debt"

    def test_bug_predictor_class_not_detected(self):
        """Test that '# Bug Predictor Class' is NOT detected."""
        line = "# Bug Predictor Class"
        debt_items, problem_items = _detect_technical_debt_in_line(237, line, "test.py")

        assert len(debt_items) == 0, "Class section should not be detected as tech debt"

    def test_bug_mention_patterns_not_detected(self):
        """Test that '# Bug mention patterns' is NOT detected."""
        line = "        # Bug mention patterns"
        debt_items, problem_items = _detect_technical_debt_in_line(148, line, "test.py")

        assert (
            len(debt_items) == 0
        ), "Section header should not be detected as tech debt"

    def test_todo_list_section_not_detected(self):
        """Test that '# Todo list items' section header is NOT detected."""
        line = "# Todo list items for release"
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 0, "Section header without colon should not match"

    def test_fixme_utils_section_not_detected(self):
        """Test that '# Fixme utilities' section header is NOT detected."""
        line = "# Fixme utilities and helpers"
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 0, "Section header without colon should not match"

    def test_hack_night_section_not_detected(self):
        """Test that '# Hack night code' section header is NOT detected."""
        line = "# Hack night code cleanup"
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 0, "Section header without colon should not match"


class TestCaseInsensitivity:
    """Test that pattern matching is case-insensitive."""

    def test_lowercase_todo_detected(self):
        """Test that lowercase 'todo:' is detected."""
        line = "# todo: this is lowercase"
        debt_items, _ = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "todo"

    def test_mixed_case_fixme_detected(self):
        """Test that mixed case 'FixMe:' is detected."""
        line = "# FixMe: mixed case example"
        debt_items, _ = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "fixme"

    def test_uppercase_bug_detected(self):
        """Test that uppercase 'BUG:' is detected."""
        line = "# BUG: uppercase bug marker"
        debt_items, _ = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "bug"


class TestEdgeCases:
    """Test edge cases for technical debt detection."""

    def test_empty_line_no_detection(self):
        """Test that empty lines don't cause issues."""
        line = ""
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 0
        assert len(problem_items) == 0

    def test_whitespace_only_no_detection(self):
        """Test that whitespace-only lines don't cause issues."""
        line = "        "
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 0
        assert len(problem_items) == 0

    def test_code_without_comment_no_detection(self):
        """Test that regular code without comments is not detected."""
        line = "def todo_handler(bug_fix):"
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 0

    def test_inline_comment_with_marker_detected(self):
        """Test that inline comments with markers are detected."""
        line = "result = calculate()  # TODO: add error handling"
        debt_items, _ = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "todo"

    def test_description_truncation(self):
        """Test that very long descriptions are truncated to 200 chars."""
        long_description = "x" * 300
        line = f"# TODO: {long_description}"
        debt_items, _ = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert len(debt_items[0]["description"]) <= 200

    def test_multiple_spaces_after_colon(self):
        """Test that multiple spaces after colon still works."""
        line = "# TODO:    lots of spaces here"
        debt_items, _ = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert "lots of spaces here" in debt_items[0]["description"]

    def test_no_space_after_hash(self):
        """Test detection when there's no space after the hash."""
        line = "#TODO: no space after hash"
        debt_items, _ = _detect_technical_debt_in_line(1, line, "test.py")

        assert len(debt_items) == 1
        assert debt_items[0]["type"] == "todo"


class TestProblemItemsGeneration:
    """Test that problem items are correctly generated alongside debt items."""

    def test_problem_item_generated_for_todo(self):
        """Test that problem items are generated with correct format."""
        line = "# TODO: implement feature"
        debt_items, problem_items = _detect_technical_debt_in_line(42, line, "test.py")

        assert len(problem_items) == 1
        assert problem_items[0]["type"] == "technical_debt_todo"
        assert problem_items[0]["line"] == 42
        assert "TODO" in problem_items[0]["description"]
        assert "Address" in problem_items[0]["suggestion"]

    def test_problem_item_severity_matches_debt_item(self):
        """Test that problem item severity matches debt item severity."""
        line = "# BUG: critical issue"
        debt_items, problem_items = _detect_technical_debt_in_line(1, line, "test.py")

        assert debt_items[0]["severity"] == "high"
        assert problem_items[0]["severity"] == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
