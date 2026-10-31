# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat path's failover seam (#19753): where text is emitted and tools run decides whether it may fire.

Drives the real ``_collect_llm_iteration_response`` -> ``_process_single_llm_iteration`` ->
``_stream_llm_response`` chain against a fake provider connection. Only the HTTP connection, the
provider registry and the degradation store are doubles; the coordinator is the real one.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from async_chat_workflow import WorkflowMessage
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.models import LLMIterationContext
from llm_shared.fallback_chain import FallbackChain, FallbackChainManager
from llm_shared.models import LLMResponse

COORDINATOR = "llm_shared.model_fallback_coordinator"
SEAM = "chat_workflow.llm_failover"


class _Store:
    def __init__(self, degraded=()):
        self.marks: list[tuple] = []
        self.degraded = set(degraded)

    async def mark_degraded(self, provider, model=None, **kwargs):
        self.marks.append((provider, model, kwargs))

    async def is_degraded(self, provider, model=None):
        return (provider, model) in self.degraded


class _Body:
    """The streamed response body: ``lines`` then, optionally, an exception mid-stream."""

    def __init__(self, lines, then_raise=None):
        self._lines, self._then_raise = list(lines), then_raise

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._lines:
            return self._lines.pop(0)
        if self._then_raise is not None:
            raise self._then_raise
        raise StopAsyncIteration


