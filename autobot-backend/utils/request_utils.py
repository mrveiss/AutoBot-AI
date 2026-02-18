#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Request Utilities for AutoBot
=============================

Shared utilities for request handling, ID generation, and tracking.
Eliminates duplication of request-related functions across the codebase.
"""

import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


def generate_request_id() -> str:
    """
    Generate a unique request ID for tracking.

    Returns:
        Unique UUID string for request identification
    """
    return str(uuid.uuid4())


def generate_session_id() -> str:
    """
    Generate a unique session ID.

    Returns:
        Unique session identifier
    """
    timestamp = int(time.time())
    return f"session_{timestamp}_{uuid.uuid4().hex[:8]}"


def generate_chat_id() -> str:
    """
    Generate a unique chat ID.

    Returns:
        Unique chat identifier with timestamp
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"chat_{timestamp}_{uuid.uuid4().hex[:8]}"


def create_request_metadata(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create standardized request metadata.

    Args:
        request_id: Request ID (generated if not provided)
        user_id: User identifier
        session_id: Session identifier
        additional_data: Additional metadata to include

    Returns:
        Dictionary with standardized request metadata
    """
    metadata = {
        "request_id": request_id or generate_request_id(),
        "timestamp": time.time(),
        "iso_timestamp": datetime.now().isoformat(),
    }

    if user_id:
        metadata["user_id"] = user_id

    if session_id:
        metadata["session_id"] = session_id

    if additional_data:
        metadata.update(additional_data)

    return metadata


def extract_request_info(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract standardized information from request data.

    Args:
        request_data: Raw request data

    Returns:
        Extracted and normalized request information
    """
    return {
        "request_id": request_data.get("request_id", generate_request_id()),
        "timestamp": request_data.get("timestamp", time.time()),
        "user_agent": request_data.get("user_agent"),
        "ip_address": request_data.get("ip_address"),
        "method": request_data.get("method"),
        "path": request_data.get("path"),
        "query_params": request_data.get("query_params", {}),
        "headers": request_data.get("headers", {}),
    }


class RequestTracker:
    """
    Simple request tracking utility for performance monitoring.
    """

    def __init__(self):
        """Initialize request tracker with empty active requests dict."""
        self._active_requests: Dict[str, Dict[str, Any]] = {}

    def start_request(self, request_id: str, operation: str, **metadata) -> None:
        """
        Start tracking a request.

        Args:
            request_id: Unique request identifier
            operation: Operation being performed
            **metadata: Additional metadata to track
        """
        self._active_requests[request_id] = {
            "operation": operation,
            "start_time": time.time(),
            "metadata": metadata,
        }

    def end_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        End tracking a request and return performance data.

        Args:
            request_id: Request identifier

        Returns:
            Request performance data or None if not found
        """
        if request_id not in self._active_requests:
            return None

        request_data = self._active_requests.pop(request_id)
        end_time = time.time()
        duration = end_time - request_data["start_time"]

        return {
            "request_id": request_id,
            "operation": request_data["operation"],
            "duration": duration,
            "start_time": request_data["start_time"],
            "end_time": end_time,
            "metadata": request_data["metadata"],
        }

    def get_active_requests(self) -> Dict[str, Dict[str, Any]]:
        """Get currently active requests"""
        current_time = time.time()
        return {
            req_id: {**data, "current_duration": current_time - data["start_time"]}
            for req_id, data in self._active_requests.items()
        }

    def cleanup_stale_requests(self, max_age_seconds: int = 300) -> int:
        """
        Clean up requests that have been active too long.

        Args:
            max_age_seconds: Maximum age for active requests

        Returns:
            Number of requests cleaned up
        """
        current_time = time.time()
        stale_requests = [
            req_id
            for req_id, data in self._active_requests.items()
            if current_time - data["start_time"] > max_age_seconds
        ]

        for req_id in stale_requests:
            del self._active_requests[req_id]

        return len(stale_requests)


# Global request tracker instance
_request_tracker = RequestTracker()


def get_request_tracker() -> RequestTracker:
    """Get the global request tracker instance"""
    return _request_tracker


def validate_request_id(request_id: str) -> bool:
    """
    Validate that a request ID has the correct format.

    Args:
        request_id: Request ID to validate

    Returns:
        True if valid UUID format
    """
    try:
        uuid.UUID(request_id)
        return True
    except ValueError:
        return False


def is_chat_request_id(request_id: str) -> bool:
    """
    Check if request ID is in chat format.

    Args:
        request_id: Request ID to check

    Returns:
        True if it's a chat request ID format
    """
    return request_id.startswith("chat_") and len(request_id.split("_")) >= 3
