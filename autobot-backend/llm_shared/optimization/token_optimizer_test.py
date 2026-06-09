# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for TokenOptimizer — Issue #2098."""

import json
import time
from unittest.mock import MagicMock, patch

from .token_optimizer import (
    CompactionEntry,
    ContextFingerprinter,
    FrequencyTracker,
    L1Cache,
    L2Cache,
    TokenOptimizer,
    TokenOptimizerConfig,
    get_token_optimizer,
)


class TestContextFingerprinter:
    def test_fingerprint_stable(self):
        fp1 = ContextFingerprinter.fingerprint("Hello world")
        fp2 = ContextFingerprinter.fingerprint("Hello world")
        assert fp1 == fp2

    def test_fingerprint_normalizes_whitespace(self):
        fp1 = ContextFingerprinter.fingerprint("Hello   world")
        fp2 = ContextFingerprinter.fingerprint("Hello world")
        assert fp1 == fp2

    def test_fingerprint_different_for_different_text(self):
        fp1 = ContextFingerprinter.fingerprint("Hello world")
        fp2 = ContextFingerprinter.fingerprint("Goodbye world")
        assert fp1 != fp2

    def test_extract_blocks_skips_short(self):
        messages = [{"role": "system", "content": "short"}]
        blocks = ContextFingerprinter.extract_blocks(messages)
        assert len(blocks) == 0

    def test_extract_blocks_finds_system(self):
        long_content = "x" * 300
        messages = [{"role": "system", "content": long_content}]
        blocks = ContextFingerprinter.extract_blocks(messages)
        assert len(blocks) == 1
        assert blocks[0]["index"] == 0
        assert blocks[0]["role"] == "system"


class TestL1Cache:
    def test_put_and_get(self):
        cache = L1Cache(max_entries=10, ttl_seconds=300)
        entry = CompactionEntry(
            fingerprint="abc",
            original_length=100,
            compacted_text="short",
            compacted_length=5,
        )
        cache.put("abc", entry)
        result = cache.get("abc")
        assert result is not None
        assert result.compacted_text == "short"

    def test_eviction_on_capacity(self):
        cache = L1Cache(max_entries=2, ttl_seconds=300)
        for i in range(3):
            entry = CompactionEntry(
                fingerprint=f"fp{i}",
                original_length=100,
                compacted_text=f"c{i}",
                compacted_length=2,
            )
            cache.put(f"fp{i}", entry)
        assert cache.get("fp0") is None
        assert cache.get("fp1") is not None
        assert cache.get("fp2") is not None

    def test_ttl_expiry(self):
        cache = L1Cache(max_entries=10, ttl_seconds=0)
        entry = CompactionEntry(
            fingerprint="abc",
            original_length=100,
            compacted_text="short",
            compacted_length=5,
            created_at=0,
        )
        cache.put("abc", entry)
        assert cache.get("abc") is None


class TestFrequencyTracker:
    def test_threshold(self):
        tracker = FrequencyTracker(threshold=3)
        tracker.record("fp1")
        assert not tracker.is_eligible("fp1")
        tracker.record("fp1")
        assert not tracker.is_eligible("fp1")
        tracker.record("fp1")
        assert tracker.is_eligible("fp1")


class TestTokenOptimizer:
    def _make_optimizer(self, **kwargs):
        config = TokenOptimizerConfig(enabled=True, min_repeat_threshold=2, min_block_length=200, **kwargs)
        return TokenOptimizer(config)

    def test_disabled_returns_original(self):
        config = TokenOptimizerConfig(enabled=False)
        opt = TokenOptimizer(config)
        msgs = [{"role": "system", "content": "x" * 300}]
        result, record = opt.optimize(msgs, "req1")
        assert result == msgs
        assert record.tokens_saved == 0

    def test_short_messages_no_optimization(self):
        opt = self._make_optimizer()
        msgs = [{"role": "user", "content": "Hello"}]
        result, record = opt.optimize(msgs, "req1")
        assert result == msgs
        assert record.blocks_compacted == 0

    def test_compaction_after_threshold(self):
        opt = self._make_optimizer()
        long_content = "This is a test system prompt.\n" * 30
        msgs = [{"role": "system", "content": long_content}]
        opt.optimize(msgs, "req1")
        opt.optimize(msgs, "req2")
        result, record = opt.optimize(msgs, "req3")
        assert record.blocks_compacted >= 1
        assert len(result[0]["content"]) < len(long_content)

    def test_stats_tracking(self):
        opt = self._make_optimizer()
        msgs = [{"role": "user", "content": "Hello"}]
        opt.optimize(msgs, "req1")
        assert opt.stats["total_requests"] == 1

    def test_cache_hit_on_subsequent_calls(self):
        opt = self._make_optimizer()
        long_content = "System instructions repeated.\n" * 30
        msgs = [{"role": "system", "content": long_content}]
        for i in range(5):
            opt.optimize(msgs, f"req{i}")
        _, record = opt.optimize(msgs, "final")
        assert record.blocks_compacted >= 1


