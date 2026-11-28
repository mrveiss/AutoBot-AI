# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Selecting ThinkCategory.SELF_REFLECTION reaches the one quality seam (#16133)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent_loop.think_tool import _REFLECTION_SCHEMA, REFLECTION_JUDGE_FAILED, ThinkTool
from agent_loop.types import ThinkCategory


def _patch_seam(seam):
    """Patch `judge_validated` in the globals `ThinkTool` actually resolves it from.

    `autobot-backend/conftest.py` and `tests/agent_loop/conftest.py` real-load `agent_loop.think_tool`
    more than once, so `sys.modules["agent_loop.think_tool"]` (what `patch("agent_loop.think_tool.X")`
    resolves) can be a different module object from the one this file's `ThinkTool` came from.
    """
    return patch.dict(ThinkTool._reflect.__globals__, {"judge_validated": seam})


@pytest.mark.asyncio
async def test_self_reflection_routes_through_judge_validated():
    seam = AsyncMock(return_value={"score": 0.4, "critique": "misses the second question"})
    with _patch_seam(seam):
        result = await ThinkTool(llm_client=object()).think(ThinkCategory.SELF_REFLECTION, "q/a", task_id="t1")

    seam.assert_awaited_once()
    assert seam.await_args.kwargs["label"] == "agent_loop.think.self_reflection"
    assert result.category is ThinkCategory.SELF_REFLECTION
    assert result.confidence == pytest.approx(0.4)
    assert result.reasoning == "misses the second question"
    assert result.task_id == "t1"


@pytest.mark.asyncio
async def test_self_reflection_completer_uses_the_llm_client():
    client = AsyncMock()
    client.generate.return_value = '{"score": 0.9, "critique": ""}'
    result = await ThinkTool(llm_client=client).think(ThinkCategory.SELF_REFLECTION, "q/a")

    client.generate.assert_awaited()
    assert result.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_other_categories_do_not_use_the_seam():
    client = AsyncMock()
    client.generate.return_value = "## Conclusion\nok"
    seam = AsyncMock()
    with _patch_seam(seam):
        await ThinkTool(llm_client=client).think(ThinkCategory.GENERAL, "ctx")
    seam.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_reflection_prompt_asks_for_json_and_carries_the_schema():
    client = AsyncMock()
    client.generate.return_value = '{"score": 0.9}'
    await ThinkTool(llm_client=client).think(ThinkCategory.SELF_REFLECTION, "q/a")

    sent = client.generate.await_args.args[0]
    assert "JSON" in sent
    assert "score" in sent
    assert json.dumps(_REFLECTION_SCHEMA, ensure_ascii=False) in sent
    assert "## Reasoning" not in sent


@pytest.mark.asyncio
async def test_a_judge_failure_is_distinguishable_from_a_low_score():
    client = AsyncMock()
    client.generate.return_value = "prose, never JSON"
    failed = await ThinkTool(llm_client=client).think(ThinkCategory.SELF_REFLECTION, "q/a")
    client.generate.return_value = '{"score": 0.3}'
    judged = await ThinkTool(llm_client=client).think(ThinkCategory.SELF_REFLECTION, "q/a")

    assert failed.confidence == 0.0
    assert REFLECTION_JUDGE_FAILED in failed.risks_identified
    assert judged.confidence == pytest.approx(0.3)
    assert judged.risks_identified == []


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
async def test_a_non_finite_judge_score_is_a_judge_failure(raw):
    client = AsyncMock()
    client.generate.return_value = '{"score": %s}' % raw
    result = await ThinkTool(llm_client=client).think(ThinkCategory.SELF_REFLECTION, "q/a")

    assert result.confidence == 0.0
    assert REFLECTION_JUDGE_FAILED in result.risks_identified
