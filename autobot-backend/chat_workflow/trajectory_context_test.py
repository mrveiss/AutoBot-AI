# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat-loop trajectory learning — search-before / store-after (#11261)."""

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow import trajectory_context as tc

# --- _format_trajectory_block (pure) --------------------------------------


def test_format_block_renders_reference_framing():
    block = tc._format_trajectory_block([{"task_text": "Deploy X", "outcome": "success", "reward": 0.95}])
    assert "reference only" in block
    assert "Deploy X" in block
    assert "reward=0.95" in block


def test_format_block_empty_when_no_usable_entries():
    assert tc._format_trajectory_block([]) == ""
    assert tc._format_trajectory_block([{"task_text": "  "}]) == ""


# --- retrieve_trajectory_context ------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_disabled():
    with patch.object(tc, "TRAJECTORY_CONTEXT_ENABLED", False):
        assert await tc.retrieve_trajectory_context("hi", user_id="u1") == ""


@pytest.mark.asyncio
async def test_retrieve_returns_empty_on_blank_message():
    with patch.object(tc, "TRAJECTORY_CONTEXT_ENABLED", True):
        assert await tc.retrieve_trajectory_context("   ", user_id="u1") == ""


@pytest.mark.asyncio
async def test_retrieve_scopes_by_user_and_formats_hits():
    store = AsyncMock()
    store.find_similar_trajectories = AsyncMock(
        return_value=[{"task_text": "Restart svc", "outcome": "success", "reward": 0.9}]
    )
    with (
        patch.object(tc, "TRAJECTORY_CONTEXT_ENABLED", True),
        patch("memory.trajectory_store.get_trajectory_store", AsyncMock(return_value=store)),
    ):
        out = await tc.retrieve_trajectory_context("Restart the service", user_id="u1", tenant_id="t1")
    assert "Restart svc" in out
    _, kwargs = store.find_similar_trajectories.call_args
    assert kwargs["user_id"] == "u1"
    assert kwargs["tenant_id"] == "t1"
    assert kwargs["min_reward"] == tc._MIN_REWARD


@pytest.mark.asyncio
async def test_retrieve_returns_empty_on_timeout():
    async def _slow(*_a, **_k):
        import asyncio

        await asyncio.sleep(1.0)
        return [{"task_text": "x", "outcome": "success", "reward": 0.9}]

    store = AsyncMock()
    store.find_similar_trajectories = _slow
    with patch.object(tc, "TRAJECTORY_CONTEXT_ENABLED", True), patch.object(
        tc, "_RETRIEVE_TIMEOUT_S", 0.01
    ), patch("memory.trajectory_store.get_trajectory_store", AsyncMock(return_value=store)):
        assert await tc.retrieve_trajectory_context("q", user_id="u1") == ""


@pytest.mark.asyncio
async def test_retrieve_is_non_fatal_on_store_error():
    with (
        patch.object(tc, "TRAJECTORY_CONTEXT_ENABLED", True),
        patch("memory.trajectory_store.get_trajectory_store", AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        assert await tc.retrieve_trajectory_context("anything", user_id="u1") == ""


# --- capture_chat_trajectory ----------------------------------------------


@pytest.mark.asyncio
async def test_capture_noop_when_self_improvement_disabled():
    store = AsyncMock()
    with (
        patch("autobot_shared.ssot_config.SELF_IMPROVEMENT_ENABLED", False),
        patch("memory.trajectory_store.get_trajectory_store", AsyncMock(return_value=store)),
    ):
        await tc.capture_chat_trajectory("q", "a", user_id="u1")
    store.capture.assert_not_called()


@pytest.mark.asyncio
async def test_capture_scores_and_stores_when_enabled():
    store = AsyncMock()
    judge = AsyncMock()
    judge.evaluate_task_outcome = AsyncMock(return_value=type("J", (), {"overall_score": 0.9})())
    with (
        patch("autobot_shared.ssot_config.SELF_IMPROVEMENT_ENABLED", True),
        patch("memory.trajectory_store.get_trajectory_store", AsyncMock(return_value=store)),
        patch("judges.task_outcome_judge.TaskOutcomeJudge", return_value=judge),
    ):
        await tc.capture_chat_trajectory("deploy X", "done", user_id="u1", tenant_id="t1")
    store.capture.assert_awaited_once()
    _, kwargs = store.capture.call_args
    assert kwargs["outcome"] == "success"
    assert kwargs["reward"] == 0.9
    assert kwargs["user_id"] == "u1"
    assert kwargs["tenant_id"] == "t1"


@pytest.mark.asyncio
async def test_capture_maps_low_score_to_failure():
    store = AsyncMock()
    judge = AsyncMock()
    judge.evaluate_task_outcome = AsyncMock(return_value=type("J", (), {"overall_score": 0.1})())
    with (
        patch("autobot_shared.ssot_config.SELF_IMPROVEMENT_ENABLED", True),
        patch("memory.trajectory_store.get_trajectory_store", AsyncMock(return_value=store)),
        patch("judges.task_outcome_judge.TaskOutcomeJudge", return_value=judge),
    ):
        await tc.capture_chat_trajectory("q", "a", user_id="u1")
    _, kwargs = store.capture.call_args
    assert kwargs["outcome"] == "failure"


@pytest.mark.asyncio
async def test_capture_non_fatal_on_blank_response():
    store = AsyncMock()
    with (
        patch("autobot_shared.ssot_config.SELF_IMPROVEMENT_ENABLED", True),
        patch("memory.trajectory_store.get_trajectory_store", AsyncMock(return_value=store)),
    ):
        await tc.capture_chat_trajectory("q", "   ", user_id="u1")
    store.capture.assert_not_called()
