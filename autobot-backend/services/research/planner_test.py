# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services.research.planner (#12624).

Covers decomposition (including the pathological-LLM-output fallback),
branch pruning, and skip-known filtering in isolation from the orchestrator.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from autobot_shared.ssot_config import config
from services.research.planner import (
    SkippedSubQuestion,
    SubQuestion,
    decompose_question,
    filter_skip_known,
    prune_low_value,
)


def _llm_returning(content: str, error: str | None = None) -> AsyncMock:
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=SimpleNamespace(content=content, error=error))
    return llm


class TestDecomposeQuestion:
    async def test_parses_valid_json_into_subquestions(self):
        llm = _llm_returning('{"sub_questions": [{"text": "a?", "expected_value": 0.9}]}')
        result = await decompose_question(llm, "original?")
        assert result == [SubQuestion(text="a?", expected_value=0.9)]

    async def test_nonsense_llm_output_falls_back_to_original_question(self):
        """Malformed JSON must never expand the branch count — the safe fallback."""
        llm = _llm_returning("not json at all, just prose")
        result = await decompose_question(llm, "original?")
        assert result == [SubQuestion(text="original?", expected_value=1.0)]

    async def test_llm_error_falls_back_to_original_question(self):
        llm = _llm_returning("", error="timeout")
        result = await decompose_question(llm, "original?")
        assert result == [SubQuestion(text="original?", expected_value=1.0)]

    async def test_over_long_response_truncated_to_configured_branch_limit(self, monkeypatch):
        monkeypatch.setattr(config, "research_planner_max_subquestions_per_round", 2)
        payload = '{"sub_questions": [{"text": "a"}, {"text": "b"}, {"text": "c"}, {"text": "d"}]}'
        llm = _llm_returning(payload)
        result = await decompose_question(llm, "q")
        assert len(result) == 2

    async def test_confidence_clamped_to_unit_range(self):
        llm = _llm_returning('{"sub_questions": [{"text": "a", "expected_value": 5.0}]}')
        result = await decompose_question(llm, "q")
        assert result[0].expected_value == 1.0


class TestPruneLowValue:
    def test_drops_branches_below_threshold(self, monkeypatch):
        monkeypatch.setattr(config, "research_planner_prune_threshold", 0.5)
        subs = [SubQuestion("a", 0.9), SubQuestion("b", 0.1)]
        kept, pruned = prune_low_value(subs)
        assert kept == [SubQuestion("a", 0.9)]
        assert pruned == [SubQuestion("b", 0.1)]

    def test_never_prunes_to_zero_branches(self, monkeypatch):
        """Every branch scoring below threshold still keeps the single best one."""
        monkeypatch.setattr(config, "research_planner_prune_threshold", 0.9)
        subs = [SubQuestion("a", 0.2), SubQuestion("b", 0.4)]
        kept, pruned = prune_low_value(subs)
        assert kept == [SubQuestion("b", 0.4)]
        assert pruned == [SubQuestion("a", 0.2)]

    def test_all_high_scoring_keeps_every_branch(self, monkeypatch):
        """'Every branch scores high' must not be treated as a bug — nothing pruned."""
        monkeypatch.setattr(config, "research_planner_prune_threshold", 0.3)
        subs = [SubQuestion("a", 0.95), SubQuestion("b", 0.9)]
        kept, pruned = prune_low_value(subs)
        assert kept == subs
        assert pruned == []


class TestFilterSkipKnown:
    async def test_high_confidence_kb_fact_skips_the_subquestion(self, monkeypatch):
        monkeypatch.setattr(config, "research_planner_skip_known_confidence_threshold", 0.7)
        kb = AsyncMock()
        kb.search = AsyncMock(
            return_value=[{"metadata": {"fact_id": "fact-9", "confidence": 0.9}, "node_id": "fact-9"}]
        )
        to_search, skipped = await filter_skip_known(kb, [SubQuestion("known?", 1.0)])
        assert to_search == []
        assert skipped == [SkippedSubQuestion(text="known?", fact_id="fact-9", confidence=0.9)]

    async def test_below_threshold_kb_fact_does_not_skip(self, monkeypatch):
        monkeypatch.setattr(config, "research_planner_skip_known_confidence_threshold", 0.7)
        kb = AsyncMock()
        kb.search = AsyncMock(
            return_value=[{"metadata": {"fact_id": "fact-9", "confidence": 0.4}, "node_id": "fact-9"}]
        )
        to_search, skipped = await filter_skip_known(kb, [SubQuestion("unknown?", 1.0)])
        assert to_search == [SubQuestion("unknown?", 1.0)]
        assert skipped == []

    async def test_no_kb_results_does_not_skip(self):
        kb = AsyncMock()
        kb.search = AsyncMock(return_value=[])
        to_search, skipped = await filter_skip_known(kb, [SubQuestion("unknown?", 1.0)])
        assert to_search == [SubQuestion("unknown?", 1.0)]
        assert skipped == []
