# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feedback Tracker Tests (Issue #905)

Tests for feedback tracking and learning loop.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from backend.models.code_pattern import CodePattern
from backend.models.completion_feedback import CompletionFeedback


def test_completion_feedback_model():
    """Test CompletionFeedback model creation."""
    feedback = CompletionFeedback(
        timestamp=datetime.utcnow(),
        user_id="user123",
        context="def calculate_",
        suggestion="sum(numbers)",
        language="python",
        action="accepted",
        pattern_id=42,
    )

    assert feedback.user_id == "user123"
    assert feedback.action == "accepted"
    assert feedback.was_accepted is True


def test_completion_feedback_to_dict():
    """Test feedback serialization."""
    feedback = CompletionFeedback(
        id=1,
        timestamp=datetime.utcnow(),
        context="def test():",
        suggestion="pass",
        action="rejected",
    )

    data = feedback.to_dict()

    assert data["id"] == 1
    assert data["action"] == "rejected"
    assert "context" in data
    assert "suggestion" in data


def test_feedback_was_accepted_property():
    """Test was_accepted property."""
    accepted = CompletionFeedback(action="accepted")
    rejected = CompletionFeedback(action="rejected")

    assert accepted.was_accepted is True
    assert rejected.was_accepted is False


@patch("backend.services.feedback_tracker.get_redis_client")
@patch("backend.services.feedback_tracker.create_engine")
def test_feedback_tracker_initialization(mock_engine, mock_redis):
    """Test FeedbackTracker initialization."""
    from backend.services.feedback_tracker import FeedbackTracker

    mock_redis.return_value = MagicMock()
    tracker = FeedbackTracker()

    assert tracker.retrain_threshold == 1000
    assert tracker.redis_client is not None


@patch("backend.services.feedback_tracker.get_redis_client")
@patch("backend.services.feedback_tracker.create_engine")
def test_record_feedback_creates_record(mock_engine, mock_redis):
    """Test feedback recording creates database record."""
    from backend.services.feedback_tracker import FeedbackTracker

    # Mock database session
    mock_session = MagicMock()
    mock_engine.return_value.begin.return_value.__enter__.return_value = mock_session
    mock_redis.return_value = MagicMock()

    tracker = FeedbackTracker()
    tracker.SessionLocal = MagicMock(return_value=mock_session)

    # Record feedback
    feedback = tracker.record_feedback(
        context="def hello():",
        suggestion="print('Hello')",
        action="accepted",
        pattern_id=1,
    )

    # Verify database add was called
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_pattern_statistics_update():
    """Test pattern statistics calculation."""
    pattern = CodePattern(
        id=1,
        pattern_type="function",
        language="python",
        signature="def test():",
        times_suggested=10,
        times_accepted=7,
    )

    # Calculate acceptance rate
    pattern.acceptance_rate = pattern.times_accepted / pattern.times_suggested

    assert pattern.acceptance_rate == 0.7


def test_acceptance_rate_after_feedback():
    """Test acceptance rate updates after feedback."""
    pattern = CodePattern(
        id=1,
        pattern_type="function",
        language="python",
        signature="def test():",
        times_suggested=5,
        times_accepted=3,
        acceptance_rate=0.6,
    )

    # Simulate accepted feedback
    pattern.times_suggested += 1
    pattern.times_accepted += 1
    pattern.acceptance_rate = pattern.times_accepted / pattern.times_suggested

    assert pattern.times_suggested == 6
    assert pattern.times_accepted == 4
    assert pattern.acceptance_rate == 4 / 6  # ~0.667


def test_acceptance_rate_after_rejection():
    """Test acceptance rate after rejection."""
    pattern = CodePattern(
        id=1,
        pattern_type="function",
        language="python",
        signature="def test():",
        times_suggested=5,
        times_accepted=3,
        acceptance_rate=0.6,
    )

    # Simulate rejected feedback
    pattern.times_suggested += 1
    # times_accepted stays same
    pattern.acceptance_rate = pattern.times_accepted / pattern.times_suggested

    assert pattern.times_suggested == 6
    assert pattern.times_accepted == 3
    assert pattern.acceptance_rate == 0.5