class TestL2CacheWithMockedRedis:
    """Tests for L2Cache with mocked Redis client."""

    def _make_entry(self, fingerprint: str = "abc123") -> CompactionEntry:
        """Create a test CompactionEntry."""
        return CompactionEntry(
            fingerprint=fingerprint,
            original_length=500,
            compacted_text="compacted content",
            compacted_length=17,
            hit_count=0,
            created_at=1000.0,
            last_accessed=1000.0,
        )

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", True)
    @patch("llm_shared.optimization.token_optimizer.get_redis_client")
    def test_put_and_get_round_trip(self, mock_get_redis):
        """L2Cache put/get should round-trip a CompactionEntry via Redis."""
        store = {}
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: store.get(key)
        mock_redis.setex.side_effect = lambda key, ttl, data: store.__setitem__(key, data)
        mock_get_redis.return_value = mock_redis

        cache = L2Cache(ttl_seconds=3600, key_prefix="test:")
        entry = self._make_entry()
        cache.put("abc123", entry)
        result = cache.get("abc123")

        assert result is not None
        assert result.fingerprint == "abc123"
        assert result.compacted_text == "compacted content"
        assert result.original_length == 500

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", True)
    @patch("llm_shared.optimization.token_optimizer.get_redis_client")
    def test_get_missing_key_returns_none(self, mock_get_redis):
        """L2Cache.get for a missing key should return None."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        cache = L2Cache(ttl_seconds=3600, key_prefix="test:")
        result = cache.get("nonexistent")
        assert result is None


class TestL2CacheGracefulDegradation:
    """Tests for L2Cache when Redis is unavailable."""

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", True)
    @patch(
        "llm_shared.optimization.token_optimizer.get_redis_client",
        side_effect=Exception("Connection refused"),
    )
    def test_get_returns_none_when_redis_fails(self, mock_get_redis):
        """L2Cache.get should return None when Redis connection fails."""
        cache = L2Cache()
        result = cache.get("any_key")
        assert result is None

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", True)
    @patch(
        "llm_shared.optimization.token_optimizer.get_redis_client",
        side_effect=Exception("Connection refused"),
    )
    def test_put_does_not_raise_when_redis_fails(self, mock_get_redis):
        """L2Cache.put should not raise when Redis connection fails."""
        cache = L2Cache()
        entry = CompactionEntry(
            fingerprint="abc",
            original_length=100,
            compacted_text="short",
            compacted_length=5,
        )
        # Should not raise
        cache.put("abc", entry)

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", False)
    def test_get_returns_none_when_redis_unavailable(self):
        """L2Cache.get should return None when redis module not importable."""
        cache = L2Cache()
        result = cache.get("any_key")
        assert result is None

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", False)
    def test_put_noop_when_redis_unavailable(self):
        """L2Cache.put should silently no-op when redis not importable."""
        cache = L2Cache()
        entry = CompactionEntry(
            fingerprint="abc",
            original_length=100,
            compacted_text="short",
            compacted_length=5,
        )
        cache.put("abc", entry)  # should not raise


class TestL1ToL2Fallback:
    """Tests for L1 miss -> L2 hit fallback in TokenOptimizer._lookup."""

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", True)
    @patch("llm_shared.optimization.token_optimizer.get_redis_client")
    def test_l2_hit_promotes_to_l1(self, mock_get_redis):
        """When L1 misses but L2 hits, entry should be promoted to L1."""
        now = time.time()
        entry = CompactionEntry(
            fingerprint="fp_test",
            original_length=500,
            compacted_text="compact",
            compacted_length=7,
            hit_count=0,
            created_at=now,
            last_accessed=now,
        )
        serialized = json.dumps(
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

        mock_redis = MagicMock()
        mock_redis.get.return_value = serialized
        mock_get_redis.return_value = mock_redis

        opt = TokenOptimizer(TokenOptimizerConfig(enabled=True))
        # L1 is empty, L2 has the entry
        result = opt._lookup("fp_test")
        assert result is not None
        assert result.compacted_text == "compact"

        # Verify it was promoted to L1
        l1_result = opt._l1.get("fp_test")
        assert l1_result is not None
        assert l1_result.compacted_text == "compact"

    @patch("llm_shared.optimization.token_optimizer.REDIS_AVAILABLE", False)
    def test_returns_none_when_both_caches_miss(self):
        """_lookup returns None when both L1 and L2 miss."""
        opt = TokenOptimizer(TokenOptimizerConfig(enabled=True))
        result = opt._lookup("nonexistent_fp")
        assert result is None


class TestGetTokenOptimizerSingleton:
    """Tests for the get_token_optimizer module-level singleton."""

    @patch("llm_shared.optimization.token_optimizer._optimizer", None)
    def test_returns_token_optimizer_instance(self):
        """get_token_optimizer should return a TokenOptimizer."""
        result = get_token_optimizer()
        assert isinstance(result, TokenOptimizer)

    @patch("llm_shared.optimization.token_optimizer._optimizer", None)
    def test_returns_same_instance_on_repeated_calls(self):
        """get_token_optimizer should return the same singleton instance."""
        first = get_token_optimizer()
        second = get_token_optimizer()
        assert first is second

    @patch("llm_shared.optimization.token_optimizer._optimizer", None)
    def test_accepts_custom_config(self):
        """get_token_optimizer should accept a custom config on first call."""
        config = TokenOptimizerConfig(enabled=False, min_repeat_threshold=5)
        result = get_token_optimizer(config)
        assert result.enabled is False

    @patch("llm_shared.optimization.token_optimizer._optimizer", None)
    def test_ignores_config_on_subsequent_calls(self):
        """Once created, get_token_optimizer ignores new config args."""
        config1 = TokenOptimizerConfig(enabled=True)
        first = get_token_optimizer(config1)
        config2 = TokenOptimizerConfig(enabled=False)
        second = get_token_optimizer(config2)
        assert first is second
        assert second.enabled is True
