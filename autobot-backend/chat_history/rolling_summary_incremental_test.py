# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rolling summary cost, progress and lock behaviour (#20852): the incremental guard, the tail-only read,
chunk-by-chunk progress and the per-gateway-call lock renewal. Fixtures are shared with rolling_summary_test."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from chat_history import rolling_summary as rs
from chat_history.context_overflow import ConversationSummarizer, SummarizationFailed
from chat_history.rolling_summary_test import SID, StubSummarizer
from chat_history.rolling_summary_test import env as _shared_env
from chat_history.summarization_prompt import SUMMARIZER_INPUT_MAX_CHARS

env = _shared_env  # the shared fixture, registered in this module


def test_the_chain_guard_extends_without_rehashing_and_is_split_independent():
    turns = [{"user": f"q{i}", "assistant": f"a{i}"} for i in range(6)]
    assert rs.chain_guard(rs.prefix_guard(turns[:4]), turns[4:]) == rs.prefix_guard(turns)
    assert rs.chain_guard(rs.chain_guard("", turns[:1]), turns[1:]) == rs.prefix_guard(turns)


@pytest.mark.asyncio
async def test_a_refresh_with_no_new_message_reads_the_session_once_and_projects_nothing(env):
    await env.run(8)
    reads, hashed = env.reads, []
    with patch.object(rs, "turn_digest", lambda t: hashed.append(t) or "x"):
        env.projected.clear()
        assert await rs.refresh_summary(SID, "m", env.stub, now=1000.0) is True
    assert env.reads == reads + 1 and env.projected == [] and hashed == []  # no projection, no hashing
    assert len(env.stub.calls) == 8 - rs.RECENT_TURNS_KEPT  # the per-turn folds only: this refresh added none


@pytest.mark.asyncio
async def test_one_new_turn_projects_only_the_tail_and_hashes_only_the_new_turns(env):
    await env.run(20)
    env.durable.append({"user": "question 21", "assistant": "answer 21"})
    env.projected.clear()
    hashed = []
    real = rs.turn_digest
    with patch.object(rs, "turn_digest", lambda t: hashed.append(t) or real(t)):
        await rs.refresh_summary(SID, "m", env.stub, now=1000.0)
    # the boundary exchange + the new unfolded one + the two recent ones = 4 exchanges = 8 messages, not 42
    assert env.projected == [8]
    assert (
        len(hashed) == 3
    )  # boundary check + the one new turn (guard, new boundary); the 19-turn prefix is not re-hashed
    entry = rs._entry_from(env.redis.data[f"{rs._SUMMARY_KEY_PREFIX}{SID}"])
    assert entry.guard == rs.prefix_guard(env.durable[: 21 - rs.RECENT_TURNS_KEPT])


@pytest.mark.asyncio
async def test_a_failure_at_chunk_k_keeps_the_chunks_already_folded(env):
    for i in range(1, 9):
        env.durable.append({"user": f"question {i}", "assistant": f"answer {i}"})
    real = env.stub.summarize_messages
    seen = []

    async def fail_on_third(messages, model, **kw):
        seen.append(1)
        if len(seen) == 3:
            raise SummarizationFailed("down")
        return await real(messages, model, **kw)

    env.stub = SimpleNamespace(summarize_messages=fail_on_third)
    with patch.object(rs, "ROLLING_SUMMARY_CHUNK_TURNS", 2):
        await rs.refresh_summary(SID, "m", env.stub, now=1000.0)
    entry = rs._entry_from(env.redis.data[f"{rs._SUMMARY_KEY_PREFIX}{SID}"])
    assert entry.folded == 4 and entry.failed_at == 1000.0  # two chunks kept, the failure recorded
    assert entry.guard == rs.prefix_guard(env.durable[:4])
    env.stub = StubSummarizer()
    with patch.object(rs, "ROLLING_SUMMARY_CHUNK_TURNS", 2):
        await rs.refresh_summary(SID, "m", env.stub, now=1000.0 + rs.ROLLING_SUMMARY_FAILURE_BACKOFF_SECONDS)
    assert env.stub.calls[0]["prior"] != "" and env.stub.calls[0]["turns"] == 6  # continued, not restarted


@pytest.mark.asyncio
async def test_the_lock_is_renewed_before_each_gateway_call_of_one_chunk(env):
    """One chunk of long turns needs 3 gateway calls of 50 s each (> the lock's lifetime); the store still lands."""
    now = [0.0]
    env.redis.clock = lambda: now[0]
    big = "x" * (SUMMARIZER_INPUT_MAX_CHARS // 2 + 1000)  # one message per call
    for i in range(5):
        env.durable.append({"user": f"q{i} {big}", "assistant": f"a{i}"})
    calls = []

    async def slow_chat(**_kw):
        calls.append(1)
        now[0] += 50.0
        return SimpleNamespace(content="summary", usage=None)

    summarizer = ConversationSummarizer(gateway=SimpleNamespace(chat=slow_chat))
    assert 3 * 50.0 > rs._LOCK_TTL_SECONDS  # without per-call renewal the lock would be gone by the store
    await rs.refresh_summary(SID, "m", summarizer, now=1000.0)
    assert len(calls) >= 3
    entry = rs._entry_from(env.redis.data[f"{rs._SUMMARY_KEY_PREFIX}{SID}"])
    assert entry is not None and entry.folded == 5 - rs.RECENT_TURNS_KEPT and entry.failed_at == 0.0


def test_a_single_message_over_the_input_cap_is_split_across_calls_never_cut():
    from chat_history.summarization_prompt import chunk_lines

    line = "".join(chr(65 + i % 26) for i in range(2500))
    chunks = chunk_lines(["short", line, "tail"], 1000)
    assert all(len(c) <= 1000 for c in chunks) and len(chunks) >= 3
    assert "".join(c.replace("\n", "") for c in chunks) == "short" + line + "tail"
