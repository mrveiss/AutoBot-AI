# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
