# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fallback types and the cached-response strategy, split out of ``graceful_degradation`` (#19553).

``GracefulDegradationManager`` (``utils/graceful_degradation.py``) composes these; the cache
they read and write lives under :func:`autobot_shared.paths.shared_cache_path`, never the repo.
"""

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict

import aiofiles

from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import shared_cache_path

logger = get_logger(__name__)


def response_cache_dir() -> Path:
    """Cached fallback responses: regenerable, so in the user cache, never the repo (#19553).

    Resolved on use, never at import: resolving keys the cache by checkout with a git call.
    """
    return shared_cache_path("claude_responses")


class DegradationLevel(Enum):
    """Levels of service degradation"""

    NORMAL = 0  # Full functionality
    REDUCED = 1  # Limited features, cached responses
    MINIMAL = 2  # Basic cached responses only
    EMERGENCY = 3  # Static fallbacks and error messages
    OFFLINE = 4  # Complete service unavailable


class ServiceHealthLevel(Enum):
    """Service health status indicators"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNSTABLE = "unstable"
    FAILING = "failing"
    DOWN = "down"


@dataclass
class FallbackResponse:
    """Represents a fallback response with metadata"""

    content: str
    source: str = "fallback"
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)
    cached: bool = False
    degradation_level: DegradationLevel = DegradationLevel.REDUCED
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DegradedState:
    """Current service status and health metrics"""

    health: ServiceHealthLevel
    degradation_level: DegradationLevel
    last_success: float | None = None
    last_failure: float | None = None
    consecutive_failures: int = 0
    error_rate: float = 0.0
    response_time: float = 0.0
    uptime_percentage: float = 100.0


class FallbackStrategy(ABC):
    """Abstract base class for fallback strategies"""

    @abstractmethod
    async def can_handle(self, request: str, context: Dict[str, Any]) -> bool:
        """Check if this strategy can handle the request"""

    @abstractmethod
    async def generate_response(self, request: str, context: Dict[str, Any]) -> FallbackResponse:
        """Generate a fallback response"""

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the identifier this strategy is registered and reported under."""


class CachedResponseStrategy(FallbackStrategy):
    """Strategy that uses cached responses from previous successful calls"""

    def __init__(self, cache_dir: str | Path | None = None):
        """Initialize cached response strategy with cache directory and settings."""
        self.cache_dir = Path(cache_dir) if cache_dir else response_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_cache_age = 24 * 60 * 60  # 24 hours
        self.similarity_threshold = 0.7

    async def can_handle(self, request: str, context: Dict[str, Any]) -> bool:
        """Check if we have a cached response for similar request"""
        cached_response = await self._find_cached_response(request)
        return cached_response is not None

    async def generate_response(self, request: str, context: Dict[str, Any]) -> FallbackResponse:
        """Return cached response if available"""
        cached_response = await self._find_cached_response(request)

        if cached_response:
            return FallbackResponse(
                content=cached_response["content"],
                source="cached_response",
                confidence=cached_response.get("confidence", 0.8),
                cached=True,
                degradation_level=DegradationLevel.REDUCED,
                metadata={"original_timestamp": cached_response.get("timestamp")},
            )

        return FallbackResponse(
            content=(
                "I apologize, but I'm currently unable to process your request due to service issues."
                "Please try again later."
            ),
            source="cached_response_fallback",
            confidence=0.1,
            degradation_level=DegradationLevel.MINIMAL,
        )

    def get_strategy_name(self) -> str:
        """Return the strategy identifier name."""
        return "cached_response"

    async def cache_response(self, request: str, response: str, confidence: float = 1.0):
        """Cache a successful response for future fallback use"""
        cache_key = self._generate_cache_key(request)
        cache_file = self.cache_dir / f"{cache_key}.json"

        cache_data = {
            "request": request,
            "content": response,
            "confidence": confidence,
            "timestamp": time.time(),
        }

        try:
            async with aiofiles.open(cache_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(cache_data))
            logger.debug("Cached response for key: %s", cache_key)
        except OSError as e:
            logger.warning("Failed to write cache file %s: %s", cache_file, e)
        except Exception as e:
            logger.warning("Failed to serialize cache response: %s", e)

    async def _find_cached_response(self, request: str) -> Dict[str, Any] | None:
        """Find a cached response for the request"""
        cache_key = self._generate_cache_key(request)
        cache_file = self.cache_dir / f"{cache_key}.json"

        # Try exact match first
        # Issue #358 - avoid blocking
        if await asyncio.to_thread(cache_file.exists):
            try:
                async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    cached_data = json.loads(content)

                # Check if cache is still valid
                age = time.time() - cached_data.get("timestamp", 0)
                if age <= self.max_cache_age:
                    return cached_data
            except OSError as e:
                logger.warning("Failed to read cache file %s: %s", cache_file, e)
            except Exception as e:
                logger.warning("Error parsing cache file %s: %s", cache_file, e)

        # Try similarity-based matching
        return await self._find_similar_cached_response(request)

    async def _find_similar_cached_response(self, request: str) -> Dict[str, Any] | None:
        """Find a cached response for similar request"""
        request_words = set(request.lower().split())
        best_match = None
        best_similarity = 0

        try:
            # Issue #358 - use lambda for proper glob() execution in thread
            cache_files = await asyncio.to_thread(lambda: list(self.cache_dir.glob("*.json")))
            for cache_file in cache_files:
                try:
                    async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        cached_data = json.loads(content)

                    # Check cache age
                    age = time.time() - cached_data.get("timestamp", 0)
                    if age > self.max_cache_age:
                        continue

                    # Calculate similarity
                    cached_words = set(cached_data["request"].lower().split())
                    if not request_words or not cached_words:
                        continue

                    intersection = request_words.intersection(cached_words)
                    union = request_words.union(cached_words)
                    similarity = len(intersection) / len(union)

                    if similarity > best_similarity and similarity >= self.similarity_threshold:
                        best_similarity = similarity
                        best_match = cached_data
                        best_match["confidence"] = similarity

                except OSError as e:
                    logger.warning("Failed to read cache file %s: %s", cache_file, e)
                except Exception as e:
                    logger.warning("Error parsing cache file %s: %s", cache_file, e)

        except Exception as e:
            logger.warning("Error scanning cache directory: %s", e)

        return best_match

    def _generate_cache_key(self, request: str) -> str:
        """Generate a cache key for the request"""
        return hashlib.md5(request.encode(), usedforsecurity=False).hexdigest()
