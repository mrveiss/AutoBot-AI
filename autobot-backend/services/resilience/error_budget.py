# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Error Budget Tracking Module

Issue #4342: Track per-component error budgets.
Component must maintain >95% success rate to stay operational.
When budget exhausted, component enters minimal-feature mode.
"""

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@dataclass
class ErrorBudget:
    """Error budget for a component."""

    component: str
    total_requests: int = 0
    failed_requests: int = 0
    created_at: float = field(default_factory=time.time)
    budget_window_seconds: float = 3600.0  # 1 hour window
    min_success_rate: float = 0.95  # 95% success required

    @property
    def success_rate(self) -> float:
        """Calculate current success rate."""
        if self.total_requests == 0:
            return 1.0
        return (self.total_requests - self.failed_requests) / self.total_requests

    @property
    def has_budget(self) -> bool:
        """Check if component still has error budget."""
        return self.success_rate >= self.min_success_rate

    @property
    def is_expired(self) -> bool:
        """Check if budget window has expired."""
        return (time.time() - self.created_at) > self.budget_window_seconds

    def record_success(self) -> None:
        """Record successful request."""
        self.total_requests += 1

    def record_failure(self) -> None:
        """Record failed request."""
        self.total_requests += 1
        self.failed_requests += 1

    def reset(self) -> None:
        """Reset budget window."""
        self.total_requests = 0
        self.failed_requests = 0
        self.created_at = time.time()


class ErrorBudgetTracker:
    """Tracks error budgets for multiple components."""

    def __init__(self, window_seconds: float = 3600.0) -> None:
        """
        Initialize error budget tracker.

        Args:
            window_seconds: Budget window duration (default: 1 hour)
        """
        self.budgets: Dict[str, ErrorBudget] = {}
        self.window_seconds = window_seconds
        self._lock = Lock()

    def get_budget(self, component: str) -> ErrorBudget:
        """Get or create error budget for component."""
        with self._lock:
            if component not in self.budgets:
                self.budgets[component] = ErrorBudget(
                    component=component,
                    budget_window_seconds=self.window_seconds,
                )
            return self.budgets[component]

    def record_success(self, component: str) -> None:
        """Record successful request for component."""
        budget = self.get_budget(component)
        if budget.is_expired:
            budget.reset()
        with self._lock:
            budget.record_success()

    def record_failure(self, component: str) -> None:
        """Record failed request for component."""
        budget = self.get_budget(component)
        if budget.is_expired:
            budget.reset()
        with self._lock:
            budget.record_failure()

            if not budget.has_budget:
                logger.warning(
                    "Component %s exhausted error budget (%.1f%% success rate)",
                    component,
                    budget.success_rate * 100,
                )

    def has_budget(self, component: str) -> bool:
        """Check if component has remaining error budget."""
        budget = self.get_budget(component)
        with self._lock:
            if budget.is_expired:
                budget.reset()
                return True
            return budget.has_budget

    def get_status(self) -> Dict[str, Dict[str, float]]:
        """Get status of all error budgets."""
        with self._lock:
            return {
                component: {
                    "success_rate": budget.success_rate,
                    "total_requests": budget.total_requests,
                    "failed_requests": budget.failed_requests,
                    "has_budget": budget.has_budget,
                }
                for component, budget in self.budgets.items()
            }

    def reset_budget(self, component: str) -> None:
        """Reset error budget for component."""
        budget = self.get_budget(component)
        with self._lock:
            budget.reset()
            logger.info("Error budget reset for component %s", component)


_global_tracker = None
_tracker_lock = Lock()


def get_error_budget_tracker(window_seconds: float = 3600.0) -> ErrorBudgetTracker:
    """Get global error budget tracker instance (singleton)."""
    global _global_tracker
    if _global_tracker is None:
        with _tracker_lock:
            if _global_tracker is None:
                _global_tracker = ErrorBudgetTracker(window_seconds)
    return _global_tracker
