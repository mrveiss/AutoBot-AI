# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for exponential_backoff_delay helper.

Issue #3565: Verify that exponential_backoff_delay applies a cap and produces
correct base-2 values.
"""

from constants.threshold_constants import RetryConfig, exponential_backoff_delay


class TestExponentialBackoffDelay:
    """Unit tests for exponential_backoff_delay."""

    def test_base_values_with_default_base(self):
        """attempt=0 → 1s, attempt=1 → 2s, attempt=2 → 4s, attempt=3 → 8s."""
        assert exponential_backoff_delay(0) == 1.0
        assert exponential_backoff_delay(1) == 2.0
        assert exponential_backoff_delay(2) == 4.0
        assert exponential_backoff_delay(3) == 8.0

    def test_cap_is_applied(self):
        """High attempt numbers must not exceed the cap."""
        cap = 60.0
        # 2**10 = 1024, well above the default cap of 60
        assert exponential_backoff_delay(10) == cap
        assert exponential_backoff_delay(30) == cap

    def test_cap_boundary(self):
        """Value exactly at the cap should be returned unchanged."""
        # 2**5 = 32 < 60; first attempt to exceed: 2**6 = 64 > 60
        assert exponential_backoff_delay(5) == 32.0
        assert exponential_backoff_delay(6) == 60.0  # capped from 64

    def test_custom_cap(self):
        """Custom cap is respected."""
        assert exponential_backoff_delay(10, cap=10.0) == 10.0
        assert exponential_backoff_delay(3, cap=10.0) == 8.0  # 2**3=8 < 10

    def test_custom_base(self):
        """Custom base is respected."""
        assert exponential_backoff_delay(3, base=3.0, cap=1000.0) == 27.0

    def test_return_type_is_float(self):
        """Return value must always be a float."""
        result = exponential_backoff_delay(0)
        assert isinstance(result, float)

    def test_default_cap_matches_retry_config(self):
        """Default cap must match RetryConfig.BACKOFF_MAX_DELAY for consistency."""
        default_cap = RetryConfig.BACKOFF_MAX_DELAY  # 60.0
        # At a large attempt the helper must be capped at BACKOFF_MAX_DELAY
        assert exponential_backoff_delay(100) == default_cap
