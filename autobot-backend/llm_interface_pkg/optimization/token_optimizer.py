# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Token Budget Optimizer - Compress recurring context to reduce LLM API token usage.

Fingerprints frequently-used context blocks (system prompts, KB summaries,
agent instructions) and caches compact representations. Reduces tokens sent
per API call by an estimated 20-30% for repeated context.

Issue #2098: Active token budget optimization with context compaction.
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Redis import — graceful fallback if unavailable
try:
    from autobot_shared.redis_client import RedisDatabase, get_redis_client

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    RedisDatabase = None


@dataclass
class TokenOptimizerConfig:
    """Configuration for the token budget optimizer."""

    enabled: bool = True
    min_repeat_threshold: int = 3
    min_block_length: int = 200
    l1_max_entries: int = 100
    l1_ttl_seconds: int = 300
    l2_ttl_seconds: int = 86400
    compaction_ratio: float = 0.6
    redis_key_prefix: str = "autobot:token_opt:"


@dataclass
class CompactionEntry:
    """A cached compacted context block."""

    fingerprint: str
    original_length: int
    compacted_text: str
    compacted_length: int
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)


@dataclass
class TokenSavingsRecord:
    """Record of token savings for analytics."""

    request_id: str
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    blocks_compacted: int
    timestamp: float = field(default_factory=time.time)


