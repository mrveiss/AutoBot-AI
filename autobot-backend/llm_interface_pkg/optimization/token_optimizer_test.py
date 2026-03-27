# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for TokenOptimizer — Issue #2098."""

from .token_optimizer import (
    CompactionEntry,
    ContextFingerprinter,
    FrequencyTracker,
    L1Cache,
    TokenOptimizer,
    TokenOptimizerConfig,
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
        config = TokenOptimizerConfig(
            enabled=True, min_repeat_threshold=2, min_block_length=200, **kwargs
        )
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
