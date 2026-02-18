# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Streaming Management - Manage LLM streaming state and failures.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)


class StreamingManager:
    """
    Manage streaming state and intelligent fallback for LLM responses.

    Tracks streaming failures per model and provides methods for
    determining whether streaming should be used.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_time: float = 300.0,  # 5 minutes
    ):
        """
        Initialize streaming manager.

        Args:
            failure_threshold: Number of failures before considering fallback
            reset_time: Time in seconds before resetting failure count
        """
        self.streaming_failures: Dict[str, Dict] = {}
        self.failure_threshold = failure_threshold
        self.reset_time = reset_time

    def should_use_streaming(self, model: str) -> bool:
        """
        CRITICAL: LLM MUST BE STREAMED AT ALL TIMES - Always return True.

        This method logs streaming failures for monitoring but never disables
        streaming as it is required for proper LLM operation.

        Args:
            model: Model name to check

        Returns:
            Always True - streaming is mandatory
        """
        if model in self.streaming_failures:
            failure_data = self.streaming_failures[model]
            if time.time() - failure_data.get("last_reset", 0) > self.reset_time:
                # Reset failures after timeout
                self.streaming_failures[model]["count"] = 0
                self.streaming_failures[model]["last_reset"] = time.time()

            if failure_data.get("count", 0) >= self.failure_threshold:
                logger.warning(
                    f"Model {model} has {failure_data.get('count', 0)} streaming "
                    "failures but streaming is REQUIRED"
                )
        return True

    def record_failure(self, model: str):
        """
        Record a streaming failure for a model.

        Args:
            model: Model name that experienced the failure
        """
        if model not in self.streaming_failures:
            self.streaming_failures[model] = {"count": 0, "last_reset": time.time()}
        self.streaming_failures[model]["count"] += 1
        logger.warning(
            f"Streaming failure recorded for {model}: "
            f"{self.streaming_failures[model]['count']} total failures"
        )

    def record_success(self, model: str):
        """
        Record a streaming success to potentially recover from failures.

        Args:
            model: Model name that succeeded
        """
        if model in self.streaming_failures:
            # Reduce failure count on success
            self.streaming_failures[model]["count"] = max(
                0, self.streaming_failures[model]["count"] - 1
            )

    def get_failure_count(self, model: str) -> int:
        """
        Get the current failure count for a model.

        Args:
            model: Model name

        Returns:
            Number of recorded failures
        """
        if model in self.streaming_failures:
            return self.streaming_failures[model].get("count", 0)
        return 0

    def reset_failures(self, model: str):
        """
        Reset failure count for a specific model.

        Args:
            model: Model name to reset
        """
        if model in self.streaming_failures:
            self.streaming_failures[model]["count"] = 0
            self.streaming_failures[model]["last_reset"] = time.time()

    def reset_all_failures(self):
        """Reset all failure counts for all models."""
        self.streaming_failures.clear()


__all__ = [
    "StreamingManager",
]