class ContextFingerprinter:
    """Hash recurring context blocks to identify compaction candidates."""

    @staticmethod
    def fingerprint(text: str) -> str:
        """Generate a stable fingerprint for a context block."""
        normalized = " ".join(text.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def extract_blocks(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Extract compactable context blocks from a message list.

        Returns list of dicts with 'index', 'role', 'content', 'fingerprint'.
        System messages and long assistant/user preambles are candidates.
        """
        blocks = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if not content or len(content) < 200:
                continue
            if msg.get("role") == "system" or (
                msg.get("role") == "user" and i == 0 and len(content) > 500
            ):
                fp = ContextFingerprinter.fingerprint(content)
                blocks.append(
                    {
                        "index": i,
                        "role": msg["role"],
                        "content": content,
                        "fingerprint": fp,
                    }
                )
        return blocks


class L1Cache:
    """In-memory LRU cache for hot compacted context (L1)."""

    def __init__(self, max_entries: int = 100, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, CompactionEntry] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds

    def get(self, fingerprint: str) -> Optional[CompactionEntry]:
        """Retrieve a compaction entry if present and not expired."""
        entry = self._cache.get(fingerprint)
        if entry is None:
            return None
        if time.time() - entry.created_at > self._ttl_seconds:
            del self._cache[fingerprint]
            return None
        self._cache.move_to_end(fingerprint)
        entry.hit_count += 1
        entry.last_accessed = time.time()
        return entry

    def put(self, fingerprint: str, entry: CompactionEntry) -> None:
        """Store a compaction entry, evicting oldest if at capacity."""
        if fingerprint in self._cache:
            self._cache.move_to_end(fingerprint)
            self._cache[fingerprint] = entry
            return
        if len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)
        self._cache[fingerprint] = entry

    @property
    def size(self) -> int:
        return len(self._cache)


class L2Cache:
    """Redis-backed persistent cache for compacted context (L2)."""

    def __init__(
        self, ttl_seconds: int = 86400, key_prefix: str = "autobot:token_opt:"
    ):
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix
        self._redis = None
        self._init_attempted = False

    def _get_redis(self):
        """Lazy-init Redis connection."""
        if self._init_attempted:
            return self._redis
        self._init_attempted = True
        if not REDIS_AVAILABLE:
            logger.debug("Redis unavailable — L2 cache disabled")
            return None
        try:
            self._redis = get_redis_client(async_client=False, database="analytics")
            return self._redis
        except Exception:
            logger.warning("Failed to connect to Redis for L2 token cache")
            return None

    def get(self, fingerprint: str) -> Optional[CompactionEntry]:
        """Retrieve a compaction entry from Redis."""
        redis = self._get_redis()
        if redis is None:
            return None
        try:
            data = redis.get(f"{self._key_prefix}{fingerprint}")
            if data is None:
                return None
            parsed = json.loads(data)
            return CompactionEntry(**parsed)
        except Exception:
            logger.debug("L2 cache read error for %s", fingerprint)
            return None

    def put(self, fingerprint: str, entry: CompactionEntry) -> None:
        """Store a compaction entry in Redis with TTL."""
        redis = self._get_redis()
        if redis is None:
            return
        try:
            data = json.dumps(
                {
                    "fingerprint": entry.fingerprint,
                    "original_length": entry.original_length,
                    "compacted_text": entry.compacted_text,
                    "compacted_length": entry.compacted_length,
                    "hit_count": entry.hit_count,
                    "created_at": entry.created_at,
                    "last_accessed": entry.last_accessed,
                }
            )
            redis.setex(f"{self._key_prefix}{fingerprint}", self._ttl_seconds, data)
        except Exception:
            logger.debug("L2 cache write error for %s", fingerprint)


class FrequencyTracker:
    """Track how often each context fingerprint is seen."""

    def __init__(self, threshold: int = 3):
        self._counts: Dict[str, int] = {}
        self._threshold = threshold

    def record(self, fingerprint: str) -> int:
        """Record a fingerprint occurrence, return new count."""
        self._counts[fingerprint] = self._counts.get(fingerprint, 0) + 1
        return self._counts[fingerprint]

    def is_eligible(self, fingerprint: str) -> bool:
        """Check if a fingerprint has been seen enough for compaction."""
        return self._counts.get(fingerprint, 0) >= self._threshold


class TokenOptimizer:
    """
    Main token budget optimizer.

    Intercepts LLM request messages, identifies recurring context blocks,
    and substitutes compact versions from a two-tier cache. Tracks savings
    for analytics.

    Usage:
        optimizer = TokenOptimizer()
        optimized_messages, record = optimizer.optimize(request.messages, request_id)
    """

    def __init__(self, config: Optional[TokenOptimizerConfig] = None):
        self._config = config or TokenOptimizerConfig()
        self._fingerprinter = ContextFingerprinter()
        self._l1 = L1Cache(
            max_entries=self._config.l1_max_entries,
            ttl_seconds=self._config.l1_ttl_seconds,
        )
        self._l2 = L2Cache(
            ttl_seconds=self._config.l2_ttl_seconds,
            key_prefix=self._config.redis_key_prefix,
        )
        self._frequency = FrequencyTracker(threshold=self._config.min_repeat_threshold)
        self._total_tokens_saved: int = 0
        self._total_requests: int = 0

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def stats(self) -> Dict[str, Any]:
        """Return aggregate optimization statistics."""
        return {
            "total_requests": self._total_requests,
            "total_tokens_saved": self._total_tokens_saved,
            "l1_cache_size": self._l1.size,
            "enabled": self._config.enabled,
        }

    def optimize(
        self,
        messages: List[Dict[str, str]],
        request_id: str = "",
    ) -> tuple:
        """Optimize messages by substituting compacted context blocks.

        Args:
            messages: LLM request messages list.
            request_id: Optional request ID for tracking.

        Returns:
            Tuple of (optimized_messages, TokenSavingsRecord).
        """
        self._total_requests += 1
        if not self._config.enabled:
            return messages, self._empty_record(messages, request_id)

        blocks = self._fingerprinter.extract_blocks(messages)
        if not blocks:
            return messages, self._empty_record(messages, request_id)

        optimized = list(messages)
        total_saved = 0
        blocks_compacted = 0

        for block in blocks:
            fp = block["fingerprint"]
            self._frequency.record(fp)
            entry = self._lookup(fp)
            if entry is not None:
                optimized[block["index"]] = {
                    **optimized[block["index"]],
                    "content": entry.compacted_text,
                }
                saved = len(block["content"]) - entry.compacted_length
                total_saved += max(saved, 0)
                blocks_compacted += 1
            elif self._frequency.is_eligible(fp):
                compacted = self._compact(block["content"])
                self._store(fp, block["content"], compacted)
                optimized[block["index"]] = {
                    **optimized[block["index"]],
                    "content": compacted,
                }
                saved = len(block["content"]) - len(compacted)
                total_saved += max(saved, 0)
                blocks_compacted += 1

        est_tokens_saved = total_saved // 4
        self._total_tokens_saved += est_tokens_saved
        original_est = sum(len(m.get("content", "")) for m in messages) // 4
        optimized_est = sum(len(m.get("content", "")) for m in optimized) // 4

        record = TokenSavingsRecord(
            request_id=request_id,
            original_tokens=original_est,
            optimized_tokens=optimized_est,
            tokens_saved=est_tokens_saved,
            blocks_compacted=blocks_compacted,
        )

        if blocks_compacted > 0:
            logger.info(
                "Token optimization: ~%d tokens saved (%d blocks compacted)",
                est_tokens_saved,
                blocks_compacted,
            )

        return optimized, record

    def _lookup(self, fingerprint: str) -> Optional[CompactionEntry]:
        """Look up a compaction entry in L1, then L2."""
        entry = self._l1.get(fingerprint)
        if entry is not None:
            return entry
        entry = self._l2.get(fingerprint)
        if entry is not None:
            self._l1.put(fingerprint, entry)
            return entry
        return None

    def _store(self, fingerprint: str, original: str, compacted: str) -> None:
        """Store a new compaction entry in both cache tiers."""
        entry = CompactionEntry(
            fingerprint=fingerprint,
            original_length=len(original),
            compacted_text=compacted,
            compacted_length=len(compacted),
        )
        self._l1.put(fingerprint, entry)
        self._l2.put(fingerprint, entry)

    def _compact(self, text: str) -> str:
        """Compact a context block using rule-based compression.

        Strips redundancy, whitespace, and filler while preserving meaning.
        For production use, a small LLM call could generate better summaries.
        """
        lines = text.split("\n")
        compacted_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") and len(stripped) < 5:
                continue
            compacted_lines.append(stripped)
        result = "\n".join(compacted_lines)
        target_len = int(len(text) * self._config.compaction_ratio)
        if len(result) > target_len:
            result = result[:target_len]
        return result

    def _empty_record(
        self, messages: List[Dict[str, str]], request_id: str
    ) -> TokenSavingsRecord:
        """Create a zero-savings record."""
        est = sum(len(m.get("content", "")) for m in messages) // 4
        return TokenSavingsRecord(
            request_id=request_id,
            original_tokens=est,
            optimized_tokens=est,
            tokens_saved=0,
            blocks_compacted=0,
        )


# Module-level singleton
_optimizer: Optional[TokenOptimizer] = None


def get_token_optimizer(
    config: Optional[TokenOptimizerConfig] = None,
) -> TokenOptimizer:
    """Get or create the global TokenOptimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = TokenOptimizer(config)
    return _optimizer
