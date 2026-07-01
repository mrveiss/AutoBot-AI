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
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestAnalyzeDiffGather:
    """Tests for analyze_diff gather ordering (Issues #10811 / #10814).

    Both tests call the REAL analyze_diff with mocked I/O dependencies so that
    a regression in the gather structure (e.g. collapsing both gathers into one)
    is detected by these tests rather than silently passing.

    Gather sites under test:
    1. source_root + diff_content — both obtained inside the first gather.
    2. redis.set + redis.lpush — first gather; redis.ltrim + redis.expire — second
       gather (the second gather depends on lpush having created the list key first).
    """

    @pytest.mark.asyncio
    async def test_source_root_and_diff_content_both_resolved(self):
        """Real analyze_diff must call both _resolve_source_root_or_404 and get_git_diff (site 1 gather)."""
        resolve_calls: list = []
        diff_calls: list = []

        async def fake_resolve(source_id):
            resolve_calls.append(source_id)
            return None

        async def fake_get_diff(commit_range):
            diff_calls.append(commit_range)
            return ""  # empty diff → early no_data return; Redis section not entered

        with (
            patch("api.analytics_code_review._resolve_source_root_or_404", fake_resolve),
            patch("api.analytics_code_review.get_git_diff", fake_get_diff),
        ):
            from api.analytics_code_review import analyze_diff

            result = await analyze_diff(admin_check=True, commit_range=None, source_id=None)

        assert len(resolve_calls) == 1, "_resolve_source_root_or_404 not called by analyze_diff"
        assert len(diff_calls) == 1, "get_git_diff not called by analyze_diff"
        assert result["status"] == "no_data"

    @pytest.mark.asyncio
    async def test_redis_persist_call_order(self):
        """lpush must be fully committed before ltrim and expire start (two-gather contract)."""
        import asyncio as real_asyncio

        # A minimal diff whose file path does not exist on disk — parse_diff produces
        # one entry but file_path.exists() returns False, so the inner file loop is
        # skipped and all_comments stays empty.  This lets us reach the Redis
        # persistence block without touching the real filesystem.
        fake_diff = "diff --git a/zzz_no_exist_autobot_test.py b/zzz_no_exist_autobot_test.py\n" "@@ -1 +1 @@\n" "+x\n"

        call_log: list[str] = []
        redis_mock = MagicMock()

        # Build a name-lookup table keyed by the mock's own attribute objects.
        # MagicMock returns the same child object on every attribute access, so
        # identity comparison is stable and survives the lazy `from ... import`
        # inside analyze_diff's try block.
        fn_to_name = {
            redis_mock.set: "set",
            redis_mock.lpush: "lpush",
            redis_mock.ltrim: "ltrim",
            redis_mock.expire: "expire",
        }

        async def tracking_to_thread(fn, *args, **kwargs):
            """Drop-in for asyncio.to_thread that records Redis call order.

            For lpush we yield once to the event loop.  If ltrim/expire share
            the SAME gather as lpush (broken code), they will run during that
            yield and appear before lpush in call_log — failing the ordering
            assertion.  With two separate gathers (correct code) there are no
            other pending tasks when lpush yields inside the first gather, so
            lpush resumes immediately and completes before the second gather
            starts.
            """
            name = fn_to_name.get(fn)
            if name == "lpush":
                # Deliberately yield so that any tasks in the same gather that
                # do NOT yield can overtake us.  This is the canary: ltrim and
                # expire must NOT be in the same gather.
                await real_asyncio.sleep(0)
            result = fn(*args, **kwargs)
            if name:
                call_log.append(name)
            return result

        with (
            patch("api.analytics_code_review._resolve_source_root_or_404", AsyncMock(return_value=None)),
            patch("api.analytics_code_review.get_git_diff", AsyncMock(return_value=fake_diff)),
            patch("autobot_shared.redis_client.get_redis_client", return_value=redis_mock),
            patch("asyncio.to_thread", tracking_to_thread),
        ):
            from api.analytics_code_review import analyze_diff

            result = await analyze_diff(admin_check=True, commit_range=None, source_id=None)

        assert result["status"] == "success"

        # All four Redis persistence operations must have been called by analyze_diff.
        assert "set" in call_log, "redis.set was not called"
        assert "lpush" in call_log, "redis.lpush was not called"
        assert "ltrim" in call_log, "redis.ltrim was not called"
        assert "expire" in call_log, "redis.expire was not called"

        # Ordering guarantee: lpush creates the history list key; ltrim and expire
        # must only run after lpush has completed (i.e. they belong to the second
        # gather, which only starts after the first gather's await returns).
        lpush_idx = call_log.index("lpush")
        ltrim_idx = call_log.index("ltrim")
        expire_idx = call_log.index("expire")
        assert ltrim_idx > lpush_idx, (
            f"ltrim (call #{ltrim_idx}) must follow lpush (call #{lpush_idx}); " f"full call order: {call_log}"
        )
        assert expire_idx > lpush_idx, (
            f"expire (call #{expire_idx}) must follow lpush (call #{lpush_idx}); " f"full call order: {call_log}"
        )
