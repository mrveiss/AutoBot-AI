# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Time Provider Utility

Provides time-related utilities for the context-aware decision system.
Reduces Feature Envy by centralizing time operations.

Part of Issue #381 - God Class Refactoring
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict

from autobot_shared.time_utils import now_utc


class TimeProvider:
    """Utility class for time-related operations to reduce Feature Envy."""

    @staticmethod
    def current_timestamp() -> float:
        """Get current Unix timestamp."""
        return time.time()

    @staticmethod
    def current_timestamp_millis() -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    @staticmethod
    def current_datetime() -> datetime:
        """Get current datetime object."""
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def is_business_hours() -> bool:
        """Check if current time is within business hours (9 AM - 5 PM UTC)."""
        return 9 <= now_utc().hour <= 17

    @staticmethod
    def is_weekend() -> bool:
        """Check if current day is weekend (UTC)."""
        return now_utc().weekday() >= 5

    @staticmethod
    def get_temporal_context_data() -> Dict[str, Any]:
        """Get comprehensive temporal context data."""
        current_time_utc = now_utc()
        return {
            "timestamp": time.time(),
            "datetime": current_time_utc.isoformat(),
            "hour": current_time_utc.hour,
            "day_of_week": current_time_utc.weekday(),
            "is_business_hours": 9 <= current_time_utc.hour <= 17,
            "is_weekend": current_time_utc.weekday() >= 5,
        }
