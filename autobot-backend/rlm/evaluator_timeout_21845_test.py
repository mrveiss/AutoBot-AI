# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An evaluator failure of any kind is not a pass; unexecuted TOOL_CALL markup is refined (#21845)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from rlm.evaluator import ResponseQualityEvaluator
from rlm.types import ReflectionVerdict, RLMConfig

BAD_CALL = """<TOOL_CALL name="browser_evaluate" params='{'expression': 'a('b')'  oops}'>x</TOOL_CALL>"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError(),
        httpx.ReadTimeout("slow"),
        ConnectionError(),
        httpx.ConnectError("refused"),
        RuntimeError("provider returned 500"),
        ValueError("unreadable reply"),
    ],
)
async def test_any_evaluator_failure_carries_no_passing_score(exc):
    evaluator = ResponseQualityEvaluator(config=RLMConfig())
    with patch.object(evaluator, "_call_llm", new=AsyncMock(side_effect=exc)):
        result = await evaluator.evaluate(query="q", response="some answer", iteration=1)
    assert result.verdict == ReflectionVerdict.INDETERMINATE
    assert result.quality_score == 0.0 < RLMConfig().quality_threshold


@pytest.mark.asyncio
async def test_unparsed_tool_call_is_refined_without_calling_the_llm():
    evaluator = ResponseQualityEvaluator(config=RLMConfig())
    llm = AsyncMock(side_effect=TimeoutError())
    with patch.object(evaluator, "_call_llm", new=llm):
        result = await evaluator.evaluate(query="q", response=BAD_CALL, iteration=1)
    assert result.verdict == ReflectionVerdict.REFINE
    assert result.refinement_hint
    llm.assert_not_called()
