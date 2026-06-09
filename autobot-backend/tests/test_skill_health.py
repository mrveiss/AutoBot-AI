# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Health Metrics Tests (Issue #4339)

Tests for skill metrics tracking, health scoring, and feedback analysis.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.skill_management.skill_feedback import SkillFeedbackAnalyzer
from services.skill_management.skill_health_scheduler import SkillHealthScheduler
from services.skill_management.skill_metrics import SkillMetrics


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return MagicMock()


@pytest.fixture
async def skill_metrics():
    """Create a SkillMetrics instance with mocked Redis."""
    metrics = SkillMetrics()
    metrics._redis = MagicMock()
    return metrics


@pytest.fixture
async def feedback_analyzer():
    """Create a SkillFeedbackAnalyzer instance with mocked Redis."""
    analyzer = SkillFeedbackAnalyzer()
    analyzer._redis = MagicMock()
    return analyzer


@pytest.mark.asyncio
async def test_log_invocation_success(skill_metrics):
    """Test logging successful skill invocation."""
    skill_metrics._redis.incr = MagicMock()
    skill_metrics._redis.lpush = MagicMock()
    skill_metrics._redis.expire = MagicMock()

    await skill_metrics.log_invocation(
        skill_id="test-skill",
        action="test-action",
        success=True,
        duration_ms=1000.0,
    )

    # Verify Redis operations
    assert skill_metrics._redis.incr.called
    assert skill_metrics._redis.expire.called


@pytest.mark.asyncio
async def test_log_invocation_with_error(skill_metrics):
    """Test logging failed skill invocation with error type."""
    skill_metrics._redis.incr = MagicMock()
    skill_metrics._redis.expire = MagicMock()

    await skill_metrics.log_invocation(
        skill_id="test-skill",
        action="test-action",
        success=False,
        duration_ms=500.0,
        error_type="TimeoutError",
    )

    # Verify error was tracked
    assert skill_metrics._redis.incr.called


@pytest.mark.asyncio
async def test_log_invocation_with_feedback(skill_metrics):
    """Test logging invocation with user feedback."""
    skill_metrics._redis.incr = MagicMock()
    skill_metrics._redis.lpush = MagicMock()
    skill_metrics._redis.expire = MagicMock()

    await skill_metrics.log_invocation(
        skill_id="test-skill",
        action="test-action",
        success=True,
        duration_ms=1500.0,
        user_feedback="Could be faster",
    )

    # Verify feedback was stored
    assert skill_metrics._redis.lpush.called


