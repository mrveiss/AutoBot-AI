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

from judges import BaseLLMJudge, _extract_json_object


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
async def test_judge_call_forces_structured_output():
    judge = BaseLLMJudge.__new__(BaseLLMJudge)  # bypass heavy __init__
    judge.judge_type = "test"
    judge.llm_interface = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content="{}")))

    await judge._get_llm_evaluation("evaluate this")

    _, kwargs = judge.llm_interface.chat.call_args
    assert kwargs.get("structured_output") is True
    assert kwargs.get("llm_type") == "analysis"
