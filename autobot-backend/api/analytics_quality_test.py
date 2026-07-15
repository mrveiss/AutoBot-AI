# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for analytics_quality.py source_id scoping (Issue #3436)

Tests the following functionality:
- get_grade helper function
- calculate_health_score helper function
- _no_data_response helper function
- _resolve_source_root_or_404 guard logic (mocked via sys.modules)
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


class TestGetGrade:
    """Tests for get_grade utility function."""

    def test_a_grade_for_high_score(self):
        """Score >= 90 should yield grade A."""
        from api.analytics_quality import QualityGrade, get_grade

        assert get_grade(95.0) == QualityGrade.A

    def test_b_grade_for_mid_score(self):
        """Score >= 80 should yield grade B."""
        from api.analytics_quality import QualityGrade, get_grade

        assert get_grade(85.0) == QualityGrade.B

    def test_c_grade(self):
        """Score >= 70 should yield grade C."""
        from api.analytics_quality import QualityGrade, get_grade

        assert get_grade(75.0) == QualityGrade.C

    def test_d_grade(self):
        """Score >= 60 should yield grade D."""
        from api.analytics_quality import QualityGrade, get_grade

        assert get_grade(65.0) == QualityGrade.D

    def test_f_grade_for_low_score(self):
        """Score < 60 should yield grade F."""
        from api.analytics_quality import QualityGrade, get_grade

        assert get_grade(50.0) == QualityGrade.F

    def test_boundary_score_90(self):
        """Exactly 90 should yield A."""
        from api.analytics_quality import QualityGrade, get_grade

        assert get_grade(90.0) == QualityGrade.A

    def test_boundary_score_just_below_90(self):
        """89.9 should yield B not A."""
        from api.analytics_quality import QualityGrade, get_grade

        assert get_grade(89.9) == QualityGrade.B


