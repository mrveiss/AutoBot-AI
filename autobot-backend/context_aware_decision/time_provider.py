# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Time Provider Utility

Provides time-related utilities for the context-aware decision system.
Reduces Feature Envy by centralizing time operations.

Part of Issue #381 - God Class Refactoring
"""

import time
from datetime import datetime
from typing import Any, Dict


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
        return datetime.now()

    @staticmethod
    def is_business_hours() -> bool:
        """Check if current time is within business hours (9 AM - 5 PM)."""
        current_hour = datetime.now().hour
        return 9 <= current_hour <= 17

    @staticmethod
    def is_weekend() -> bool:
        """Check if current day is weekend."""
        return datetime.now().weekday() >= 5

    @staticmethod
    def get_temporal_context_data() -> Dict[str, Any]:
        """Get comprehensive temporal context data."""
        current_time = datetime.now()
        return {
            "timestamp": time.time(),
            "datetime": current_time.isoformat(),
            "hour": current_time.hour,
            "day_of_week": current_time.weekday(),
            "is_business_hours": 9 <= current_time.hour <= 17,
            "is_weekend": current_time.weekday() >= 5,
        }
