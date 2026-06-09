# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for analytics_code_review.py source_id scoping (Issue #3436)

Tests the following functionality:
- parse_diff helper function
- calculate_review_score helper function
- _no_data_response helper function
- _resolve_source_or_404 guard logic (mocked via sys.modules)
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_shared_mock(return_path=None):
    """Build a fake api.codebase_analytics.endpoints.shared module."""

    async def fake_resolve(source_id):
        if source_id is None:
            return None
        return return_path

    mod = types.ModuleType("api.codebase_analytics.endpoints.shared")
    mod.resolve_source_root = fake_resolve
    return mod


class TestParseDiff:
    """Tests for parse_diff utility function."""

    def test_empty_diff_returns_empty_list(self):
        """Empty diff string should return empty list."""
        from api.analytics_code_review import parse_diff

        result = parse_diff("")
        assert result == []

    def test_single_file_diff_parsed(self):
        """A single-file diff should produce one entry."""
        from api.analytics_code_review import parse_diff

        diff = "diff --git a/foo.py b/foo.py\n" "@@ -1,2 +1,3 @@\n" " existing_line\n" "+new_line\n" "-removed_line\n"
        result = parse_diff(diff)
        assert len(result) == 1
        assert result[0]["path"] == "foo.py"
        assert result[0]["additions"] == 1
        assert result[0]["deletions"] == 1

    def test_multiple_files_in_diff(self):
        """Multiple file headers in a diff should produce multiple entries."""
        from api.analytics_code_review import parse_diff

        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "@@ -1 +1 @@\n"
            "+line\n"
            "diff --git a/bar.py b/bar.py\n"
            "@@ -1 +1 @@\n"
            "+another_line\n"
        )
        result = parse_diff(diff)
        assert len(result) == 2


class TestCalculateReviewScore:
    """Tests for calculate_review_score utility function."""

    def test_no_comments_returns_100(self):
        """No review comments should give a perfect score."""
        from api.analytics_code_review import calculate_review_score

        assert calculate_review_score([]) == 100.0

    def test_critical_comment_reduces_score(self):
        """A critical comment should reduce the score significantly."""
        from api.analytics_code_review import (
            ReviewCategory,
            ReviewComment,
            ReviewSeverity,
            calculate_review_score,
        )

        comment = ReviewComment(
            id="SEC001-1",
            file_path="test.py",
            line_number=1,
            severity=ReviewSeverity.CRITICAL,
            category=ReviewCategory.SECURITY,
            message="Critical issue",
        )
        score = calculate_review_score([comment])
        assert score < 100.0
        assert score >= 0.0

    def test_score_clamped_to_zero(self):
        """Score should not go below 0."""
        from api.analytics_code_review import (
            ReviewCategory,
            ReviewComment,
            ReviewSeverity,
            calculate_review_score,
        )

        comments = [
            ReviewComment(
                id=f"SEC001-{i}",
                file_path="test.py",
                line_number=i,
                severity=ReviewSeverity.CRITICAL,
                category=ReviewCategory.SECURITY,
                message="Critical issue",
            )
            for i in range(20)
        ]
        score = calculate_review_score(comments)
        assert score == 0.0


class TestNoDataResponse:
    """Tests for _no_data_response helper."""

    def test_default_message(self):
        """Should include no_data status and message key."""
        from api.analytics_code_review import _no_data_response

        result = _no_data_response()
        assert result["status"] == "no_data"
        assert "message" in result
        assert "comments" in result

    def test_custom_message(self):
        """Should accept a custom message."""
        from api.analytics_code_review import _no_data_response

        result = _no_data_response("Custom message")
        assert result["message"] == "Custom message"


class TestSourceIdGuardLogic:
    """Tests for _resolve_source_or_404 guard (mocked via sys.modules injection)."""

    @pytest.mark.asyncio
    async def test_none_source_id_does_not_raise(self):
        """_resolve_source_or_404 with None should return without raising."""
        from api.analytics_code_review import _resolve_source_or_404

        await _resolve_source_or_404(None)

    @pytest.mark.asyncio
    async def test_unknown_source_id_raises_404(self):
        """_resolve_source_or_404 with unknown source_id should raise HTTP 404."""
        from fastapi import HTTPException

        fake_mod = _make_shared_mock(return_path=None)
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_code_review import _resolve_source_or_404

            with pytest.raises(HTTPException) as exc_info:
                await _resolve_source_or_404("nonexistent-id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_source_id_does_not_raise(self):
        """_resolve_source_or_404 with valid source_id should return without raising."""
        fake_mod = _make_shared_mock(return_path=Path("/repos/review-project"))
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_code_review import _resolve_source_or_404

            await _resolve_source_or_404("valid-id")