class TestCalculateHealthScore:
    """Tests for calculate_health_score helper."""

    def test_returns_health_score_object(self):
        """Should return a HealthScore with overall, grade, and breakdown."""
        from api.analytics_quality import HealthScore, calculate_health_score

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
        assert any(cat in rec_text.lower() for cat in ["maintainability", "reliability", "security"])

    def test_max_5_recommendations(self):
        """At most 5 recommendations are returned."""
        from api.analytics_quality import calculate_health_score

        metrics = {
            k: 40.0
            for k in ["maintainability", "reliability", "security", "performance", "testability", "documentation"]
        }
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
    """Tests for _resolve_source_root_or_404 guard (mocked via sys.modules injection)."""

    @pytest.mark.asyncio
    async def test_none_source_id_does_not_raise(self):
        """_resolve_source_root_or_404 with None should return without raising."""
        from api.analytics_quality import _resolve_source_root_or_404

        # Should not raise even without the codebase_analytics package loaded
        await _resolve_source_root_or_404(None)

    @pytest.mark.asyncio
    async def test_unknown_source_id_raises_404(self):
        """_resolve_source_root_or_404 with unknown source_id should raise HTTP 404."""
        from fastapi import HTTPException

        fake_mod = _make_shared_mock(return_path=None)
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_quality import _resolve_source_root_or_404

            with pytest.raises(HTTPException) as exc_info:
                await _resolve_source_root_or_404("nonexistent-id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_source_id_does_not_raise(self):
        """_resolve_source_root_or_404 with valid source_id should return without raising."""
        fake_mod = _make_shared_mock(return_path=Path("/repos/myproject"))
        with patch.dict(sys.modules, {"api.codebase_analytics.endpoints.shared": fake_mod}):
            from api.analytics_quality import _resolve_source_root_or_404

            # Should not raise
            await _resolve_source_root_or_404("valid-id")


class TestPerSourceStatsLookup:
    """Issue #6670: _get_problems_from_chromadb must look up codebase_stats_{source_id} first."""

    def _fake_collection(self, problems_metadatas, stats_by_id):
        """Build an AsyncMock ChromaDB collection that records the ids/where it was queried with."""
        calls = []

        async def get(**kwargs):
            calls.append(kwargs)
            if kwargs.get("where") == {"type": "problem"}:
                return {"metadatas": problems_metadatas}
            ids = kwargs.get("ids") or []
            for stats_id in ids:
                if stats_id in stats_by_id:
                    return {"metadatas": [stats_by_id[stats_id]]}
            return {"metadatas": []}

        collection = MagicMock()
        collection.get = AsyncMock(side_effect=get)
        return collection, calls

    @pytest.mark.asyncio
    async def test_uses_per_source_stats_key_when_source_id_provided(self):
        """When source_id is given, the per-source codebase_stats_{id} doc must be tried first."""
        from api import analytics_quality as aq

        collection, calls = self._fake_collection(
            problems_metadatas=[],
            stats_by_id={"codebase_stats_abc123": {"total_files": 42, "total_lines": 1234}},
        )

        async def fake_get_collection():
            return collection

        with patch(
            "api.codebase_analytics.storage.get_code_collection_async",
            new=fake_get_collection,
        ):
            problems, stats = await aq._get_problems_from_chromadb(source_id="abc123")

        # Per-source key must be queried; global key must NOT be queried (returned data first)
        id_queries = [c.get("ids") for c in calls if "ids" in c]
        assert ["codebase_stats_abc123"] in id_queries
        assert ["codebase_stats"] not in id_queries
        assert stats["total_files"] == 42

    @pytest.mark.asyncio
    async def test_falls_back_to_global_stats_when_per_source_missing(self):
        """If codebase_stats_{id} is absent, fall back to the global codebase_stats key."""
        from api import analytics_quality as aq

        collection, calls = self._fake_collection(
            problems_metadatas=[],
            stats_by_id={"codebase_stats": {"total_files": 7, "total_lines": 200}},
        )

        async def fake_get_collection():
            return collection

        with patch(
            "api.codebase_analytics.storage.get_code_collection_async",
            new=fake_get_collection,
        ):
            problems, stats = await aq._get_problems_from_chromadb(source_id="missing-id")

        id_queries = [c.get("ids") for c in calls if "ids" in c]
        assert ["codebase_stats_missing-id"] in id_queries
        assert ["codebase_stats"] in id_queries
        assert stats["total_files"] == 7

    @pytest.mark.asyncio
    async def test_global_path_when_no_source_id(self):
        """When source_id is None, only the global codebase_stats doc is queried."""
        from api import analytics_quality as aq

        collection, calls = self._fake_collection(
            problems_metadatas=[],
            stats_by_id={"codebase_stats": {"total_files": 99}},
        )

        async def fake_get_collection():
            return collection

        with patch(
            "api.codebase_analytics.storage.get_code_collection_async",
            new=fake_get_collection,
        ):
            problems, stats = await aq._get_problems_from_chromadb()

        id_queries = [c.get("ids") for c in calls if "ids" in c]
        assert ["codebase_stats"] in id_queries
        assert all(q != ["codebase_stats_None"] for q in id_queries)
        assert stats["total_files"] == 99


# ============================================================================
# Issue #11184: runtime_risk dimension tests
# ============================================================================


class TestQualityWeights:
    """Weights dict must sum to 1.0 after adding runtime_risk (#11184)."""

    def test_weights_sum_to_one(self):
        from api.analytics_quality import _QUALITY_WEIGHTS

        total = sum(_QUALITY_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    def test_runtime_risk_key_present(self):
        from api.analytics_quality import _QUALITY_WEIGHTS

        assert "runtime_risk" in _QUALITY_WEIGHTS

    def test_runtime_risk_weight_is_0_10(self):
        from api.analytics_quality import _QUALITY_WEIGHTS

        assert abs(_QUALITY_WEIGHTS["runtime_risk"] - 0.10) < 1e-9

    def test_maintainability_reduced_to_0_20(self):
        from api.analytics_quality import _QUALITY_WEIGHTS

        assert abs(_QUALITY_WEIGHTS["maintainability"] - 0.20) < 1e-9

    def test_testability_reduced_to_0_05(self):
        from api.analytics_quality import _QUALITY_WEIGHTS

        assert abs(_QUALITY_WEIGHTS["testability"] - 0.05) < 1e-9


class TestCalculateRuntimeRiskScore:
    """Unit tests for _calculate_runtime_risk_score (#11184)."""

    def test_empty_map_returns_neutral_100(self):
        """Empty map must return 100.0 — neutral, never drags health down."""
        from api.analytics_quality import _calculate_runtime_risk_score

        assert _calculate_runtime_risk_score({}) == 100.0

    def test_high_risk_yields_low_health(self):
        """High mean runtime_risk → low health score."""
        from api.analytics_quality import _calculate_runtime_risk_score

        # All files near max risk → health near 0
        risk_map = {"a.py": 0.9, "b.py": 0.8, "c.py": 0.95}
        score = _calculate_runtime_risk_score(risk_map)
        assert score < 20.0, f"Expected low health for high risk, got {score}"

    def test_zero_risk_yields_100_health(self):
        """Zero risk across all files → perfect health of 100."""
        from api.analytics_quality import _calculate_runtime_risk_score

        risk_map = {"a.py": 0.0, "b.py": 0.0}
        assert _calculate_runtime_risk_score(risk_map) == 100.0

    def test_health_inversion_formula(self):
        """score == 100 * (1 - mean(risk)) for non-empty map."""
        from api.analytics_quality import _calculate_runtime_risk_score

        risk_map = {"x.py": 0.4, "y.py": 0.6}
        expected = 100.0 * (1.0 - 0.5)  # mean = 0.5
        assert abs(_calculate_runtime_risk_score(risk_map) - expected) < 1e-9

    def test_single_file_uses_that_value(self):
        from api.analytics_quality import _calculate_runtime_risk_score

        risk_map = {"solo.py": 0.3}
        expected = 100.0 * (1.0 - 0.3)
        assert abs(_calculate_runtime_risk_score(risk_map) - expected) < 1e-9


class TestDrillDownRuntimeRisk:
    """Tests for the runtime_risk drill-down path (#11184)."""

    @pytest.mark.asyncio
    async def test_returns_top_files_sorted_desc(self):
        """drill-down returns files sorted by runtime_risk descending."""
        risk_map = {"low.py": 0.1, "high.py": 0.9, "mid.py": 0.5}

        with patch("code_analysis.src.runtime_risk.build_runtime_risk_map", new=AsyncMock(return_value=risk_map)):
            from api import analytics_quality as aq

            result = await aq._drill_down_runtime_risk(limit=10)

        assert result["status"] == "success"
        files = result["files"]
        assert len(files) == 3
        risks = [f["runtime_risk"] for f in files]
        assert risks == sorted(risks, reverse=True)
        assert files[0]["file"] == "high.py"

    @pytest.mark.asyncio
    async def test_empty_map_returns_no_data(self):
        """Empty risk map yields no_data response, not a crash."""
        with patch("code_analysis.src.runtime_risk.build_runtime_risk_map", new=AsyncMock(return_value={})):
            from api import analytics_quality as aq

            result = await aq._drill_down_runtime_risk()

        assert result["status"] == "no_data"

    @pytest.mark.asyncio
    async def test_limit_is_respected(self):
        """Only `limit` top files are returned."""
        risk_map = {f"file{i}.py": i / 100.0 for i in range(20)}

        with patch("code_analysis.src.runtime_risk.build_runtime_risk_map", new=AsyncMock(return_value=risk_map)):
            from api import analytics_quality as aq

            result = await aq._drill_down_runtime_risk(limit=5)

        assert len(result["files"]) == 5
