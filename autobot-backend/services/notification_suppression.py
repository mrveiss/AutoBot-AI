"""
GitHub Notification Suppression Service

Automatically suppresses CI/CD failure notifications to reduce inbox clutter.
Implements multi-tiered filtering for actionable vs. noise notifications.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso

logger = get_logger(__name__)


class NotificationReason(str, Enum):
    """GitHub notification reason types."""

    AUTHOR = "author"
    REVIEW_REQUESTED = "review_requested"
    MENTION = "mention"
    STATE_CHANGE = "state_change"
    CI_ACTIVITY = "ci_activity"
    SUBSCRIBED = "subscribed"


@dataclass
class NotificationFilter:
    """Configuration for notification filtering."""

    reason: NotificationReason
    action: str  # "archive", "keep", "review"
    description: str
    max_age_days: int | None = None  # Archive if older than N days


class NotificationSuppressionConfig:
    """Configuration for notification suppression rules."""

    # Default filters - suppress CI noise, keep actionable items
    DEFAULT_FILTERS = [
        NotificationFilter(
            reason=NotificationReason.CI_ACTIVITY,
            action="archive",
            description="Workflow failures, check suite results",
            max_age_days=7,
        ),
        NotificationFilter(
            reason=NotificationReason.AUTHOR,
            action="keep",
            description="Issues and PRs you created",
            max_age_days=None,
        ),
        NotificationFilter(
            reason=NotificationReason.REVIEW_REQUESTED,
            action="keep",
            description="Code reviews requested from you",
            max_age_days=None,
        ),
        NotificationFilter(
            reason=NotificationReason.MENTION,
            action="keep",
            description="Direct mentions in issues/PRs",
            max_age_days=None,
        ),
        NotificationFilter(
            reason=NotificationReason.STATE_CHANGE,
            action="review",
            description="PR merged/closed, issue status changes",
            max_age_days=30,
        ),
        NotificationFilter(
            reason=NotificationReason.SUBSCRIBED,
            action="archive",
            description="Background subscriptions",
            max_age_days=14,
        ),
    ]

    def __init__(self, filters: List[NotificationFilter] | None = None) -> None:
        """Initialize with custom or default filters."""
        self.filters = filters or self.DEFAULT_FILTERS
        self._filter_map = {f.reason: f for f in self.filters}

    def should_suppress(self, reason: NotificationReason, age_days: int) -> bool:
        """Determine if a notification should be suppressed."""
        filter_config = self._filter_map.get(reason)
        if not filter_config:
            return False

        if filter_config.action == "keep":
            return False

        # Archive old notifications even if action is "review"
        if filter_config.max_age_days and age_days > filter_config.max_age_days:
            return True

        return filter_config.action == "archive"

    def get_filter(self, reason: NotificationReason) -> NotificationFilter | None:
        """Get filter configuration for a reason."""
        return self._filter_map.get(reason)


class NotificationSuppressionManager:
    """Manager for suppressing CI notifications via GitHub API."""

    def __init__(self, config: NotificationSuppressionConfig | None = None) -> None:
        """Initialize with suppression configuration."""
        self.config = config or NotificationSuppressionConfig()
        self.suppressed_count = 0
        self.kept_count = 0

    def classify_notification(self, reason: str, updated_at: str) -> tuple[bool, str]:
        """
        Classify a notification and determine if it should be suppressed.

        Returns:
            (should_suppress, reason_description)
        """
        try:
            reason_enum = NotificationReason(reason)
        except ValueError:
            logger.warning(f"Unknown notification reason: {reason}")
            return False, f"unknown reason: {reason}"

        filter_config = self.config.get_filter(reason_enum)
        if not filter_config:
            return False, "no filter configured"

        # Calculate age
        try:
            updated = parse_utc_iso(updated_at)
            now = datetime.now(updated.tzinfo)
            age_days = (now - updated).days
        except (ValueError, TypeError):
            age_days = 0

        should_suppress = self.config.should_suppress(reason_enum, age_days)

        if should_suppress:
            self.suppressed_count += 1
            action = filter_config.action
            return True, f"{action} ({age_days} days old)"
        else:
            self.kept_count += 1
            return False, f"keep ({filter_config.description})"

    def get_summary(self) -> dict:
        """Get suppression statistics."""
        total = self.suppressed_count + self.kept_count
        return {
            "total_processed": total,
            "suppressed": self.suppressed_count,
            "kept": self.kept_count,
            "suppression_rate": (f"{100 * self.suppressed_count / total:.1f}%" if total > 0 else "0%"),
        }
