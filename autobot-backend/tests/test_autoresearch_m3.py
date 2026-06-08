# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration test for AutoResearch M3 — Issue #2600."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.autoresearch.knowledge_synthesizer import KnowledgeSynthesizer
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    HyperParams,
)
from services.autoresearch.prompt_optimizer import PromptOptimizer, PromptOptTarget
from services.autoresearch.scorers import LLMJudgeScorer


class TestM3Integration:
    """Test the full M3 pipeline: optimize -> synthesize -> query insights."""

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        # For mutation: return variants
        mutation_response = MagicMock()
        mutation_response.content = json.dumps(["variant A", "variant B"])

        # For judge: return rating
        judge_response = MagicMock()
        judge_response.content = '{"rating": 7, "reasoning": "Good"}'

        # For synthesis: return insights
        synthesis_response = MagicMock()
        synthesis_response.content = json.dumps(
            [
                {
                    "statement": "Higher warmup improves convergence",
                    "confidence": 0.9,
                    "supporting_experiments": ["e1"],
                    "related_hyperparams": ["warmup_steps"],
                }
            ]
        )

        # Cycle through responses
        llm.chat.side_effect = [
            mutation_response,  # optimizer mutation
            judge_response,  # scorer: variant A
            judge_response,  # scorer: variant B
            synthesis_response,  # knowledge synthesis
        ]
        return llm

    @pytest.mark.asyncio
    async def test_optimize_then_synthesize(self, mock_llm):
        # Setup scorer
        scorer = LLMJudgeScorer(
            llm_service=mock_llm,
            criteria=["relevance"],
        )

        # Setup optimizer
        optimizer = PromptOptimizer(
            scorers={"llm_judge": scorer},
            llm_service=mock_llm,
        )
        optimizer._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test_agent",
            current_prompt="base prompt",
            scorer_chain=["llm_judge"],
            mutation_count=2,
            top_k=1,
        )

        async def benchmark(prompt: str) -> str:
            return f"Output from: {prompt}"

        # Run optimization
        session = await optimizer.optimize(target, benchmark, max_rounds=1)
        assert session.status.value == "completed"
        assert session.best_variant is not None

        # Setup synthesizer with mock store
        mock_store = AsyncMock()
        mock_store.list_experiments.return_value = [
            Experiment(
                id="e1",
                hypothesis="test",
                state=ExperimentState.KEPT,
                hyperparams=HyperParams(warmup_steps=300),
                result=ExperimentResult(val_bpb=4.5),
                tags=["session:test-session"],
            ),
        ]

        synthesizer = KnowledgeSynthesizer(
            store=mock_store,
            llm_service=mock_llm,
        )
        mock_collection = AsyncMock()
        synthesizer._insights_collection = mock_collection

        # Run synthesis
        insights = await synthesizer.synthesize_session("test-session")
        assert len(insights) == 1
        assert insights[0].statement == "Higher warmup improves convergence"
        mock_collection.upsert.assert_called_once()
