# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for ContextCompressionService. Issue #3770."""

import pytest

from services.memory.compression import (
    _DEFAULT_COMPRESSION_THRESHOLD,
    ContextCompressionService,
    _estimate_tokens,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_svc(config_path=None) -> ContextCompressionService:
    """Return a service instance without loading the real YAML (path missing)."""
    # Pass a non-existent path so _load_thresholds falls back gracefully.
    return ContextCompressionService(config_path=config_path)


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert _estimate_tokens("") == 0

    def test_single_word(self) -> None:
        # 1 word * 1.3 = int(1.3) = 1
        assert _estimate_tokens("hello") == 1

    def test_multiple_words(self) -> None:
        text = " ".join(["word"] * 10)
        # 10 * 1.3 = 13
        assert _estimate_tokens(text) == 13


# ---------------------------------------------------------------------------
# should_compress
# ---------------------------------------------------------------------------


class TestShouldCompress:
    @pytest.mark.asyncio
    async def test_unknown_model_uses_default_threshold(self) -> None:
        svc = _make_svc()
        # Below default threshold — should not compress
        assert not await svc.should_compress("unknown-model", 1000)

    @pytest.mark.asyncio
    async def test_above_threshold_triggers_compression(self) -> None:
        svc = _make_svc()
        # Inject a model with threshold == 8192
        svc._model_thresholds["phi3"] = 8192
        assert await svc.should_compress("phi3", 9000)

    @pytest.mark.asyncio
    async def test_at_threshold_does_not_compress(self) -> None:
        svc = _make_svc()
        svc._model_thresholds["phi3"] = 8192
        # Exactly at threshold — not strictly greater, so no compression
        assert not await svc.should_compress("phi3", 8192)

    @pytest.mark.asyncio
    async def test_large_model_compresses_when_content_exceeds_threshold(self) -> None:
        """Large models compress only when content genuinely exceeds their threshold."""
        svc = _make_svc()
        svc._model_thresholds["gpt-4o"] = 32768
        # Content well below the large-model threshold — no compression
        assert not await svc.should_compress("gpt-4o", 10000)
        # Content above the large-model threshold — compression fires
        assert await svc.should_compress("gpt-4o", 40000)


# ---------------------------------------------------------------------------
# compress_history
# ---------------------------------------------------------------------------


class TestCompressHistory:
    @pytest.mark.asyncio
    async def test_empty_history_unchanged(self) -> None:
        svc = _make_svc()
        result = await svc.compress_history([], 1000)
        assert result == []

    @pytest.mark.asyncio
    async def test_fits_within_budget_unchanged(self) -> None:
        svc = _make_svc()
        messages = [_msg("user", "hi"), _msg("assistant", "hello")]
        # Budget large enough — no summary prepended
        result = await svc.compress_history(messages, 10000)
        assert result == messages

    @pytest.mark.asyncio
    async def test_drops_old_messages_and_prepends_summary(self) -> None:
        svc = _make_svc()
        # Create 5 messages; each ~6 tokens ("word word word word word .")
        messages = [_msg("user", " ".join(["word"] * 5 + ["."])) for _ in range(5)]
        # Allow budget for only 2 messages (~6 tokens each -> 12 tokens needed)
        # Each message is 6 words * 1.3 = 7 tokens
        result = await svc.compress_history(messages, 15)
        # First element must be an assistant summary (system mid-history is invalid)
        assert result[0]["role"] == "assistant"
        assert "omitted" in result[0]["content"]
        # Fewer messages than original
        assert len(result) < len(messages) + 1  # +1 for the summary

    @pytest.mark.asyncio
    async def test_preserves_order_of_kept_messages(self) -> None:
        svc = _make_svc()
        messages = [
            _msg("user", "first"),
            _msg("assistant", "second"),
            _msg("user", "third"),
        ]
        result = await svc.compress_history(messages, 5)
        # Kept messages should be in original order (oldest to newest)
        contents = [m["content"] for m in result if m["role"] != "system"]
        for i in range(len(contents) - 1):
            idx_a = next(j for j, m in enumerate(messages) if m["content"] == contents[i])
            idx_b = next(j for j, m in enumerate(messages) if m["content"] == contents[i + 1])
            assert idx_a < idx_b

    @pytest.mark.asyncio
    async def test_error_falls_back_to_original(self) -> None:
        """On internal error, original messages returned unchanged."""
        svc = _make_svc()
        # Pass non-dict items to force an error path
        bad_messages = [None, None]
        result = await svc.compress_history(bad_messages, 100)
        assert result == bad_messages


# ---------------------------------------------------------------------------
# compress_kb_results
# ---------------------------------------------------------------------------


class TestCompressKbResults:
    @pytest.mark.asyncio
    async def test_empty_results_unchanged(self) -> None:
        svc = _make_svc()
        result = await svc.compress_kb_results([], 1000)
        assert result == []

    @pytest.mark.asyncio
    async def test_high_score_kept_first(self) -> None:
        svc = _make_svc()
        results = [
            {"score": 0.1, "content": "low score fact"},
            {"score": 0.9, "content": "high score fact"},
            {"score": 0.5, "content": "medium score fact"},
        ]
        # Budget for ~2 results (each ~3 words * 1.3 = 3 tokens -> ~6 total for 2)
        kept = await svc.compress_kb_results(results, 6)
        # Highest-score entries should be preferred
        assert kept[0]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_all_fit_within_budget(self) -> None:
        svc = _make_svc()
        results = [
            {"score": 0.8, "content": "fact a"},
            {"score": 0.6, "content": "fact b"},
        ]
        kept = await svc.compress_kb_results(results, 10000)
        assert len(kept) == 2

    @pytest.mark.asyncio
    async def test_object_with_score_attribute(self) -> None:
        """Results may be objects with .score and .content attributes."""

        class KBResult:
            def __init__(self, score, content):
                self.score = score
                self.content = content

        svc = _make_svc()
        results = [KBResult(0.3, "low"), KBResult(0.9, "high")]
        kept = await svc.compress_kb_results(results, 10000)
        assert len(kept) == 2
        assert kept[0].score == 0.9

    @pytest.mark.asyncio
    async def test_error_falls_back_to_original(self) -> None:
        """On internal error, original results returned unchanged."""
        svc = _make_svc()

        class Broken:
            @property
            def score(self):
                raise RuntimeError("boom")

            @property
            def content(self):
                raise RuntimeError("boom")

        bad = [Broken()]
        result = await svc.compress_kb_results(bad, 1000)
        assert result == bad


# ---------------------------------------------------------------------------
# Load thresholds from real YAML
# ---------------------------------------------------------------------------


class TestLoadThresholds:
    def test_phi3_threshold_matches_context_window(self) -> None:
        """phi3 compression_threshold must equal its context_window_tokens (4096)."""
        from pathlib import Path

        # Locate the real YAML relative to this test file
        yaml_path = Path(__file__).parent.parent.parent / "config" / "context_windows.yaml"
        if not yaml_path.exists():
            pytest.skip("context_windows.yaml not found")

        svc = ContextCompressionService(config_path=yaml_path)
        assert svc._get_threshold("phi3") == 4096

    def test_large_model_threshold_above_default(self) -> None:
        """Large models (e.g. gpt-4o) should have threshold > 8192."""
        from pathlib import Path

        yaml_path = Path(__file__).parent.parent.parent / "config" / "context_windows.yaml"
        if not yaml_path.exists():
            pytest.skip("context_windows.yaml not found")

        svc = ContextCompressionService(config_path=yaml_path)
        assert svc._get_threshold("gpt-4o") > _DEFAULT_COMPRESSION_THRESHOLD


# ---------------------------------------------------------------------------
# Issue #3811: compression_threshold <= context_window_tokens validation
# ---------------------------------------------------------------------------


class TestCompressionThresholdValidation:
    """Ensure invalid configs (threshold > context_window) fail fast at load time."""

    def _write_yaml(self, tmp_path, models_block: str) -> "Path":
        pass

        content = f"models:\n{models_block}\ntoken_estimation:\n  chars_per_token: 4\n  safety_margin: 0.9\n"
        p = tmp_path / "context_windows.yaml"
        p.write_text(content, encoding="utf-8")
        return p

    def test_threshold_exceeds_context_window_raises(self, tmp_path) -> None:
        """Loading a YAML where compression_threshold > context_window_tokens must raise ValueError."""
        yaml_path = self._write_yaml(
            tmp_path,
            "  tiny-model:\n    context_window_tokens: 4096\n    max_output_tokens: 2048\n    compression_threshold: 8192\n",
        )
        with pytest.raises(ValueError, match="compression_threshold"):
            ContextCompressionService(config_path=yaml_path)

    def test_threshold_equal_context_window_is_valid(self, tmp_path) -> None:
        """compression_threshold == context_window_tokens must not raise."""
        yaml_path = self._write_yaml(
            tmp_path,
            "  small-model:\n    context_window_tokens: 4096\n    max_output_tokens: 2048\n    compression_threshold: 4096\n",
        )
        svc = ContextCompressionService(config_path=yaml_path)
        assert svc._get_threshold("small-model") == 4096

    def test_threshold_below_context_window_is_valid(self, tmp_path) -> None:
        """compression_threshold < context_window_tokens must not raise."""
        yaml_path = self._write_yaml(
            tmp_path,
            "  big-model:\n    context_window_tokens: 128000\n    max_output_tokens: 4096\n    compression_threshold: 32768\n",
        )
        svc = ContextCompressionService(config_path=yaml_path)
        assert svc._get_threshold("big-model") == 32768

    def test_real_yaml_passes_validation(self) -> None:
        """The committed context_windows.yaml must pass the validator for all models."""
        from pathlib import Path

        yaml_path = Path(__file__).parent.parent.parent / "config" / "context_windows.yaml"
        if not yaml_path.exists():
            pytest.skip("context_windows.yaml not found")

        # Must not raise
        svc = ContextCompressionService(config_path=yaml_path)
        assert len(svc._model_thresholds) > 0

    def test_missing_context_window_tokens_skips_validation(self, tmp_path) -> None:
        """A model entry without context_window_tokens must not raise (threshold defaults apply)."""
        yaml_path = self._write_yaml(
            tmp_path,
            "  legacy-model:\n    max_output_tokens: 2048\n    compression_threshold: 99999\n",
        )
        # No context_window_tokens key — validation is skipped, no error raised
        svc = ContextCompressionService(config_path=yaml_path)
        assert svc._get_threshold("legacy-model") == 99999