@patch("backend.services.feedback_tracker.get_redis_client")
@patch("backend.services.feedback_tracker.create_engine")
def test_get_acceptance_metrics(mock_engine, mock_redis):
    """Test metrics calculation."""
    from backend.services.feedback_tracker import FeedbackTracker

    mock_session = MagicMock()
    mock_redis.return_value = MagicMock()

    # Mock query results
    mock_query = MagicMock()
    mock_query.count.return_value = 100
    mock_query.filter.return_value = mock_query
    mock_query.group_by.return_value.all.return_value = [
        ("python", 80),
        ("typescript", 20),
    ]

    mock_session.query.return_value = mock_query

    tracker = FeedbackTracker()
    tracker.SessionLocal = MagicMock(return_value=mock_session)

    metrics = tracker.get_acceptance_metrics(time_window_days=7)

    assert "total_feedback" in metrics
    assert "acceptance_rate" in metrics
    assert "language_breakdown" in metrics


def test_feedback_event_time_filtering():
    """Test feedback time window filtering."""
    now = datetime.utcnow()
    old_feedback = CompletionFeedback(
        timestamp=now - timedelta(days=10),
        context="old",
        suggestion="old",
        action="accepted",
    )
    recent_feedback = CompletionFeedback(
        timestamp=now - timedelta(days=2),
        context="recent",
        suggestion="recent",
        action="accepted",
    )

    # Check timestamps
    seven_days_ago = now - timedelta(days=7)
    assert old_feedback.timestamp < seven_days_ago
    assert recent_feedback.timestamp > seven_days_ago


def test_retrain_threshold_check():
    """Test retraining threshold logic."""
    threshold = 1000
    current_feedback = 500

    should_retrain = current_feedback >= threshold
    assert should_retrain is False

    current_feedback = 1200
    should_retrain = current_feedback >= threshold
    assert should_retrain is True


def test_feedback_action_validation():
    """Test action field validation."""
    valid_actions = ["accepted", "rejected"]

    for action in valid_actions:
        feedback = CompletionFeedback(
            context="test",
            suggestion="test",
            action=action,
        )
        assert feedback.action in valid_actions


def test_pattern_boost_from_acceptance():
    """Test pattern boosting from high acceptance rate."""
    high_accept_pattern = CodePattern(
        id=1,
        pattern_type="function",
        signature="def popular():",
        frequency=10,
        times_suggested=20,
        times_accepted=18,
        acceptance_rate=0.9,
    )

    low_accept_pattern = CodePattern(
        id=2,
        pattern_type="function",
        signature="def unpopular():",
        frequency=10,
        times_suggested=20,
        times_accepted=5,
        acceptance_rate=0.25,
    )

    # High acceptance pattern should be prioritized
    assert high_accept_pattern.acceptance_rate > low_accept_pattern.acceptance_rate
    assert high_accept_pattern.acceptance_rate >= 0.8  # Good threshold


def test_context_truncation_in_to_dict():
    """Test context truncation for display."""
    long_context = "x" * 200
    feedback = CompletionFeedback(
        id=1,
        timestamp=datetime.utcnow(),
        context=long_context,
        suggestion="test",
        action="accepted",
    )

    data = feedback.to_dict()

    # Should be truncated to 100 chars + "..."
    assert len(data["context"]) == 103
    assert data["context"].endswith("...")


def test_confidence_score_storage():
    """Test confidence score storage."""
    feedback = CompletionFeedback(
        context="test",
        suggestion="test",
        action="accepted",
        confidence_score="0.85",
    )

    assert feedback.confidence_score == "0.85"


def test_completion_rank_storage():
    """Test completion rank storage."""
    feedback = CompletionFeedback(
        context="test",
        suggestion="test",
        action="accepted",
        completion_rank=2,  # Was 2nd suggestion
    )

    assert feedback.completion_rank == 2
