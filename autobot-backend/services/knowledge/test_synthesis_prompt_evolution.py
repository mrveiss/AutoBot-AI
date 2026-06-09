# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for autonomous synthesis prompt evolution (#4675).

Covers:
- KBSynthesizer._score_synthesis_output
- KBSynthesizer._select_prompt_variant
"""

from __future__ import annotations

import sys
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs for optional heavy deps so the module can be imported.
# ---------------------------------------------------------------------------
sys.modules.setdefault("utils.chromadb_client", MagicMock())
sys.modules.setdefault("autobot_shared", MagicMock())
sys.modules.setdefault("autobot_shared.redis_client", MagicMock())

from services.knowledge.kb_synthesizer import KBSynthesizer  # noqa: E402

# ---------------------------------------------------------------------------
# _score_synthesis_output
# ---------------------------------------------------------------------------


class TestScoreSynthesisOutput:
    """Tests for KBSynthesizer._score_synthesis_output."""

    def test_empty_text_returns_zero(self) -> None:
        assert KBSynthesizer._score_synthesis_output("") == 0.0
        assert KBSynthesizer._score_synthesis_output("   ") == 0.0

    def test_normal_text_returns_high_score(self) -> None:
        # 100 distinct words, each a unique sentence → near-perfect score.
        words = " ".join(f"word{i}" for i in range(100))
        score = KBSynthesizer._score_synthesis_output(words)
        assert 0.5 < score <= 1.0

    def test_very_long_text_penalised(self) -> None:
        # 5000 words — well beyond the 2000-word sweet spot.
        long_text = " ".join(f"word{i}" for i in range(5000))
        score = KBSynthesizer._score_synthesis_output(long_text)
        assert score < 1.0

    def test_very_short_text_penalised(self) -> None:
        # 10 words — below the 50-word minimum.
        short_text = " ".join(f"word{i}" for i in range(10))
        score = KBSynthesizer._score_synthesis_output(short_text)
        assert score < 0.6  # token_score is 10/50 = 0.2; total < 0.52

    def test_repetitive_text_penalised(self) -> None:
        # 200 copies of the same sentence → uniqueness_score near 1/200.
        sentence = "This is a repeated sentence"
        repetitive = ". ".join([sentence] * 200) + "."
        score = KBSynthesizer._score_synthesis_output(repetitive)
        # High word count → token_score=1.0; uniqueness near 0 → total < 0.7
        assert score < 0.7

    def test_score_in_bounds(self) -> None:
        for text in ["", "a", "word " * 50, "word " * 3000]:
            score = KBSynthesizer._score_synthesis_output(text)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _select_prompt_variant
# ---------------------------------------------------------------------------


def _make_synthesizer(provenance_entries: List[dict]) -> KBSynthesizer:
    """Create a KBSynthesizer with a mocked provenance log."""
    mock_log = MagicMock()
    mock_log.get_recent = AsyncMock(return_value=provenance_entries)
    synth = KBSynthesizer(llm_service=MagicMock(), provenance_log=mock_log)
    return synth


@pytest.mark.asyncio
class TestSelectPromptVariant:
    """Tests for KBSynthesizer._select_prompt_variant."""

    async def test_no_variants_returns_fallback(self) -> None:
        synth = _make_synthesizer([])
        prompt, vid = await synth._select_prompt_variant("col", [], "base_text")
        assert prompt == "base_text"
        assert vid == "base"

    async def test_cold_start_returns_first_untried(self) -> None:
        """With no history, should return the first untried variant (base)."""
        synth = _make_synthesizer([])
        variants = ["variant_text_A", "variant_text_B"]
        prompt, vid = await synth._select_prompt_variant("col", variants, "base_text")
        # Cold-start: base is tried first because it's in all_variants first.
        assert vid == "base"
        assert prompt == "base_text"

    async def test_ucb1_picks_best_after_history(self) -> None:
        """After runs, UCB1 should prefer the variant with the highest avg score."""
        entries = [
            # variant_0 ran once with low score.
            {"prompt_template": "col", "collection_name": "col", "prompt_variant": "base", "score": 0.9},
            {"prompt_template": "col", "collection_name": "col", "prompt_variant": "variant_0", "score": 0.2},
            {"prompt_template": "col", "collection_name": "col", "prompt_variant": "variant_1", "score": 0.8},
        ]
        synth = _make_synthesizer(entries)
        variants = ["variant_text_A", "variant_text_B"]
        # All variants have been tried; UCB1 should favour base or variant_1.
        prompt, vid = await synth._select_prompt_variant("col", variants, "base_text")
        # base has score 0.9 and variant_1 has 0.8; base should win UCB1.
        assert vid in ("base", "variant_1")

    async def test_provenance_read_failure_returns_fallback(self) -> None:
        """If provenance log throws, fall back to base gracefully."""
        mock_log = MagicMock()
        mock_log.get_recent = AsyncMock(side_effect=RuntimeError("redis down"))
        synth = KBSynthesizer(llm_service=MagicMock(), provenance_log=mock_log)
        prompt, vid = await synth._select_prompt_variant("col", ["v_text"], "base_text")
        assert prompt == "base_text"
        assert vid == "base"

    async def test_entries_filtered_by_collection(self) -> None:
        """Entries for a different collection must not affect selection."""
        entries = [
            # All entries belong to a different collection.
            {
                "prompt_template": "other_col",
                "collection_name": "other_col",
                "prompt_variant": "variant_0",
                "score": 0.95,
            },
        ]
        synth = _make_synthesizer(entries)
        variants = ["v_text"]
        # Cold-start for "col" → should return "base" first.
        prompt, vid = await synth._select_prompt_variant("col", variants, "base_text")
        assert vid == "base"
