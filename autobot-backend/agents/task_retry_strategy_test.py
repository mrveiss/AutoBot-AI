# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for TaskRetryStrategy (Issue #930)
"""

import json
from unittest.mock import AsyncMock

import pytest
from agents.task_retry_strategy import RetryApproach, TaskRetryStrategy


@pytest.fixture
def strategy():
    return TaskRetryStrategy(llm_interface=None)


class TestRetryApproach:
    def test_defaults(self):
        approach = RetryApproach(
            task_type="code_gen",
            goal="write a function",
            original_strategy="direct",
            failure_reason="incomplete output",
            suggested_prompt="retry prompt",
            suggested_approach="step by step",
        )
        assert approach.confidence == 0.5
        assert approach.tool_sequence == []
        assert approach.timestamp  # auto-populated


class TestTaskRetryStrategy:
    def test_build_retry_prompt_contains_goal(self, strategy):
        prompt = strategy._build_retry_prompt(
            "code_gen", "my goal", "direct", "incomplete", 0.3
        )
        assert "my goal" in prompt
        assert "0.30" in prompt
        assert "code_gen" in prompt

    def test_fallback_retry_returns_approach(self, strategy):
        result = strategy._fallback_retry("t", "g", "direct", "failed")
        assert isinstance(result, RetryApproach)
        assert result.confidence == 0.3
        assert "step-by-step" in result.suggested_approach

    def test_parse_retry_response_valid_json(self, strategy):
        data = {
            "suggested_prompt": "better prompt",
            "suggested_approach": "decompose",
            "tool_sequence": ["grep", "edit"],
            "rationale": "more focused",
            "confidence": 0.8,
        }
        result = strategy._parse_retry_response(
            json.dumps(data), "t", "g", "old", "reason"
        )
        assert result.suggested_prompt == "better prompt"
        assert result.confidence == 0.8
        assert result.tool_sequence == ["grep", "edit"]

    def test_parse_retry_response_invalid_json_falls_back(self, strategy):
        result = strategy._parse_retry_response("not json", "t", "g", "old", "reason")
        assert isinstance(result, RetryApproach)
        assert result.confidence == 0.3  # fallback confidence

    @pytest.mark.asyncio
    async def test_generate_retry_uses_llm(self, strategy):
        mock_llm = AsyncMock()
        mock_llm.chat_completion_async = AsyncMock(
            return_value=json.dumps(
                {
                    "suggested_prompt": "new prompt",
                    "suggested_approach": "different angle",
                    "tool_sequence": [],
                    "rationale": "because",
                    "confidence": 0.7,
                }
            )
        )
        strategy._llm = mock_llm
        result = await strategy.generate_retry(
            task_type="analysis",
            goal="analyze code",
            original_strategy="direct",
            failure_reason="too broad",
            previous_score=0.4,
        )
        assert result.suggested_prompt == "new prompt"
        assert result.confidence == 0.7
        mock_llm.chat_completion_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_retry_falls_back_on_llm_error(self, strategy):
        mock_llm = AsyncMock()
        mock_llm.chat_completion_async = AsyncMock(
            side_effect=Exception("LLM unavailable")
        )
        strategy._llm = mock_llm
        result = await strategy.generate_retry("t", "g", "old", "reason", 0.2)
        assert isinstance(result, RetryApproach)
        assert result.confidence == 0.3
