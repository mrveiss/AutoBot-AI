# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Error Budget Tracking

Issue #4342: Track per-component error budgets.
Components must maintain >95% success rate.
"""

import time

from services.resilience.error_budget import (
    ErrorBudget,
    ErrorBudgetTracker,
)


class TestErrorBudget:
    """Test suite for error budget."""

    def test_budget_initial_state(self):
        """Test initial state of error budget."""
        budget = ErrorBudget(component="redis")
        assert budget.success_rate == 1.0
        assert budget.has_budget is True
        assert budget.failed_requests == 0
        assert budget.total_requests == 0

    def test_budget_success_rate_calculation(self):
        """Test success rate calculation."""
        budget = ErrorBudget(component="redis")

        # 3 successes, 1 failure = 75% success rate
        budget.record_success()
        budget.record_success()
        budget.record_success()
        budget.record_failure()

        assert budget.success_rate == 0.75
        assert budget.total_requests == 4

    def test_budget_exhaustion(self):
        """Test that budget is exhausted when success rate drops."""
        budget = ErrorBudget(component="api")

        # Record 5 successes and 5 failures = 50% success rate
        for _ in range(5):
            budget.record_success()
            budget.record_failure()

        assert budget.success_rate == 0.5
        assert budget.has_budget is False

    def test_budget_recovery_above_threshold(self):
        """Test that budget recovers when success rate exceeds threshold."""
        budget = ErrorBudget(component="redis", min_success_rate=0.95)

        # Record 19 successes and 1 failure = 95% success rate
        for _ in range(19):
            budget.record_success()
        budget.record_failure()

        assert budget.success_rate >= 0.95
        assert budget.has_budget is True

    def test_budget_window_expiration(self):
        """Test that budget window expires and resets."""
        budget = ErrorBudget(
            component="api",
            budget_window_seconds=0.1,  # Very short window
        )

        # Exhaust budget
        for _ in range(10):
            budget.record_failure()

        assert budget.has_budget is False

        # Wait for window to expire
        time.sleep(0.15)

        assert budget.is_expired is True

        # Reset and check
        budget.reset()
        assert budget.success_rate == 1.0
        assert budget.has_budget is True


class TestErrorBudgetTracker:
    """Test suite for error budget tracker."""

    def test_tracker_creates_budget_on_demand(self):
        """Test that tracker creates budget on first access."""
        tracker = ErrorBudgetTracker()

        budget1 = tracker.get_budget("redis")
        budget2 = tracker.get_budget("redis")

        assert budget1 is budget2
        assert budget1.component == "redis"

    def test_tracker_records_success(self):
        """Test that tracker records successful requests."""
        tracker = ErrorBudgetTracker()

        tracker.record_success("redis")
        tracker.record_success("redis")

        budget = tracker.get_budget("redis")
        assert budget.total_requests == 2
        assert budget.failed_requests == 0

    def test_tracker_records_failure(self):
        """Test that tracker records failed requests."""
        tracker = ErrorBudgetTracker()

        tracker.record_failure("redis")
        tracker.record_failure("redis")

        budget = tracker.get_budget("redis")
        assert budget.failed_requests == 2
        assert budget.total_requests == 2

    def test_tracker_tracks_multiple_components(self):
        """Test that tracker tracks multiple components."""
        tracker = ErrorBudgetTracker()

        # Redis: 9 successes, 1 failure = 90% (no budget)
        for _ in range(9):
            tracker.record_success("redis")
        tracker.record_failure("redis")

        # API: 19 successes, 1 failure = 95% (has budget)
        for _ in range(19):
            tracker.record_success("api")
        tracker.record_failure("api")

        assert tracker.has_budget("redis") is False
        assert tracker.has_budget("api") is True

    def test_tracker_has_budget_check(self):
        """Test has_budget check method."""
        tracker = ErrorBudgetTracker()

        # Initially has budget
        assert tracker.has_budget("redis") is True

        # Exhaust budget
        for _ in range(100):
            tracker.record_failure("redis")

        assert tracker.has_budget("redis") is False

    def test_tracker_status(self):
        """Test tracker status report."""
        tracker = ErrorBudgetTracker()

        tracker.record_success("redis")
        tracker.record_success("redis")
        tracker.record_failure("redis")

        status = tracker.get_status()
        assert "redis" in status
        assert status["redis"]["total_requests"] == 3
        assert status["redis"]["failed_requests"] == 1

    def test_tracker_reset_budget(self):
        """Test tracker budget reset."""
        tracker = ErrorBudgetTracker()

        # Exhaust budget
        for _ in range(100):
            tracker.record_failure("redis")

        assert tracker.has_budget("redis") is False

        # Reset
        tracker.reset_budget("redis")
        assert tracker.has_budget("redis") is True


class TestGracefulDegradation:
    """Test graceful degradation based on error budgets."""

    def test_component_enters_minimal_mode_when_budget_exhausted(self):
        """Test that component degrades when budget exhausted."""
        tracker = ErrorBudgetTracker(window_seconds=3600)

        def operate_with_degradation(component):
            if tracker.has_budget(component):
                return "full_functionality"
            else:
                return "degraded_mode"

        # Initially has budget
        assert operate_with_degradation("redis") == "full_functionality"

        # Exhaust budget
        for _ in range(100):
            tracker.record_failure("redis")

        # Now in degraded mode
        assert operate_with_degradation("redis") == "degraded_mode"

    def test_multiple_component_degradation(self):
        """Test degradation of multiple components independently."""
        tracker = ErrorBudgetTracker()

        # Exhaust only redis budget
        for _ in range(100):
            tracker.record_failure("redis")

        # Keep api healthy
        for _ in range(10):
            tracker.record_success("api")

        assert tracker.has_budget("redis") is False
        assert tracker.has_budget("api") is True

    def test_budget_window_reset_restores_full_functionality(self):
        """Test that window reset restores full functionality."""
        tracker = ErrorBudgetTracker(window_seconds=0.1)

        # Exhaust budget
        for _ in range(100):
            tracker.record_failure("redis")

        assert tracker.has_budget("redis") is False

        # Wait for window to expire
        time.sleep(0.15)

        # Window expired, check again (triggers reset)
        assert tracker.has_budget("redis") is True


class TestErrorBudgetIntegration:
    """Integration tests for error budgets."""

    def test_redis_component_budget(self):
        """Test Redis component maintaining error budget."""
        tracker = ErrorBudgetTracker()

        # Simulate 95 successes and 5 failures = 95% success rate
        for _ in range(95):
            tracker.record_success("redis")
        for _ in range(5):
            tracker.record_failure("redis")

        assert tracker.has_budget("redis") is True

    def test_chromadb_component_budget(self):
        """Test ChromaDB component error budget."""
        tracker = ErrorBudgetTracker()

        # Simulate 80 successes and 20 failures = 80% success rate
        for _ in range(80):
            tracker.record_success("chromadb")
        for _ in range(20):
            tracker.record_failure("chromadb")

        assert tracker.has_budget("chromadb") is False

    def test_external_api_budget(self):
        """Test external API component error budget."""
        tracker = ErrorBudgetTracker()

        # Simulate 98 successes and 2 failures = 98% success rate
        for _ in range(98):
            tracker.record_success("external_api")
        for _ in range(2):
            tracker.record_failure("external_api")

        assert tracker.has_budget("external_api") is True
