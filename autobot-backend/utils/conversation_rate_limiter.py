#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Rate Limiting Middleware for Claude API
Prevents conversation crashes by monitoring and controlling request patterns
to avoid hitting Claude API rate limits during development sessions.
"""

import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for JSON-serializable types
_JSON_SERIALIZABLE_TYPES = (list, tuple)


@dataclass
class RequestInfo:
    """Information about a single request"""

    timestamp: float
    payload_size: int
    response_time: Optional[float] = None
    success: bool = True
    error_type: Optional[str] = None


class PayloadSizeTracker:
    """Tracks payload sizes and provides optimization recommendations"""

    def __init__(self, max_safe_size: int = 30000, warning_size: int = 20000):
        """Initialize payload tracker with size thresholds and history buffer."""
        self.max_safe_size = max_safe_size
        self.warning_size = warning_size
        self.size_history = deque(maxlen=50)

    def analyze_payload(self, payload: Any) -> Dict[str, Any]:
        """Analyze payload and return size info and recommendations"""
        size = self._calculate_size(payload)
        self.size_history.append(size)

        analysis = {
            "size": size,
            "status": "safe",
            "recommendation": None,
            "average_size": (
                sum(self.size_history) / len(self.size_history)
                if self.size_history
                else 0
            ),
        }

        if size > self.max_safe_size:
            analysis["status"] = "dangerous"
            analysis["recommendation"] = "split_request"
        elif size > self.warning_size:
            analysis["status"] = "warning"
            analysis["recommendation"] = "optimize_payload"

        return analysis

    def _calculate_size(self, payload: Any) -> int:
        """Calculate approximate size of payload in bytes"""
        try:
            if isinstance(payload, str):
                return len(payload.encode("utf-8"))
            elif isinstance(payload, dict):
                return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            elif isinstance(payload, _JSON_SERIALIZABLE_TYPES):  # Issue #380
                return len(str(payload).encode("utf-8"))
            else:
                return len(str(payload).encode("utf-8"))
        except Exception as e:
            logger.warning("Failed to calculate payload size: %s", e)
            return 0


class ConversationRateLimiter:
    """
    Rate limiter specifically designed for Claude conversations to prevent API crashes.

    Features:
    - Sliding window rate limiting
    - Payload size monitoring
    - Intelligent backoff calculations
    - Usage pattern analysis
    - Early warning system
    """

    def __init__(
        self,
        requests_per_minute: int = 50,
        requests_per_hour: int = 2000,
        max_payload_size: int = 30000,
        warning_payload_size: int = 20000,
    ):
        """Initialize rate limiter with request limits and payload thresholds."""
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.max_payload_size = max_payload_size

        # Request tracking
        self.request_history = deque()
        self.payload_tracker = PayloadSizeTracker(
            max_payload_size, warning_payload_size
        )

        # Lock for thread-safe stats access
        import threading

        self._stats_lock = threading.Lock()

        # Statistics
        self.total_requests = 0
        self.blocked_requests = 0
        self.large_payload_count = 0
        self.average_response_time = 0.0

        # State management
        self.last_warning_time = 0
        self.warning_cooldown = 300  # 5 minutes between warnings

        logger.info(
            f"ConversationRateLimiter initialized: {requests_per_minute}/min, {requests_per_hour}/hour"
        )

    def can_make_request(self, payload: Any = None) -> Dict[str, Any]:
        """
        Check if a request can be made without hitting rate limits.

        Returns:
            Dict with status, can_proceed, wait_time, and recommendations
        """
        current_time = time.time()

        # Clean old requests
        self._cleanup_old_requests(current_time)

        # Check rate limits
        rate_check = self._check_rate_limits(current_time)

        # Check payload size if provided
        payload_check = {"status": "safe", "recommendation": None}
        if payload is not None:
            payload_check = self.payload_tracker.analyze_payload(payload)

        # Determine if request can proceed
        can_proceed = (
            rate_check["can_proceed"] and payload_check["status"] != "dangerous"
        )

        # Calculate wait time if needed
        wait_time = 0
        if not can_proceed:
            wait_time = max(
                rate_check.get("wait_time", 0),
                30 if payload_check["status"] == "dangerous" else 0,
            )

        result = {
            "can_proceed": can_proceed,
            "wait_time": wait_time,
            "rate_status": rate_check,
            "payload_status": payload_check,
            "recommendation": self._get_recommendation(rate_check, payload_check),
            "statistics": self.get_usage_statistics(),
        }

        # Send warning if approaching limits
        self._check_and_send_warnings(result, current_time)

        return result

    def record_request(
        self,
        payload_size: int,
        response_time: float = None,
        success: bool = True,
        error_type: str = None,
    ):
        """Record a completed request for rate limiting calculations (thread-safe)"""
        current_time = time.time()

        request_info = RequestInfo(
            timestamp=current_time,
            payload_size=payload_size,
            response_time=response_time,
            success=success,
            error_type=error_type,
        )

        self.request_history.append(request_info)

        # Update stats with lock protection
        with self._stats_lock:
            self.total_requests += 1

            if payload_size > self.payload_tracker.warning_size:
                self.large_payload_count += 1

            # Update average response time
            if response_time and success:
                self.average_response_time = (
                    self.average_response_time * (self.total_requests - 1)
                    + response_time
                ) / self.total_requests

        # Log rate limit violations
        if error_type == "rate_limit":
            logger.warning("Rate limit hit! Adjusting strategy.")
            self._handle_rate_limit_hit()

    def get_usage_statistics(self) -> Dict[str, Any]:
        """Get comprehensive usage statistics (thread-safe)"""
        current_time = time.time()
        self._cleanup_old_requests(current_time)

        minute_requests = len(
            [r for r in self.request_history if current_time - r.timestamp <= 60]
        )
        hour_requests = len(
            [r for r in self.request_history if current_time - r.timestamp <= 3600]
        )

        successful_requests = len([r for r in self.request_history if r.success])

        # Copy stats under lock
        with self._stats_lock:
            total_requests = self.total_requests
            blocked_requests = self.blocked_requests
            large_payload_count = self.large_payload_count
            average_response_time = self.average_response_time

        return {
            "requests_last_minute": minute_requests,
            "requests_last_hour": hour_requests,
            "total_requests": total_requests,
            "blocked_requests": blocked_requests,
            "success_rate": (successful_requests / max(total_requests, 1)) * 100,
            "large_payload_count": large_payload_count,
            "average_response_time": average_response_time,
            "rate_limit_utilization": {
                "minute": (minute_requests / self.requests_per_minute) * 100,
                "hour": (hour_requests / self.requests_per_hour) * 100,
            },
        }

    def _cleanup_old_requests(self, current_time: float):
        """Remove requests older than 1 hour"""
        cutoff_time = current_time - 3600  # 1 hour
        while self.request_history and self.request_history[0].timestamp < cutoff_time:
            self.request_history.popleft()

    def _check_rate_limits(self, current_time: float) -> Dict[str, Any]:
        """Check current rate limit status"""
        minute_window = current_time - 60
        hour_window = current_time - 3600

        minute_requests = len(
            [r for r in self.request_history if r.timestamp > minute_window]
        )
        hour_requests = len(
            [r for r in self.request_history if r.timestamp > hour_window]
        )

        # Check limits
        minute_exceeded = minute_requests >= self.requests_per_minute
        hour_exceeded = hour_requests >= self.requests_per_hour

        # Calculate wait times
        wait_time = 0
        if minute_exceeded:
            oldest_in_minute = min(
                [
                    r.timestamp
                    for r in self.request_history
                    if r.timestamp > minute_window
                ]
            )
            wait_time = max(wait_time, 60 - (current_time - oldest_in_minute))

        if hour_exceeded:
            oldest_in_hour = min(
                [r.timestamp for r in self.request_history if r.timestamp > hour_window]
            )
            wait_time = max(wait_time, 3600 - (current_time - oldest_in_hour))

        return {
            "can_proceed": not (minute_exceeded or hour_exceeded),
            "minute_exceeded": minute_exceeded,
            "hour_exceeded": hour_exceeded,
            "minute_requests": minute_requests,
            "hour_requests": hour_requests,
            "wait_time": wait_time,
        }

    def _get_recommendation(self, rate_check: Dict, payload_check: Dict) -> str:
        """Get recommendation based on current status"""
        if payload_check["status"] == "dangerous":
            return "Split request into smaller parts to avoid 413 errors"
        elif payload_check["status"] == "warning":
            return "Consider optimizing payload size to improve performance"
        elif rate_check["minute_exceeded"]:
            return "Rate limit exceeded - wait before making more requests"
        elif rate_check["minute_requests"] > self.requests_per_minute * 0.8:
            return "Approaching rate limits - consider batching requests"
        else:
            return "Request looks good to proceed"

    def _check_and_send_warnings(self, result: Dict, current_time: float):
        """Send warnings if approaching limits"""
        if current_time - self.last_warning_time < self.warning_cooldown:
            return

        rate_status = result["rate_status"]
        payload_status = result["payload_status"]

        warning_conditions = [
            rate_status["minute_requests"] > self.requests_per_minute * 0.9,
            rate_status["hour_requests"] > self.requests_per_hour * 0.9,
            payload_status["status"] == "warning",
        ]

        if any(warning_conditions):
            logger.warning("API Usage Warning: %s", result["recommendation"])
            self.last_warning_time = current_time

    def _handle_rate_limit_hit(self):
        """Handle when a rate limit is actually hit (thread-safe)"""
        # Temporarily reduce limits to be more conservative
        with self._stats_lock:
            self.requests_per_minute = max(10, int(self.requests_per_minute * 0.8))
            new_limit = self.requests_per_minute
        logger.warning("Rate limits adjusted to %s/min after limit hit", new_limit)


# Global instance for easy access (thread-safe)
import threading

_global_rate_limiter: Optional[ConversationRateLimiter] = None
_global_rate_limiter_lock = threading.Lock()


def get_rate_limiter() -> ConversationRateLimiter:
    """Get the global rate limiter instance (thread-safe)"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        with _global_rate_limiter_lock:
            # Double-check after acquiring lock
            if _global_rate_limiter is None:
                _global_rate_limiter = ConversationRateLimiter()
    return _global_rate_limiter


def check_request_allowed(payload: Any = None) -> bool:
    """Quick check if a request is allowed"""
    limiter = get_rate_limiter()
    result = limiter.can_make_request(payload)
    return result["can_proceed"]


def record_request_completion(
    payload_size: int,
    response_time: float = None,
    success: bool = True,
    error_type: str = None,
):
    """Record a completed request"""
    limiter = get_rate_limiter()
    limiter.record_request(payload_size, response_time, success, error_type)
