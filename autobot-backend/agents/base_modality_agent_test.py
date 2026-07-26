# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Tests for BaseModalityAgent (Issue #12658).

Covers:
- import-smoke + MRO for the base and all 7 modality-agent subclasses
- per-agent hook configuration (temperature/max_tokens/error message) is
  preserved exactly as it was before the de-duplication
- `_extract_content`/`process_query` are defined exactly once (in the base;
  subclasses only inherit)
- the one genuine per-agent behavioural difference (SentimentAnalysisAgent's
  diary write) survives via the `_after_success` hook
- the default `_after_success` hook is a no-op passthrough for every other
  agent
"""

from unittest.mock import AsyncMock

import pytest

from agents.audio_processing_agent import AudioProcessingAgent
from agents.base_modality_agent import BaseModalityAgent
from agents.code_generation_agent import CodeGenerationAgent
from agents.data_analysis_agent import DataAnalysisAgent
from agents.image_analysis_agent import ImageAnalysisAgent
from agents.sentiment_analysis_agent import SentimentAnalysisAgent
from agents.summarization_agent import SummarizationAgent
from agents.translation_agent import TranslationAgent
from constants.threshold_constants import LLMDefaults

MODALITY_AGENTS = [
    AudioProcessingAgent,
    CodeGenerationAgent,
    DataAnalysisAgent,
    ImageAnalysisAgent,
    SentimentAnalysisAgent,
    SummarizationAgent,
    TranslationAgent,
]


class TestBaseModalityAgentMRO:
    """Every modality agent inherits BaseModalityAgent and shares one impl."""

    @pytest.mark.parametrize("agent_cls", MODALITY_AGENTS)
    def test_inherits_base_modality_agent(self, agent_cls):
        assert issubclass(agent_cls, BaseModalityAgent)

    @pytest.mark.parametrize("agent_cls", MODALITY_AGENTS)
    def test_process_query_defined_once_in_base(self, agent_cls):
        assert "process_query" not in agent_cls.__dict__
        assert agent_cls.process_query is BaseModalityAgent.process_query

    @pytest.mark.parametrize("agent_cls", MODALITY_AGENTS)
    def test_extract_content_defined_once_in_base(self, agent_cls):
        assert "_extract_content" not in agent_cls.__dict__
        assert agent_cls._extract_content is BaseModalityAgent._extract_content


class TestPerAgentHookConfiguration:
    """Each subclass configures its own genuine per-modality constants."""

    EXPECTED = {
        AudioProcessingAgent: (0.3, LLMDefaults.SYNTHESIS_MAX_TOKENS, "Error processing audio. Please try again."),
        CodeGenerationAgent: (
            0.2,
            LLMDefaults.EXTENDED_MAX_TOKENS,
            "Error generating code. Please try rephrasing your request.",
        ),
        DataAnalysisAgent: (
            0.3,
            LLMDefaults.SYNTHESIS_MAX_TOKENS,
            "Error analyzing data. Please try rephrasing your request.",
        ),
        ImageAnalysisAgent: (0.5, LLMDefaults.SYNTHESIS_MAX_TOKENS, "Error analyzing image. Please try again."),
        SentimentAnalysisAgent: (0.1, LLMDefaults.CHAT_MAX_TOKENS, "Error analyzing sentiment. Please try again."),
        SummarizationAgent: (0.5, LLMDefaults.SYNTHESIS_MAX_TOKENS, "Error generating summary. Please try again."),
        TranslationAgent: (0.3, LLMDefaults.CHAT_MAX_TOKENS, "Error processing translation. Please try again."),
    }

    @pytest.mark.parametrize("agent_cls", MODALITY_AGENTS)
    def test_query_constants_match_pre_refactor_values(self, agent_cls):
        temperature, max_tokens, error_message = self.EXPECTED[agent_cls]
        assert agent_cls.QUERY_TEMPERATURE == temperature
        assert agent_cls.QUERY_MAX_TOKENS == max_tokens
        assert agent_cls.QUERY_ERROR_MESSAGE == error_message


class TestExtractContent:
    """`_extract_content` behavior is unchanged by the move to the base class."""

    def _agent(self):
        return AudioProcessingAgent.__new__(AudioProcessingAgent)

    def test_plain_string_is_stripped(self):
        assert self._agent()._extract_content("  hello  ") == "hello"

    def test_message_content_dict(self):
        assert self._agent()._extract_content({"message": {"content": " hi "}}) == "hi"

    def test_choices_message_content(self):
        response = {"choices": [{"message": {"content": " choice "}}]}
        assert self._agent()._extract_content(response) == "choice"

    def test_top_level_content(self):
        assert self._agent()._extract_content({"content": " raw "}) == "raw"

    def test_unrecognized_dict_falls_back_to_str(self):
        assert self._agent()._extract_content({"unrelated": 1}) == "{'unrelated': 1}"


class TestAfterSuccessHook:
    """The one genuine per-agent difference: SentimentAnalysisAgent's diary write."""

    @pytest.mark.asyncio
    async def test_sentiment_after_success_writes_diary_entry(self):
        inst = SentimentAnalysisAgent.__new__(SentimentAnalysisAgent)
        diary_write = AsyncMock()

        class FakeDiary:
            write = diary_write

        class FakeMemoryManager:
            agent_diary = FakeDiary()

        inst._memory_manager = FakeMemoryManager()
        inst.AGENT_ID = "sentiment_analysis"

        result = {"status": "success", "response": "positive"}
        out = await inst._after_success(result, {}, "sess-123")

        assert out is result
        diary_write.assert_awaited_once()
        args, kwargs = diary_write.call_args
        assert args[0] == "sentiment_analysis"
        assert args[1] == "sess-123"
        assert args[2] == "SESSION:sess-123|ACTION:sentiment_analysis|OUTCOME:success|TOPIC:sentiment"
        assert kwargs.get("topic") == "sentiment"

    @pytest.mark.asyncio
    async def test_default_after_success_is_noop_passthrough(self):
        """Every other agent uses the base default: pass the result through unchanged."""
        for agent_cls in MODALITY_AGENTS:
            if agent_cls is SentimentAnalysisAgent:
                continue
            inst = agent_cls.__new__(agent_cls)
            result = {"status": "success", "response": "x"}
            out = await inst._after_success(result, {}, "sess-1")
            assert out is result
