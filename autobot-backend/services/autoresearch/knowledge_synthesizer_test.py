# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for knowledge synthesizer — Issue #2600."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.autoresearch.knowledge_synthesizer import (
    ExperimentInsight,
    KnowledgeSynthesizer,
)
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    HyperParams,
)


class TestExperimentInsight:
    def test_to_dict(self) -> None:
        insight = ExperimentInsight(
            statement="Dropout < 0.1 degrades val_bpb",
            confidence=0.85,
            supporting_experiments=["exp1", "exp2"],
            related_hyperparams=["dropout"],
        )
        d = insight.to_dict()
        assert d["statement"] == "Dropout < 0.1 degrades val_bpb"
        assert d["confidence"] == 0.85
        assert len(d["supporting_experiments"]) == 2


class TestKnowledgeSynthesizer:
    @pytest.fixture
    def mock_store(self):
        store = AsyncMock()
        store.list_experiments.return_value = [
            Experiment(
                id="e1",
                hypothesis="Lower dropout to 0.05",
                state=ExperimentState.DISCARDED,
                hyperparams=HyperParams(dropout=0.05),
                result=ExperimentResult(val_bpb=6.0),
                baseline_val_bpb=5.5,
                tags=["session:session-1"],
            ),
            Experiment(
                id="e2",
                hypothesis="Increase warmup to 300",
                state=ExperimentState.KEPT,
                hyperparams=HyperParams(warmup_steps=300),
                result=ExperimentResult(val_bpb=5.2),
                baseline_val_bpb=5.5,
                tags=["session:session-1"],
            ),
        ]
        return store

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            [
                {
                    "statement": "Warmup steps >= 300 improve convergence",
                    "confidence": 0.8,
                    "supporting_experiments": ["e2"],
                    "related_hyperparams": ["warmup_steps"],
                }
            ]
        )
        llm.chat.return_value = mock_response
        return llm

    @pytest.fixture
    def mock_chromadb(self):
        collection = AsyncMock()
        return collection

    @pytest.fixture
    def synthesizer(self, mock_store, mock_llm, mock_chromadb):
        s = KnowledgeSynthesizer(
            store=mock_store,
            llm_service=mock_llm,
        )
        s._insights_collection = mock_chromadb
        return s

    @pytest.mark.asyncio
    async def test_synthesize_session(self, synthesizer, mock_llm, mock_chromadb) -> None:
        insights = await synthesizer.synthesize_session("session-1")

        assert len(insights) == 1
        assert insights[0].statement == "Warmup steps >= 300 improve convergence"
        assert insights[0].confidence == 0.8
        mock_llm.chat.assert_called_once()
        mock_chromadb.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesize_empty_session_returns_empty(self, synthesizer) -> None:
        """No experiments tagged with session returns [] without calling LLM — Issue #3211."""
        insights = await synthesizer.synthesize_session("session-nonexistent")
        assert insights == []

    @pytest.mark.asyncio
    async def test_synthesize_session_llm_failure_returns_empty(self, synthesizer, mock_llm) -> None:
        """LLM exception during synthesis returns [] gracefully — Issue #3211."""
        mock_llm.chat.side_effect = RuntimeError("LLM service unavailable")
        insights = await synthesizer.synthesize_session("session-1")
        assert insights == []

    @pytest.mark.asyncio
    async def test_query_insights(self, synthesizer, mock_chromadb) -> None:
        mock_chromadb.query.return_value = {
            "ids": [["i1"]],
            "documents": [["Warmup steps >= 300 improve convergence"]],
            "metadatas": [
                [
                    {
                        "confidence": 0.8,
                        "supporting_experiments": "e2",
                        "related_hyperparams": "warmup_steps",
                        "session_id": "s1",
                    }
                ]
            ],
        }
        results = await synthesizer.query_insights("warmup", limit=5)
        assert len(results) == 1
        assert "Warmup" in results[0].statement
