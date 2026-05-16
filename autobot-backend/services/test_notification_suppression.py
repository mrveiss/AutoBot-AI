"""Unit tests for notification suppression service."""

import unittest
from datetime import timedelta

from notification_suppression import (
    NotificationFilter,
    NotificationReason,
    NotificationSuppressionConfig,
    NotificationSuppressionManager,
)

from autobot_shared.time_utils import now_utc


class TestNotificationFilter(unittest.TestCase):
    """Test NotificationFilter configuration."""

    def test_filter_creation(self) -> None:
        """Test creating a notification filter."""
        filter_obj = NotificationFilter(
            reason=NotificationReason.CI_ACTIVITY,
            action="archive",
            description="CI failures",
            max_age_days=7,
        )
        self.assertEqual(filter_obj.reason, NotificationReason.CI_ACTIVITY)
        self.assertEqual(filter_obj.action, "archive")
        self.assertEqual(filter_obj.max_age_days, 7)


class TestNotificationSuppressionConfig(unittest.TestCase):
    """Test suppression configuration."""

    def setUp(self) -> None:
        """Set up test configuration."""
        self.config = NotificationSuppressionConfig()

    def test_default_filters_loaded(self) -> None:
        """Test that default filters are loaded."""
        self.assertTrue(len(self.config.filters) > 0)
        self.assertIsNotNone(self.config._filter_map[NotificationReason.CI_ACTIVITY])

    def test_should_suppress_ci_activity(self) -> None:
        """Test that old CI activity is suppressed."""
        # 10 days old, max is 7
        should_suppress = self.config.should_suppress(NotificationReason.CI_ACTIVITY, age_days=10)
        self.assertTrue(should_suppress)

    def test_should_not_suppress_recent_ci_activity(self) -> None:
        """Test that recent CI activity is not suppressed."""
        # 3 days old, max is 7
        should_suppress = self.config.should_suppress(NotificationReason.CI_ACTIVITY, age_days=3)
        self.assertFalse(should_suppress)

    def test_keep_author_notifications(self) -> None:
        """Test that author notifications are always kept."""
        should_suppress = self.config.should_suppress(NotificationReason.AUTHOR, age_days=100)
        self.assertFalse(should_suppress)

    def test_keep_review_requested(self) -> None:
        """Test that review requests are always kept."""
        should_suppress = self.config.should_suppress(NotificationReason.REVIEW_REQUESTED, age_days=100)
        self.assertFalse(should_suppress)

    def test_get_filter(self) -> None:
        """Test retrieving filter configuration."""
        filter_obj = self.config.get_filter(NotificationReason.CI_ACTIVITY)
        self.assertIsNotNone(filter_obj)
        self.assertEqual(filter_obj.action, "archive")


class TestNotificationSuppressionManager(unittest.TestCase):
    """Test suppression manager."""

    def setUp(self) -> None:
        """Set up test manager."""
        self.manager = NotificationSuppressionManager()

    def test_classify_old_ci_notification(self) -> None:
        """Test classifying an old CI notification."""
        # Create timestamp 10 days ago
        old_time = now_utc() - timedelta(days=10)
        updated_at = old_time.isoformat().replace("+00:00", "Z")

        should_suppress, reason = self.manager.classify_notification("ci_activity", updated_at)
        self.assertTrue(should_suppress)
        self.assertIn("archive", reason)

    def test_classify_author_notification(self) -> None:
        """Test classifying an author notification."""
        old_time = now_utc() - timedelta(days=100)
        updated_at = old_time.isoformat().replace("+00:00", "Z")

        should_suppress, reason = self.manager.classify_notification("author", updated_at)
        self.assertFalse(should_suppress)
        self.assertIn("keep", reason)

    def test_classify_unknown_reason(self) -> None:
        """Test classifying unknown reason."""
        now = now_utc().isoformat().replace("+00:00", "Z")
        should_suppress, reason = self.manager.classify_notification("unknown_reason", now)
        self.assertFalse(should_suppress)
        self.assertIn("unknown", reason)

    def test_get_summary(self) -> None:
        """Test getting suppression summary."""
        # Simulate some classifications
        now = now_utc().isoformat().replace("+00:00", "Z")
        self.manager.classify_notification("ci_activity", now)
        self.manager.classify_notification("author", now)

        summary = self.manager.get_summary()
        self.assertEqual(summary["total_processed"], 2)
        self.assertEqual(summary["suppressed"], 0)
        self.assertEqual(summary["kept"], 2)


if __name__ == "__main__":
    unittest.main()
