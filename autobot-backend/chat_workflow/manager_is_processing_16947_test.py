# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ChatWorkflowManager.is_processing() is true for a stream's span (#16947).

Presence has no per-role concurrency signal for AI-stack agents -- this is
the busy source `sync_ai_stack_presence` reads. Drives the real
`process_message_stream` generator (patching only its two heavy internals,
`_apply_session_role` and `_process_via_graph`), not `is_processing()` and
the counter in isolation, so a future refactor that stops incrementing
`_active_streams` around the real yield loop fails here.
"""

from unittest.mock import AsyncMock

import pytest

from chat_workflow.manager import ChatWorkflowManager


async def _one_message_graph(*_args, **_kwargs):
    yield {"content": "hi"}


@pytest.mark.asyncio
async def test_is_processing_is_true_only_for_the_streams_span(monkeypatch):
    mgr = ChatWorkflowManager()
    monkeypatch.setattr(mgr, "_apply_session_role", AsyncMock(return_value={}))
    monkeypatch.setattr(mgr, "_process_via_graph", _one_message_graph)

    assert mgr.is_processing() is False

    seen_busy_mid_stream = False
    async for _ in mgr.process_message_stream("sess-1", "hello"):
        seen_busy_mid_stream = mgr.is_processing()

    assert seen_busy_mid_stream is True
    assert mgr.is_processing() is False


@pytest.mark.asyncio
async def test_is_processing_reflects_overlapping_streams(monkeypatch):
    """Two concurrent sessions -- is_processing must not drop early when one finishes."""
    mgr = ChatWorkflowManager()
    monkeypatch.setattr(mgr, "_apply_session_role", AsyncMock(return_value={}))
    monkeypatch.setattr(mgr, "_process_via_graph", _one_message_graph)

    gen_a = mgr.process_message_stream("sess-a", "hello")
    await gen_a.__anext__()
    assert mgr.is_processing() is True

    async for _ in mgr.process_message_stream("sess-b", "hello"):
        assert mgr.is_processing() is True

    # sess-a's generator is still open (one item consumed, not exhausted) --
    # is_processing must still see it.
    assert mgr.is_processing() is True
    await gen_a.aclose()
    assert mgr.is_processing() is False


@pytest.mark.asyncio
async def test_is_processing_clears_even_when_the_stream_raises(monkeypatch):
    async def _raising_graph(*_args, **_kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover -- makes this an async generator

    async def _raising_legacy(*_args, **_kwargs):
        raise RuntimeError("boom-legacy")
        yield  # pragma: no cover

    mgr = ChatWorkflowManager()
    monkeypatch.setattr(mgr, "_apply_session_role", AsyncMock(return_value={}))
    monkeypatch.setattr(mgr, "_process_via_graph", _raising_graph)
    monkeypatch.setattr(mgr, "_process_message_stream_legacy", _raising_legacy)

    with pytest.raises(RuntimeError, match="boom-legacy"):
        async for _ in mgr.process_message_stream("sess-1", "hello"):
            pass

    assert mgr.is_processing() is False
