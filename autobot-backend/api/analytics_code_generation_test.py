# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for analytics_code_generation.py source_id scoping (Issue #3436)

Tests the following functionality:
- _extract_language_stats helper function
- _get_refactoring_description helper function
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


class TestExtractLanguageStats:
    """Tests for _extract_language_stats utility function."""

    def test_empty_dict_returns_empty(self):
        """Empty stats should return empty dict."""
        from api.analytics_code_generation import _extract_language_stats

        result = _extract_language_stats({})
        assert result == {}

    def test_excludes_reserved_keys(self):
        """Keys in EXCLUDED_LANGUAGE_KEYS should be excluded."""
        from api.analytics_code_generation import _extract_language_stats

        stats = {
            "total": 100,
            "success": 50,
            "tokens": 999,
        }
        result = _extract_language_stats(stats)
        assert result == {}

    def test_extracts_language_with_colon_format(self):
        """Keys in 'prefix:lang:suffix' format should produce language entries."""
        from api.analytics_code_generation import _extract_language_stats

        stats = {
            "gen:python:count": 10,
            "gen:typescript:count": 5,
        }
        result = _extract_language_stats(stats)
        assert "python" in result
        assert "typescript" in result


class TestGetRefactoringDescription:
    """Tests for _get_refactoring_description helper."""

    def test_known_type_returns_non_empty_description(self):
        """Each defined RefactoringType should have a description."""
        from api.analytics_code_generation import (
            RefactoringType,
            _get_refactoring_description,
        )

        for rt in RefactoringType:
            desc = _get_refactoring_description(rt)
            assert isinstance(desc, str)
            assert len(desc) > 0

    def test_general_type_returns_fallback(self):
        """GENERAL type should return a reasonable description."""
        from api.analytics_code_generation import (
            RefactoringType,
            _get_refactoring_description,
        )

        desc = _get_refactoring_description(RefactoringType.GENERAL)
        assert "general" in desc.lower() or "quality" in desc.lower()


class TestSourceIdGuardLogic:
    """Tests for _resolve_source_or_404 guard (mocked via sys.modules injection)."""

    @pytest.mark.asyncio
    async def test_none_source_id_does_not_raise(self):
        """_resolve_source_or_404 with None should return without raising."""
        from api.analytics_code_generation import _resolve_source_or_404

        await _resolve_source_or_404(None)

    @pytest.mark.asyncio
    async def test_unknown_source_id_raises_404(self):
        """_resolve_source_or_404 with unknown source_id should raise HTTP 404."""
        from fastapi import HTTPException

        fake_mod = _make_shared_mock(return_path=None)
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_code_generation import _resolve_source_or_404

            with pytest.raises(HTTPException) as exc_info:
                await _resolve_source_or_404("unknown-gen-id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_source_id_does_not_raise(self):
        """_resolve_source_or_404 with valid source_id should return without raising."""
        fake_mod = _make_shared_mock(return_path=Path("/repos/gen-project"))
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_code_generation import _resolve_source_or_404

            await _resolve_source_or_404("gen-project-id")


class TestTrackGenerationStatsGather:
    """Tests for _track_generation_stats gather refactor (Issue #10811).

    Verifies that the gathered hincrby calls produce identical results to the
    previous sequential version: all four hash fields are written and expire is
    set exactly once, in order.
    """

    @pytest.mark.asyncio
    async def test_gather_calls_all_hincrby_fields_on_success(self):
        """All four hincrby fields plus expire must be called when success=True."""
        from api.analytics_code_generation import CodeGenerationEngine

        redis_mock = AsyncMock()
        redis_mock.hincrby = AsyncMock(return_value=1)
        redis_mock.expire = AsyncMock(return_value=True)

        engine = CodeGenerationEngine.__new__(CodeGenerationEngine)
        engine._redis = redis_mock
        engine._stats_key = "autobot:code_generation:stats"

        await engine._track_generation_stats("generate", "python", 100, True)

        called_fields = [call.args[1] for call in redis_mock.hincrby.call_args_list]
        assert "generate:total" in called_fields
        assert "generate:python:total" in called_fields
        assert "generate:tokens" in called_fields
        assert "generate:success" in called_fields
        assert redis_mock.expire.call_count == 1

    @pytest.mark.asyncio
    async def test_gather_omits_success_field_on_failure(self):
        """When success=False the success field must NOT be incremented."""
        from api.analytics_code_generation import CodeGenerationEngine

        redis_mock = AsyncMock()
        redis_mock.hincrby = AsyncMock(return_value=1)
        redis_mock.expire = AsyncMock(return_value=True)

        engine = CodeGenerationEngine.__new__(CodeGenerationEngine)
        engine._redis = redis_mock
        engine._stats_key = "autobot:code_generation:stats"

        await engine._track_generation_stats("generate", "typescript", 50, False)

        called_fields = [call.args[1] for call in redis_mock.hincrby.call_args_list]
        assert "generate:success" not in called_fields
        assert "generate:total" in called_fields

    @pytest.mark.asyncio
    async def test_expire_called_after_hincrby(self):
        """expire must be called exactly once, after the gather completes."""
        from api.analytics_code_generation import CodeGenerationEngine

        call_order = []

        async def track_hincrby(*args, **kwargs):
            call_order.append("hincrby")
            return 1

        async def track_expire(*args, **kwargs):
            call_order.append("expire")
            return True

        redis_mock = MagicMock()
        redis_mock.hincrby = track_hincrby
        redis_mock.expire = track_expire

        engine = CodeGenerationEngine.__new__(CodeGenerationEngine)
        engine._redis = redis_mock
        engine._stats_key = "autobot:code_generation:stats"

        await engine._track_generation_stats("refactor", "python", 200, True)

        assert "expire" in call_order
        # expire must come after all hincrby calls
        last_hincrby_idx = max(i for i, v in enumerate(call_order) if v == "hincrby")
        expire_idx = call_order.index("expire")
        assert expire_idx > last_hincrby_idx


class TestGetRedisAwaitsCoroutine:
    """Regression: _get_redis must await get_redis_client(async_client=True), which
    returns a coroutine. A missing await silently broke every stats/version Redis op
    (AttributeError on the coroutine, swallowed by except)."""

    async def test_get_redis_returns_resolved_client_not_coroutine(self):
        from api.analytics_code_generation import CodeGenerationEngine

        engine = CodeGenerationEngine.__new__(CodeGenerationEngine)
        engine._redis = None
        fake_client = MagicMock(name="async_redis_client")
        with patch(
            "api.analytics_code_generation.get_redis_client",
            new=AsyncMock(return_value=fake_client),
        ) as mock_get:
            result = await engine._get_redis()

        # Must be the resolved client, never an un-awaited coroutine.
        assert result is fake_client
        mock_get.assert_awaited_once()

    async def test_get_redis_caches_client(self):
        from api.analytics_code_generation import CodeGenerationEngine

        engine = CodeGenerationEngine.__new__(CodeGenerationEngine)
        engine._redis = None
        fake_client = MagicMock(name="async_redis_client")
        with patch(
            "api.analytics_code_generation.get_redis_client",
            new=AsyncMock(return_value=fake_client),
        ) as mock_get:
            first = await engine._get_redis()
            second = await engine._get_redis()

        assert first is second is fake_client
        mock_get.assert_awaited_once()  # cached — acquired only once
