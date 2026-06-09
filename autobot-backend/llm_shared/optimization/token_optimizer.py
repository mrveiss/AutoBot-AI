# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Token Budget Optimizer - Compress recurring context to reduce LLM API token usage.

Fingerprints frequently-used context blocks (system prompts, KB summaries,
agent instructions) and caches compact representations. Reduces tokens sent
per API call by an estimated 20-30% for repeated context.

Compaction is delegated to PromptCompressor (from this package) for rule-based
compression. This module adds the caching, fingerprinting, and frequency
tracking layers on top.

Issue #2098: Active token budget optimization with context compaction.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_5_MINUTES

logger = get_logger(__name__)

# Redis import — graceful fallback if unavailable
try:
    from autobot_shared.redis_client import get_redis_client

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Reuse existing PromptCompressor for actual compaction (Rule 2). Issue #2098.
try:
    from .prompt_compressor import CompressionConfig, PromptCompressor

    _COMPRESSOR_AVAILABLE = True
except ImportError:
    _COMPRESSOR_AVAILABLE = False


@dataclass
class TokenOptimizerConfig:
    """Configuration for the token budget optimizer."""

    enabled: bool = True
    min_repeat_threshold: int = 3
    min_block_length: int = 200
    min_preamble_length: int = 500
    l1_max_entries: int = 100
    l1_ttl_seconds: int = TTL_5_MINUTES
    l2_ttl_seconds: int = 86400
    compaction_ratio: float = 0.6
    redis_key_prefix: str = "autobot:token_opt:"
    max_tracked_fingerprints: int = 1000


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
    """Record of estimated token savings for analytics.

    Token counts are character-based estimates (chars // 4), not exact
    tokenizer counts. Suitable for analytics and cost tracking, not billing.
    """

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
    def extract_blocks(
        messages: List[Dict[str, str]],
        min_block_length: int = 200,
        min_preamble_length: int = 500,
    ) -> List[Dict[str, Any]]:
        """Extract compactable context blocks from a message list."""
        blocks = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if not content or len(content) < min_block_length:
                continue
            if msg.get("role") == "system" or (
                msg.get("role") == "user" and i == 0 and len(content) > min_preamble_length
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
    """In-memory LRU cache for hot compacted context (L1).

    All public methods are thread-safe. A single lock guards all mutations
    and reads on the underlying OrderedDict so concurrent FastAPI request
    handlers (including those running in thread-pool executors) cannot
    corrupt the LRU ordering or the entry hit-count fields. Issue #2577.
    """

    def __init__(self, max_entries: int = 100, ttl_seconds: int = TTL_5_MINUTES):
        self._cache: OrderedDict[str, CompactionEntry] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def get(self, fingerprint: str) -> CompactionEntry | None:
        """Retrieve a compaction entry if present and not expired. Thread-safe."""
        with self._lock:
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
        """Store a compaction entry, evicting oldest if at capacity. Thread-safe."""
        with self._lock:
            if fingerprint in self._cache:
                self._cache.move_to_end(fingerprint)
                self._cache[fingerprint] = entry
                return
            if len(self._cache) >= self._max_entries:
                self._cache.popitem(last=False)
            self._cache[fingerprint] = entry

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


class L2Cache:
    """Redis-backed persistent cache for compacted context (L2)."""

    def __init__(self, ttl_seconds: int = 86400, key_prefix: str = "autobot:token_opt:"):
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

    def get(self, fingerprint: str) -> CompactionEntry | None:
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
            data = json.dumps(asdict(entry))
            redis.setex(f"{self._key_prefix}{fingerprint}", self._ttl_seconds, data)
        except Exception:
            logger.debug("L2 cache write error for %s", fingerprint)


class FrequencyTracker:
    """Track how often each context fingerprint is seen.

    Evicts least-seen entries when max_entries is reached to prevent
    unbounded memory growth in long-running processes. Issue #2098.

    All public methods are thread-safe. A single lock guards all reads
    and writes on _counts so concurrent requests cannot corrupt the
    frequency map or trigger a double-eviction. Issue #2577.
    """

    def __init__(self, threshold: int = 3, max_entries: int = 1000):
        self._counts: Dict[str, int] = {}
        self._threshold = threshold
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def record(self, fingerprint: str) -> int:
        """Record a fingerprint occurrence, return new count. Thread-safe."""
        with self._lock:
            self._counts[fingerprint] = self._counts.get(fingerprint, 0) + 1
            if len(self._counts) > self._max_entries:
                self._evict_least_seen()
            return self._counts.get(fingerprint, 0)

    def is_eligible(self, fingerprint: str) -> bool:
        """Check if a fingerprint has been seen enough for compaction. Thread-safe."""
        with self._lock:
            return self._counts.get(fingerprint, 0) >= self._threshold

    def _evict_least_seen(self) -> None:
        """Remove the bottom 10% of entries by count to reclaim space.

        Must be called with self._lock already held. Issue #2577.
        """
        target = int(self._max_entries * 0.9)
        sorted_fps = sorted(self._counts, key=lambda k: self._counts[k])
        for fp in sorted_fps[: len(sorted_fps) - target]:
            del self._counts[fp]


class TokenOptimizer:
    """
    Main token budget optimizer.

    Intercepts LLM request messages, identifies recurring context blocks,
    and substitutes compact versions from a two-tier cache. Tracks savings
    for analytics.

    All public methods are thread-safe. A dedicated lock guards the shared
    aggregate counters (_total_tokens_saved, _total_requests) so concurrent
    FastAPI handlers cannot produce lost updates. L1Cache and FrequencyTracker
    each carry their own locks for their respective state. L2Cache (Redis)
    relies on redis-py's built-in connection-pool thread safety. Issue #2577.

    Usage:
        optimizer = TokenOptimizer()
        optimized_messages, record = optimizer.optimize(request.messages, request_id)
    """

    def __init__(self, config: TokenOptimizerConfig | None = None):
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
        self._frequency = FrequencyTracker(
            threshold=self._config.min_repeat_threshold,
            max_entries=self._config.max_tracked_fingerprints,
        )
        self._compressor = self._init_compressor()
        self._total_tokens_saved: int = 0
        self._total_requests: int = 0
        self._lock = threading.Lock()

    @staticmethod
    def _init_compressor() -> "PromptCompressor" | None:
        """Initialize PromptCompressor if available. Issue #2098."""
        if not _COMPRESSOR_AVAILABLE:
            return None
        return PromptCompressor(CompressionConfig(enabled=True, target_ratio=0.6))

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def stats(self) -> Dict[str, Any]:
        """Return a consistent snapshot of aggregate optimization statistics. Thread-safe."""
        with self._lock:
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
    ) -> Tuple[List[Dict[str, str]], TokenSavingsRecord]:
        """Optimize messages by substituting compacted context blocks. Thread-safe."""
        with self._lock:
            self._total_requests += 1
        if not self._config.enabled:
            return messages, self._empty_record(messages, request_id)

        blocks = self._fingerprinter.extract_blocks(
            messages, self._config.min_block_length, self._config.min_preamble_length
        )
        if not blocks:
            return messages, self._empty_record(messages, request_id)

        optimized, total_saved, blocks_compacted = self._process_blocks(messages, blocks)
        return optimized, self._build_record(messages, optimized, total_saved, blocks_compacted, request_id)

    def _process_blocks(
        self,
        messages: List[Dict[str, str]],
        blocks: List[Dict[str, Any]],
    ) -> Tuple[list, int, int]:
        """Apply compaction to eligible blocks. Issue #2098."""
        optimized = list(messages)
        total_saved = 0
        blocks_compacted = 0

        for block in blocks:
            fp = block["fingerprint"]
            self._frequency.record(fp)
            compacted_text = self._get_or_create_compaction(fp, block["content"])
            if compacted_text is not None:
                optimized[block["index"]] = {
                    **optimized[block["index"]],
                    "content": compacted_text,
                }
                total_saved += max(len(block["content"]) - len(compacted_text), 0)
                blocks_compacted += 1

        return optimized, total_saved, blocks_compacted

    def _get_or_create_compaction(self, fp: str, content: str) -> str | None:
        """Look up cached compaction or create one if eligible."""
        entry = self._lookup(fp)
        if entry is not None:
            return entry.compacted_text
        if self._frequency.is_eligible(fp):
            compacted = self._compact(content)
            self._store(fp, content, compacted)
            return compacted
        return None

    def _build_record(
        self,
        original: List[Dict[str, str]],
        optimized: List[Dict[str, str]],
        total_saved: int,
        blocks_compacted: int,
        request_id: str,
    ) -> TokenSavingsRecord:
        """Build a TokenSavingsRecord from optimization results. Thread-safe."""
        est_tokens_saved = total_saved // 4
        with self._lock:
            self._total_tokens_saved += est_tokens_saved

        if blocks_compacted > 0:
            logger.info(
                "Token optimization: ~%d tokens saved (%d blocks compacted)",
                est_tokens_saved,
                blocks_compacted,
            )

        return TokenSavingsRecord(
            request_id=request_id,
            original_tokens=sum(len(m.get("content", "")) for m in original) // 4,
            optimized_tokens=sum(len(m.get("content", "")) for m in optimized) // 4,
            tokens_saved=est_tokens_saved,
            blocks_compacted=blocks_compacted,
        )

    def _lookup(self, fingerprint: str) -> CompactionEntry | None:
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
        """Compact a context block, delegating to PromptCompressor if available.

        Falls back to simple line-based compression if PromptCompressor
        is not importable. Truncates at line boundaries to avoid mid-sentence cuts.
        """
        if self._compressor is not None:
            result = self._compressor.compress(text)
            return result.compressed_text

        # Fallback: simple line-based compression
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        result = "\n".join(lines)
        target_len = int(len(text) * self._config.compaction_ratio)
        if len(result) > target_len:
            cut = result[:target_len].rfind("\n")
            result = result[: cut if cut > 0 else target_len]
        return result

    def _empty_record(self, messages: List[Dict[str, str]], request_id: str) -> TokenSavingsRecord:
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
_optimizer: TokenOptimizer | None = None


def get_token_optimizer(
    config: TokenOptimizerConfig | None = None,
) -> TokenOptimizer:
    """Get or create the global TokenOptimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = TokenOptimizer(config)
    return _optimizer
