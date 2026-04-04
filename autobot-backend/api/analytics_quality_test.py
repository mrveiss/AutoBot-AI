# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for analytics_quality.py source_id scoping (Issue #3436)

Tests the following functionality:
- get_grade helper function
- calculate_health_score helper function
- _no_data_response helper function
- _resolve_source_or_404 guard logic (mocked via sys.modules)
"""

import sys
import types
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _make_shared_mock(return_path=None):
    """Build a fake api.codebase_analytics.endpoints.shared module."""
    async def fake_resolve(source_id):
        if source_id is None:
            return None
        return return_path

    mod = types.ModuleType("api.codebase_analytics.endpoints.shared")
    mod.resolve_source_root = fake_resolve
    return mod


class TestGetGrade:
    """Tests for get_grade utility function."""

    def test_a_grade_for_high_score(self):
        """Score >= 90 should yield grade A."""
        from api.analytics_quality import get_grade, QualityGrade

        assert get_grade(95.0) == QualityGrade.A

    def test_b_grade_for_mid_score(self):
        """Score >= 80 should yield grade B."""
        from api.analytics_quality import get_grade, QualityGrade

        assert get_grade(85.0) == QualityGrade.B

    def test_c_grade(self):
        """Score >= 70 should yield grade C."""
        from api.analytics_quality import get_grade, QualityGrade

        assert get_grade(75.0) == QualityGrade.C

    def test_d_grade(self):
        """Score >= 60 should yield grade D."""
        from api.analytics_quality import get_grade, QualityGrade

        assert get_grade(65.0) == QualityGrade.D

    def test_f_grade_for_low_score(self):
        """Score < 60 should yield grade F."""
        from api.analytics_quality import get_grade, QualityGrade

        assert get_grade(50.0) == QualityGrade.F

    def test_boundary_score_90(self):
        """Exactly 90 should yield A."""
        from api.analytics_quality import get_grade, QualityGrade

        assert get_grade(90.0) == QualityGrade.A

    def test_boundary_score_just_below_90(self):
        """89.9 should yield B not A."""
        from api.analytics_quality import get_grade, QualityGrade

        assert get_grade(89.9) == QualityGrade.B


class TestCalculateHealthScore:
    """Tests for calculate_health_score helper."""

    def test_returns_health_score_object(self):
        """Should return a HealthScore with overall, grade, and breakdown."""
        from api.analytics_quality import calculate_health_score, HealthScore

        metrics = {
            "maintainability": 80.0,
            "reliability": 75.0,
            "security": 90.0,
            "performance": 70.0,
            "testability": 65.0,
            "documentation": 60.0,
        }
        result = calculate_health_score(metrics)

        assert isinstance(result, HealthScore)
        assert 0 <= result.overall <= 100
        assert result.grade is not None
        assert isinstance(result.breakdown, dict)
        assert isinstance(result.recommendations, list)

    def test_recommendations_for_low_scores(self):
        """Low scores should generate recommendation strings."""
        from api.analytics_quality import calculate_health_score

        metrics = {
            "maintainability": 50.0,
            "reliability": 55.0,
            "security": 45.0,
            "performance": 85.0,
            "testability": 90.0,
            "documentation": 80.0,
        }
        result = calculate_health_score(metrics)

        assert len(result.recommendations) > 0
        rec_text = " ".join(result.recommendations)
        assert any(
            cat in rec_text.lower()
            for cat in ["maintainability", "reliability", "security"]
        )

    def test_max_5_recommendations(self):
        """At most 5 recommendations are returned."""
        from api.analytics_quality import calculate_health_score

        metrics = {k: 40.0 for k in ["maintainability", "reliability", "security",
                                       "performance", "testability", "documentation"]}
        result = calculate_health_score(metrics)
        assert len(result.recommendations) <= 5


class TestNoDataResponse:
    """Tests for _no_data_response helper."""

    def test_default_message(self):
        """Should return a dict with status=no_data and default message."""
        from api.analytics_quality import _no_data_response

        result = _no_data_response()
        assert result["status"] == "no_data"
        assert "message" in result

    def test_custom_message(self):
        """Should return the custom message when provided."""
        from api.analytics_quality import _no_data_response

        result = _no_data_response("Custom error message")
        assert result["message"] == "Custom error message"


class TestSourceIdGuardLogic:
    """Tests for _resolve_source_or_404 guard (mocked via sys.modules injection)."""

    @pytest.mark.asyncio
    async def test_none_source_id_does_not_raise(self):
        """_resolve_source_or_404 with None should return without raising."""
        from api.analytics_quality import _resolve_source_or_404

        # Should not raise even without the codebase_analytics package loaded
        await _resolve_source_or_404(None)

    @pytest.mark.asyncio
    async def test_unknown_source_id_raises_404(self):
        """_resolve_source_or_404 with unknown source_id should raise HTTP 404."""
        from fastapi import HTTPException

        fake_mod = _make_shared_mock(return_path=None)
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_quality import _resolve_source_or_404

            with pytest.raises(HTTPException) as exc_info:
                await _resolve_source_or_404("nonexistent-id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_source_id_does_not_raise(self):
        """_resolve_source_or_404 with valid source_id should return without raising."""
        fake_mod = _make_shared_mock(return_path=Path("/repos/myproject"))
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_quality import _resolve_source_or_404

            # Should not raise
            await _resolve_source_or_404("valid-id")
