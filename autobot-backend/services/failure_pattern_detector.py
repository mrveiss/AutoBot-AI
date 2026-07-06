# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Failure Pattern Detector

Learns failure patterns over time by analyzing causal chains.
Stores patterns in Redis and detects when new errors match known patterns,
improving recovery recommendations through feedback loops.

Issue #2154: Pattern-based error recovery optimization.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.time_utils import now_utc
from constants.ttl_constants import TTL_30_DAYS

logger = get_logger(__name__)

# Redis key patterns
PATTERN_KEY_PREFIX = "failure:pattern:"
PATTERN_STATS_SUFFIX = ":stats"
PATTERN_HISTORY_SUFFIX = ":history"
KNOWN_PATTERNS_KEY = "failure:patterns:known"

# Maximum seconds to wait for any single Redis operation on the failure path.
# Keeps a slow/hung Redis from stalling workflow error handling.
_REDIS_OP_TIMEOUT: float = 2.0


@dataclass
class FailurePattern:
    """A learned failure pattern."""

    pattern_id: str
    causal_chain: str
    error_types: List[str] = field(default_factory=list)
    occurrence_count: int = 0
    successful_resolutions: List[str] = field(default_factory=list)  # Action names
    resolution_success_rate: float = 0.0  # 0.0-1.0
    confidence: float = 0.8  # How confident in this pattern's recovery strategy
    first_seen: str = field(default_factory=lambda: now_utc().isoformat())
    last_seen: str = field(default_factory=lambda: now_utc().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "pattern_id": self.pattern_id,
            "causal_chain": self.causal_chain,
            "error_types": self.error_types,
            "occurrence_count": self.occurrence_count,
            "successful_resolutions": self.successful_resolutions,
            "resolution_success_rate": self.resolution_success_rate,
            "confidence": self.confidence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FailurePattern":
        """Deserialize from dict."""
        return cls(
            pattern_id=data["pattern_id"],
            causal_chain=data["causal_chain"],
            error_types=data.get("error_types", []),
            occurrence_count=data.get("occurrence_count", 0),
            successful_resolutions=data.get("successful_resolutions", []),
            resolution_success_rate=data.get("resolution_success_rate", 0.0),
            confidence=data.get("confidence", 0.8),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
        )


class FailurePatternDetector(AsyncRedisClientMixin):
    """
    Detects and learns failure patterns from error causal chains.

    Maintains a registry of known patterns in Redis and provides:
    - Pattern matching for new errors
    - Confidence scoring based on historical resolution data
    - Feedback loop for improving recommendations over time

    All Redis I/O is async-native (``await redis.<op>``) via
    ``AsyncRedisClientMixin``.  Each operation is bounded by
    ``_REDIS_OP_TIMEOUT`` seconds so a slow Redis cannot stall the
    workflow failure path.
    """

    _redis_database = "main"

    def hash_causal_chain(self, causal_chain: str) -> str:
        """Hash a causal chain for pattern matching."""
        return hashlib.md5(causal_chain.encode(), usedforsecurity=False).hexdigest()[:16]

    async def detect_pattern(self, causal_chain: str, error_type: str) -> FailurePattern | None:
        """
        Check if a causal chain matches a known failure pattern.

        Args:
            causal_chain: The causal chain from error analysis
            error_type: The error exception type name

        Returns:
            Matching FailurePattern if found, None otherwise
        """
        pattern_hash = self.hash_causal_chain(causal_chain)

        try:
            redis = await self._get_redis()
            pattern_key = f"{PATTERN_KEY_PREFIX}{pattern_hash}"

            pattern_data = await asyncio.wait_for(redis.get(pattern_key), timeout=_REDIS_OP_TIMEOUT)
            if not pattern_data:
                return None

            try:
                pattern = FailurePattern.from_dict(json.loads(pattern_data))
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Corrupt pattern data for hash=%s: %s", pattern_hash, exc)
                return None

            pattern.last_seen = now_utc().isoformat()
            await self._store_pattern(pattern_hash, pattern)

            logger.debug(
                "Found known pattern: hash=%s, count=%d, success_rate=%.2f",
                pattern_hash,
                pattern.occurrence_count,
                pattern.resolution_success_rate,
            )
            return pattern

        except Exception as exc:
            logger.warning("Failed to detect pattern: %s", exc)
            return None

    async def learn_pattern(
        self,
        causal_chain: str,
        error_type: str,
        successful_action: str | None = None,
    ) -> FailurePattern:
        """
        Learn/update a pattern from error experience.

        Args:
            causal_chain: The causal chain
            error_type: The error type
            successful_action: If provided, update resolution stats

        Returns:
            Updated FailurePattern
        """
        pattern_hash = self.hash_causal_chain(causal_chain)

        try:
            redis = await self._get_redis()
            pattern_key = f"{PATTERN_KEY_PREFIX}{pattern_hash}"

            pattern_data = await asyncio.wait_for(redis.get(pattern_key), timeout=_REDIS_OP_TIMEOUT)
            if pattern_data:
                try:
                    pattern = FailurePattern.from_dict(json.loads(pattern_data))
                except (json.JSONDecodeError, KeyError):
                    pattern = self._create_new_pattern(pattern_hash, causal_chain)
            else:
                pattern = self._create_new_pattern(pattern_hash, causal_chain)

            if error_type not in pattern.error_types:
                pattern.error_types.append(error_type)

            pattern.occurrence_count += 1
            pattern.last_seen = now_utc().isoformat()

            if successful_action:
                if successful_action not in pattern.successful_resolutions:
                    pattern.successful_resolutions.append(successful_action)
                if pattern.occurrence_count > 0:
                    success_count = len(pattern.successful_resolutions)
                    pattern.resolution_success_rate = success_count / pattern.occurrence_count
                    pattern.confidence = min(1.0, 0.7 + (pattern.resolution_success_rate * 0.3))

            await self._store_pattern(pattern_hash, pattern)

            logger.info(
                "Updated pattern: hash=%s, count=%d, success_rate=%.2f, confidence=%.2f",
                pattern_hash,
                pattern.occurrence_count,
                pattern.resolution_success_rate,
                pattern.confidence,
            )
            return pattern

        except Exception as exc:
            logger.warning("Failed to learn pattern: %s", exc)
            return FailurePattern(
                pattern_id=pattern_hash,
                causal_chain=causal_chain,
                error_types=[error_type],
                occurrence_count=1,
                confidence=0.5,
            )

    def _create_new_pattern(self, pattern_hash: str, causal_chain: str) -> FailurePattern:
        """Create a new failure pattern."""
        return FailurePattern(
            pattern_id=pattern_hash,
            causal_chain=causal_chain,
            error_types=[],
            occurrence_count=0,
            confidence=0.7,
            first_seen=now_utc().isoformat(),
            last_seen=now_utc().isoformat(),
        )

    async def _store_pattern(self, pattern_hash: str, pattern: FailurePattern) -> None:
        """Store a pattern to Redis (async-native, bounded by _REDIS_OP_TIMEOUT)."""
        try:
            redis = await self._get_redis()
            pattern_key = f"{PATTERN_KEY_PREFIX}{pattern_hash}"

            await asyncio.wait_for(
                redis.set(pattern_key, json.dumps(pattern.to_dict()), ex=TTL_30_DAYS),
                timeout=_REDIS_OP_TIMEOUT,
            )
            await asyncio.wait_for(redis.sadd(KNOWN_PATTERNS_KEY, pattern_hash), timeout=_REDIS_OP_TIMEOUT)
            await asyncio.wait_for(redis.expire(KNOWN_PATTERNS_KEY, TTL_30_DAYS), timeout=_REDIS_OP_TIMEOUT)

        except Exception as exc:
            logger.warning("Failed to store pattern: %s", exc)

    @staticmethod
    def _decode_members(raw: set) -> set:
        """Normalise smembers() output to a set of str.

        Redis-py returns ``set[bytes]`` when *decode_responses* is False/unset
        and ``set[str]`` when it is True.  Normalising at the consumption
        point makes every caller correct regardless of client configuration.
        """
        return {m.decode() if isinstance(m, bytes) else m for m in raw}

    async def get_pattern_statistics(self) -> Dict[str, Any]:
        """Get overall statistics about learned patterns."""
        try:
            redis = await self._get_redis()

            raw = await asyncio.wait_for(redis.smembers(KNOWN_PATTERNS_KEY), timeout=_REDIS_OP_TIMEOUT)
            pattern_hashes = self._decode_members(raw or set())

            if not pattern_hashes:
                return {
                    "total_patterns": 0,
                    "total_occurrences": 0,
                    "average_success_rate": 0.0,
                    "high_confidence_patterns": 0,
                }

            total_occurrences = 0
            total_success_rate = 0.0
            high_confidence_count = 0

            for pattern_hash in pattern_hashes:
                pattern_key = f"{PATTERN_KEY_PREFIX}{pattern_hash}"
                pattern_data = await asyncio.wait_for(redis.get(pattern_key), timeout=_REDIS_OP_TIMEOUT)
                if pattern_data:
                    try:
                        pattern = FailurePattern.from_dict(json.loads(pattern_data))
                        total_occurrences += pattern.occurrence_count
                        total_success_rate += pattern.resolution_success_rate
                        if pattern.confidence > 0.8:
                            high_confidence_count += 1
                    except (json.JSONDecodeError, KeyError):
                        continue

            pattern_count = len(pattern_hashes)
            avg_success_rate = total_success_rate / pattern_count if pattern_count > 0 else 0.0

            return {
                "total_patterns": pattern_count,
                "total_occurrences": total_occurrences,
                "average_success_rate": avg_success_rate,
                "high_confidence_patterns": high_confidence_count,
            }

        except Exception as exc:
            logger.warning("Failed to get pattern statistics: %s", exc)
            return {
                "total_patterns": 0,
                "total_occurrences": 0,
                "average_success_rate": 0.0,
                "high_confidence_patterns": 0,
                "error": str(exc),
            }

    async def list_known_patterns(self, limit: int = 50) -> List[FailurePattern]:
        """
        List known patterns sorted by occurrence count.

        Args:
            limit: Maximum number of patterns to return

        Returns:
            List of FailurePattern ordered by frequency
        """
        try:
            redis = await self._get_redis()
            raw = await asyncio.wait_for(redis.smembers(KNOWN_PATTERNS_KEY), timeout=_REDIS_OP_TIMEOUT)
            pattern_hashes = self._decode_members(raw or set())

            patterns: List[FailurePattern] = []

            for pattern_hash in pattern_hashes:
                pattern_key = f"{PATTERN_KEY_PREFIX}{pattern_hash}"
                pattern_data = await asyncio.wait_for(redis.get(pattern_key), timeout=_REDIS_OP_TIMEOUT)
                if pattern_data:
                    try:
                        pattern = FailurePattern.from_dict(json.loads(pattern_data))
                        patterns.append(pattern)
                    except (json.JSONDecodeError, KeyError):
                        continue

            patterns.sort(key=lambda p: p.occurrence_count, reverse=True)
            return patterns[:limit]

        except Exception as exc:
            logger.warning("Failed to list patterns: %s", exc)
            return []

    async def clear_patterns(self) -> None:
        """Clear all learned patterns (for testing or reset)."""
        try:
            redis = await self._get_redis()
            raw = await asyncio.wait_for(redis.smembers(KNOWN_PATTERNS_KEY), timeout=_REDIS_OP_TIMEOUT)
            pattern_hashes = self._decode_members(raw or set())

            for pattern_hash in pattern_hashes:
                pattern_key = f"{PATTERN_KEY_PREFIX}{pattern_hash}"
                await asyncio.wait_for(redis.delete(pattern_key), timeout=_REDIS_OP_TIMEOUT)

            await asyncio.wait_for(redis.delete(KNOWN_PATTERNS_KEY), timeout=_REDIS_OP_TIMEOUT)
            logger.info("Cleared %d failure patterns", len(pattern_hashes))

        except Exception as exc:
            logger.warning("Failed to clear patterns: %s", exc)


# Module-level singleton
_pattern_detector = FailurePatternDetector()


def get_pattern_detector() -> FailurePatternDetector:
    """Get the shared pattern detector singleton."""
    return _pattern_detector