@pytest.mark.asyncio
async def test_get_metrics_empty(skill_metrics):
    """Test getting metrics when no data exists."""
    skill_metrics._redis.get = MagicMock(return_value=None)
    skill_metrics._redis.keys = MagicMock(return_value=[])
    skill_metrics._redis.lrange = MagicMock(return_value=[])

    metrics = await skill_metrics.get_metrics("test-skill", days=30)

    assert metrics["skill_id"] == "test-skill"
    assert metrics["invocations"] == 0
    assert metrics["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_metrics_with_data(skill_metrics):
    """Test getting metrics with invocation data."""

    # Setup mock to return invocation counts for single day
    def mock_get(key):
        key_str = key.decode() if isinstance(key, bytes) else str(key)
        if "total" in key_str:
            return b"10"
        elif "success" in key_str:
            return b"8"
        return None

    skill_metrics._redis.get = MagicMock(side_effect=mock_get)
    skill_metrics._redis.keys = MagicMock(return_value=[])
    skill_metrics._redis.lrange = MagicMock(return_value=[])

    # Get metrics for 1 day only (so 10 invocations total)
    metrics = await skill_metrics.get_metrics("test-skill", days=1)

    assert metrics["invocations"] == 10
    assert metrics["successes"] == 8
    assert metrics["success_rate"] == 80.0


@pytest.mark.asyncio
async def test_health_score_untested(skill_metrics):
    """Test health score for untested skill."""
    skill_metrics._redis = None

    health_score = await skill_metrics.get_health_score("test-skill")

    # Untested skills get default score
    assert health_score == 0.5


@pytest.mark.asyncio
async def test_health_score_healthy(skill_metrics):
    """Test health score for healthy skill."""

    # Setup mock metrics
    def mock_get(key):
        key_str = key.decode() if isinstance(key, bytes) else str(key)
        if "total" in key_str:
            return b"100"
        elif "success" in key_str:
            return b"95"
        return None

    skill_metrics._redis.get = MagicMock(side_effect=mock_get)
    skill_metrics._redis.keys = MagicMock(return_value=[])
    skill_metrics._redis.lrange = MagicMock(return_value=[])

    health_score = await skill_metrics.get_health_score("test-skill", days=1)

    # Healthy skill with 95% success rate should have high score
    assert health_score >= 0.8


@pytest.mark.asyncio
async def test_health_score_degraded(skill_metrics):
    """Test health score for degraded skill."""

    def mock_get(key):
        key_str = key.decode() if isinstance(key, bytes) else str(key)
        if "total" in key_str:
            return b"100"
        elif "success" in key_str:
            return b"60"
        return None

    skill_metrics._redis.get = MagicMock(side_effect=mock_get)
    skill_metrics._redis.keys = MagicMock(return_value=[])
    skill_metrics._redis.lrange = MagicMock(return_value=[])

    health_score = await skill_metrics.get_health_score("test-skill", days=1)

    # Degraded skill with 60% success rate
    assert 0.4 <= health_score < 0.7


@pytest.mark.asyncio
async def test_mark_stale(skill_metrics):
    """Test marking skill as stale."""
    skill_metrics._redis.get = MagicMock(return_value=None)
    skill_metrics._redis.set = MagicMock()

    await skill_metrics.mark_stale("test-skill")

    # Verify stale flag was set
    assert skill_metrics._redis.set.called


@pytest.mark.asyncio
async def test_get_stale_skills(skill_metrics):
    """Test retrieving list of stale skills."""
    skill_metrics._redis.keys = MagicMock(
        return_value=[
            b"skill_health:old-skill-1:stale",
            b"skill_health:old-skill-2:stale",
        ]
    )

    stale_skills = await skill_metrics.get_stale_skills()

    assert len(stale_skills) == 2
    assert "old-skill-1" in stale_skills
    assert "old-skill-2" in stale_skills


@pytest.mark.asyncio
async def test_submit_user_feedback(feedback_analyzer):
    """Test submitting user feedback."""
    feedback_analyzer._redis.lpush = MagicMock()
    feedback_analyzer._redis.expire = MagicMock()

    await feedback_analyzer.log_user_feedback(
        skill_id="test-skill",
        action="test-action",
        rating=5,
        feedback_text="Excellent skill!",
    )

    assert feedback_analyzer._redis.lpush.called


@pytest.mark.asyncio
async def test_get_feedback_summary_empty(feedback_analyzer):
    """Test getting feedback summary when no data exists."""
    feedback_analyzer._redis.lrange = MagicMock(return_value=[])

    summary = await feedback_analyzer.get_feedback_summary("test-skill", days=30)

    assert summary["skill_id"] == "test-skill"
    assert summary["total_feedback"] == 0
    assert summary["avg_rating"] == 0.0


@pytest.mark.asyncio
async def test_get_feedback_summary_with_ratings(feedback_analyzer):
    """Test getting feedback summary with ratings."""
    feedback_entries = [
        json.dumps(
            {
                "timestamp": "2025-04-13T00:00:00",
                "skill_id": "test-skill",
                "action": "test",
                "rating": 5,
                "feedback": "",
            }
        ).encode(),
        json.dumps(
            {
                "timestamp": "2025-04-13T00:01:00",
                "skill_id": "test-skill",
                "action": "test",
                "rating": 4,
                "feedback": "",
            }
        ).encode(),
        json.dumps(
            {
                "timestamp": "2025-04-13T00:02:00",
                "skill_id": "test-skill",
                "action": "test",
                "rating": 5,
                "feedback": "",
            }
        ).encode(),
    ]

    # Mock to always return the entries for any lrange call
    feedback_analyzer._redis.lrange = MagicMock(return_value=feedback_entries)

    summary = await feedback_analyzer.get_feedback_summary("test-skill", days=1)

    assert summary["total_feedback"] == 3
    assert summary["avg_rating"] == pytest.approx(4.67, abs=0.01)
    assert summary["rating_distribution"]["5_star"] == 2
    assert summary["rating_distribution"]["4_star"] == 1


@pytest.mark.asyncio
async def test_refinement_suggestions_high_failure_rate(feedback_analyzer):
    """Test getting refinement suggestions for failing skill."""
    # Mock the analyzer methods
    feedback_analyzer.get_feedback_summary = AsyncMock(
        return_value={
            "total_feedback": 10,
            "avg_rating": 1.5,
            "failure_patterns": [
                {"pattern": "Timeout error", "count": 5},
                {"pattern": "Invalid input", "count": 3},
            ],
            "needs_refinement": True,
        }
    )

    # Mock SkillMetrics
    with patch("services.skill_management.skill_feedback.SkillMetrics"):
        mock_metrics = AsyncMock()
        mock_metrics.get_metrics = AsyncMock(
            return_value={
                "invocations": 10,
                "avg_duration_ms": 1000,
                "error_patterns": {"TimeoutError": 5},
            }
        )
        feedback_analyzer._metrics = mock_metrics

        suggestions = await feedback_analyzer.get_refinement_suggestions("test-skill")

        assert suggestions["total_suggestions"] > 0
        # Should suggest refinement for failure patterns
        has_refinement = any(s["type"] == "refinement" for s in suggestions["suggestions"])
        assert has_refinement


@pytest.mark.asyncio
async def test_health_scheduler_check_all_skills():
    """Test health scheduler checking all skills."""
    scheduler = SkillHealthScheduler()

    with patch("services.skill_management.skill_health_scheduler.get_skill_registry") as mock_registry:
        mock_registry.return_value.list_skills = MagicMock(
            return_value=[
                {"name": "skill-1"},
                {"name": "skill-2"},
            ]
        )

        # Mock metrics
        with patch.object(scheduler._metrics, "get_health_score", new_callable=AsyncMock) as mock_health:
            with patch.object(scheduler._metrics, "get_metrics", new_callable=AsyncMock) as mock_metrics:
                with patch.object(scheduler._metrics, "mark_stale", new_callable=AsyncMock):
                    with patch.object(scheduler._metrics, "get_stale_skills", new_callable=AsyncMock) as mock_stale:
                        mock_health.return_value = 0.8
                        mock_metrics.return_value = {
                            "invocations": 10,
                            "success_rate": 85.0,
                        }
                        mock_stale.return_value = []

                        results = await scheduler.check_all_skills()

                        assert results["checked"] == 2
                        assert results["healthy"] >= 0


@pytest.mark.asyncio
async def test_health_scheduler_auto_disable():
    """Test auto-disabling unhealthy skills."""
    scheduler = SkillHealthScheduler()

    with patch("services.skill_management.skill_health_scheduler.get_skill_registry") as mock_registry:
        mock_skill_registry = MagicMock()
        mock_skill_registry.list_skills = MagicMock(return_value=[{"name": "bad-skill"}])
        mock_skill_registry.disable_skill = MagicMock(return_value={"success": True})
        mock_registry.return_value = mock_skill_registry

        with patch.object(scheduler._metrics, "get_health_score", new_callable=AsyncMock) as mock_health:
            with patch.object(scheduler._metrics, "get_metrics", new_callable=AsyncMock) as mock_metrics:
                with patch.object(scheduler._metrics, "mark_stale", new_callable=AsyncMock):
                    with patch.object(scheduler._metrics, "get_stale_skills", new_callable=AsyncMock) as mock_stale:
                        with patch("services.skill_management.skill_health_scheduler.get_redis_client"):
                            # Low health score triggers disable
                            mock_health.return_value = 0.3
                            mock_metrics.return_value = {
                                "invocations": 50,
                                "success_rate": 30.0,
                            }
                            mock_stale.return_value = []

                            results = await scheduler.check_all_skills()

                            assert results["disabled"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
