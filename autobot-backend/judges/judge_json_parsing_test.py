# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Judge JSON parsing + structured_output wiring (#10672).

Forcing structured output and tolerating code fences stops valid judgments from
being silently turned into error/REJECT results by a bare json.loads().
"""

from __future__ import annotations

import json
import types
from unittest.mock import AsyncMock

import pytest

from judges import ERROR_MODEL_SENTINEL, BaseLLMJudge, _extract_json_object


def test_extract_json_bare():
    assert _extract_json_object('{"overall_score": 0.9}') == {"overall_score": 0.9}


def test_extract_json_fenced():
    assert _extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json_object('```\n{"a": 2}\n```') == {"a": 2}


def test_extract_json_raises_on_unparseable():
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("this is not json")


def test_extract_json_fenced_but_invalid_raises():
    # a fenced block whose body isn't valid JSON must still raise, not return junk
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("```json\nnot valid json\n```")


@pytest.mark.asyncio
async def test_a_malformed_judgment_retries_against_the_schema():
    """#17307: three attempts with the validation error fed back, then an error judgment.

    The old path indexed `overall_score` out of whatever arrived and raised on
    the first miss. Now the reply is validated against JUDGMENT_SCHEMA, the
    error goes back to the model, and only an exhausted retry budget produces
    the `llm_model_used == "error"` judgment the workflow gate reads.
    """
    judge = BaseLLMJudge.__new__(BaseLLMJudge)
    judge.judge_type = "test"
    judge.judgment_history = []
    judge.llm_interface = types.SimpleNamespace(
        chat=AsyncMock(return_value=types.SimpleNamespace(content="not a judgment at all", error=None))
    )
    judge._prepare_judgment_prompt = AsyncMock(return_value="judge this")

    result = await judge.make_judgment("subject", [], {})

    assert judge.llm_interface.chat.await_count == 3
    assert result.llm_model_used == ERROR_MODEL_SENTINEL
    assert result.recommendation == "REJECT"
    second_call_prompt = judge.llm_interface.chat.await_args_list[1].args[0][1]["content"]
    assert "previous response was invalid" in second_call_prompt


@pytest.mark.asyncio
async def test_a_valid_judgment_is_accepted_on_the_first_attempt():
    judge = BaseLLMJudge.__new__(BaseLLMJudge)
    judge.judge_type = "test"
    judge.judgment_history = []
    payload = json.dumps(
        {
            "overall_score": 0.82,
            "recommendation": "APPROVE",
            "confidence": "high",
            "reasoning": "the step is safe",
            "criterion_scores": [
                {"dimension": "safety", "score": 0.9, "confidence": "high", "reasoning": "no mutations"}
            ],
        }
    )
    judge.llm_interface = types.SimpleNamespace(
        chat=AsyncMock(return_value=types.SimpleNamespace(content=payload, error=None))
    )
    judge._prepare_judgment_prompt = AsyncMock(return_value="judge this")

    result = await judge.make_judgment("subject", [], {})

    assert judge.llm_interface.chat.await_count == 1
    assert (result.recommendation, result.overall_score) == ("APPROVE", 0.82)
    assert result.criterion_scores[0].dimension.value == "safety"


@pytest.mark.asyncio
async def test_a_recommendation_outside_the_enum_is_not_accepted():
    """An invented fifth recommendation would read as "not approved" at the gate."""
    judge = BaseLLMJudge.__new__(BaseLLMJudge)
    judge.judge_type = "test"
    judge.judgment_history = []
    payload = json.dumps(
        {"overall_score": 0.9, "recommendation": "SHIP IT", "confidence": "high", "reasoning": "looks fine"}
    )
    judge.llm_interface = types.SimpleNamespace(
        chat=AsyncMock(return_value=types.SimpleNamespace(content=payload, error=None))
    )
    judge._prepare_judgment_prompt = AsyncMock(return_value="judge this")

    result = await judge.make_judgment("subject", [], {})

    assert result.llm_model_used == ERROR_MODEL_SENTINEL


@pytest.mark.asyncio
async def test_judge_call_forces_structured_output():
    judge = BaseLLMJudge.__new__(BaseLLMJudge)  # bypass heavy __init__
    judge.judge_type = "test"
    judge.llm_interface = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content="{}")))

    await judge._get_llm_evaluation("evaluate this")

    _, kwargs = judge.llm_interface.chat.call_args
    assert kwargs.get("structured_output") is True
    assert kwargs.get("llm_type") == "analysis"