class _Reply:
    def __init__(self, status=200, body=None):
        self.status = status
        self.content = body or _Body([])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Http:
    """``post`` returns ``reply`` or raises ``error``; counts calls and ``decrement_active``."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error
        self.posts: list[dict] = []
        self.decrements = 0

    async def post(self, url, json=None, **kwargs):  # noqa: A002
        self.posts.append(json)
        if self.error is not None:
            raise self.error
        return self.reply

    async def decrement_active(self):
        self.decrements += 1


def _chunk(text, done=False):
    return json.dumps({"response": text, "done": done}).encode() + b"\n"


def _registry(answer="backup answer", model="backup-model"):
    asked: list[str] = []

    async def dispatch(request):
        asked.append(request.model_name)
        return LLMResponse(content=answer, model=model, provider="ollama")

    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(
        return_value=MagicMock(provider_name="ollama", chat_completion=dispatch)
    )
    registry.asked = asked
    return registry


def _chains(provider="ollama", *, operator=False):
    mgr = FallbackChainManager.__new__(FallbackChainManager)
    chain = FallbackChain("primary-model", ["backup-model"], "ollama", [provider], operator_configured=operator)
    mgr._chains = {"primary-model": chain}
    return mgr


def _ctx(**kwargs):
    base = dict(
        ollama_endpoint="http://provider/api/generate",
        selected_model="primary-model",
        session_id="s1",
        terminal_session_id="t1",
        used_knowledge=False,
        rag_citations=[],
        workflow_messages=[],
        system_prompt="be brief",
        initial_prompt="hello",
    )
    base.update(kwargs)
    return LLMIterationContext(**base)


@contextmanager
def _world(registry, *, store=None, mgr=None):
    store = store or _Store()
    with (
        patch(f"{SEAM}.get_provider_registry", return_value=registry),
        patch(f"{SEAM}.get_degradation_store", return_value=store),
        patch(f"{COORDINATOR}.get_degradation_store", return_value=store),
        patch(f"{COORDINATOR}.get_fallback_chain_manager", return_value=mgr or _chains()),
        patch(f"{COORDINATOR}.emit_fallback_event", new=AsyncMock()) as emitted,
        patch(f"{COORDINATOR}.exhausted_window", new=AsyncMock(return_value=None)),
    ):
        yield SimpleNamespace(store=store, emitted=emitted)


async def _run(http, ctx, iteration=1, *, hand_picked=False):
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    session = SimpleNamespace(metadata={"model_override": "primary-model"} if hand_picked else {})
    manager.get_or_create_session = AsyncMock(return_value=session)
    return [item async for item in manager._collect_llm_iteration_response(http, "hello", iteration, ctx)]


def _texts(items):
    return [i.content for i in items if isinstance(i, WorkflowMessage)]


# --------------------------------------------------------------------------------------------------
# A 503 from the primary, then a completed answer from the backup
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_503_from_the_primary_is_followed_by_a_completed_answer_from_the_backup():
    http, registry = _Http(_Reply(503)), _registry()
    with _world(registry) as world:
        items = await _run(http, _ctx())

    assert items[-1] == ("backup answer", [])
    assert _texts(items) == ["backup answer"]
    assert items[0].metadata["failover"]["from_model"] == "primary-model"
    assert registry.asked == ["backup-model"]
    assert http.decrements == 1  # the primary connection was released
    assert world.store.marks == [("ollama", "primary-model", {})]
    assert world.emitted.await_args.kwargs["reason"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_the_backup_gets_the_same_prompt_the_primary_got():
    registry, seen = _registry(), []
    provider = registry.get_provider_for_request.return_value
    inner = provider.chat_completion

    async def spy(request):
        seen.append(request.messages)
        return await inner(request)

    provider.chat_completion = spy
    with _world(registry):
        await _run(_Http(_Reply(503)), _ctx())
    assert seen == [[{"role": "system", "content": "be brief"}, {"role": "user", "content": "hello"}]]


@pytest.mark.asyncio
async def test_a_connection_failure_before_any_output_fails_over():
    http, registry = _Http(error=aiohttp.ClientConnectionError("refused")), _registry()
    with _world(registry):
        items = await _run(http, _ctx())
    assert items[-1] == ("backup answer", [])


@pytest.mark.asyncio
async def test_a_timeout_before_any_output_fails_over():
    http, registry = _Http(error=asyncio.TimeoutError()), _registry()
    with _world(registry) as world:
        items = await _run(http, _ctx())
    assert items[-1] == ("backup answer", [])
    assert world.emitted.await_args.kwargs["reason"] == "timeout"


@pytest.mark.asyncio
async def test_a_healthy_primary_never_touches_the_backup():
    http = _Http(_Reply(200, _Body([_chunk("hi "), _chunk("there", done=True)])))
    registry = _registry()
    with _world(registry):
        items = await _run(http, _ctx())
    assert items[-1][0] == "hi there"
    assert registry.asked == []


# --------------------------------------------------------------------------------------------------
# The not-acted guard: text emitted or a tool run means the error is surfaced
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_turn_that_already_ran_a_tool_does_not_fail_over():
    http, registry = _Http(_Reply(503)), _registry()
    ctx = _ctx(execution_history=[{"tool": "run_shell", "status": "success"}])
    with _world(registry) as world:
        items = await _run(http, ctx, iteration=2)

    assert _texts(items) == ["LLM service error: 503"]
    assert items[-1] == (None, None)
    assert registry.asked == []
    assert world.store.marks == []


@pytest.mark.asyncio
async def test_a_tool_history_alone_blocks_failover_even_on_the_first_iteration():
    http, registry = _Http(_Reply(503)), _registry()
    with _world(registry):
        items = await _run(http, _ctx(execution_history=[{"tool": "x"}]), iteration=1)
    assert _texts(items) == ["LLM service error: 503"]
    assert registry.asked == []


@pytest.mark.asyncio
async def test_a_later_iteration_does_not_fail_over():
    http, registry = _Http(_Reply(503)), _registry()
    with _world(registry):
        items = await _run(http, _ctx(), iteration=2)
    assert _texts(items) == ["LLM service error: 503"]
    assert registry.asked == []


@pytest.mark.asyncio
async def test_a_message_already_shown_this_turn_blocks_failover():
    http, registry = _Http(_Reply(503)), _registry()
    shown = WorkflowMessage(type="thought", content="thinking", metadata={})
    with _world(registry):
        items = await _run(http, _ctx(workflow_messages=[shown]))
    assert _texts(items) == ["LLM service error: 503"]
    assert registry.asked == []


@pytest.mark.asyncio
async def test_a_failure_after_text_was_streamed_is_surfaced_not_replayed():
    body = _Body([_chunk("partial ")], then_raise=aiohttp.ClientPayloadError("cut off"))
    http, registry = _Http(_Reply(200, body)), _registry()
    got = []
    with _world(registry), pytest.raises(aiohttp.ClientPayloadError):
        manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
        manager.get_or_create_session = AsyncMock(return_value=SimpleNamespace(metadata={}))
        async for item in manager._collect_llm_iteration_response(http, "hello", 1, _ctx()):
            got.append(item)
    assert any(isinstance(i, WorkflowMessage) and "partial" in i.content for i in got)  # the text was shown
    assert registry.asked == []  # and no second answer was fetched on top of it


@pytest.mark.asyncio
async def test_an_error_nobody_can_fix_by_switching_model_is_surfaced():
    http, registry = _Http(_Reply(400)), _registry()
    with _world(registry):
        items = await _run(http, _ctx())
    assert _texts(items) == ["LLM service error: 400"]
    assert registry.asked == []


@pytest.mark.asyncio
async def test_a_failover_that_itself_fails_surfaces_the_original_error():
    http, registry = _Http(_Reply(503)), _registry()
    registry.get_provider_for_request = AsyncMock(side_effect=RuntimeError("registry down"))
    with _world(registry):
        items = await _run(http, _ctx())
    assert _texts(items) == ["LLM service error: 503"]


# --------------------------------------------------------------------------------------------------
# Skip window, return to primary, hand-picked model
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_primary_inside_its_skip_window_is_not_called_at_all():
    http, registry = _Http(_Reply(200, _Body([_chunk("x", done=True)]))), _registry()
    with _world(registry, store=_Store(degraded={("ollama", "primary-model")})) as world:
        items = await _run(http, _ctx())
    assert http.posts == []
    assert items[-1] == ("backup answer", [])
    assert world.store.marks == []  # already held: not re-marked, so the window does not stretch


@pytest.mark.asyncio
async def test_the_primary_is_used_again_once_its_hold_ends():
    http, registry = _Http(_Reply(200, _Body([_chunk("primary again", done=True)]))), _registry()
    with _world(registry, store=_Store()):  # nothing degraded: the mark expired
        items = await _run(http, _ctx())
    assert items[-1][0] == "primary again"
    assert len(http.posts) == 1
    assert registry.asked == []


@pytest.mark.asyncio
async def test_a_hand_picked_model_is_still_tried_even_inside_its_skip_window():
    http, registry = _Http(_Reply(200, _Body([_chunk("mine", done=True)]))), _registry()
    with _world(registry, store=_Store(degraded={("ollama", "primary-model")})):
        items = await _run(http, _ctx(), hand_picked=True)
    assert items[-1][0] == "mine"
    assert registry.asked == []


@pytest.mark.asyncio
async def test_a_primary_held_out_does_not_skip_once_the_turn_has_acted():
    http = _Http(_Reply(200, _Body([_chunk("still primary", done=True)])))
    registry = _registry()
    with _world(registry, store=_Store(degraded={("ollama", "primary-model")})):
        items = await _run(http, _ctx(execution_history=[{"tool": "x"}]), iteration=2)
    assert items[-1][0] == "still primary"
    assert registry.asked == []


# --------------------------------------------------------------------------------------------------
# Data locality: a local model's prompt does not reach an external provider unless the operator said so
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_local_primary_never_fails_over_to_an_external_provider_on_a_default_chain():
    http, registry = _Http(_Reply(503)), _registry()
    with _world(registry, mgr=_chains(provider="openai", operator=False)):
        items = await _run(http, _ctx())
    assert _texts(items) == ["LLM service error: 503"]
    assert registry.asked == []  # nothing was sent anywhere


@pytest.mark.asyncio
async def test_a_local_primary_fails_over_to_an_external_provider_on_an_operator_chain():
    http, registry = _Http(_Reply(503)), _registry()
    with _world(registry, mgr=_chains(provider="openai", operator=True)):
        items = await _run(http, _ctx())
    assert items[-1] == ("backup answer", [])
