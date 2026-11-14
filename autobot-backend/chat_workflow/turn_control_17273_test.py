# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat turn ends when its client does, and is bounded in time (#17273).

Every test drives the real ``ChatWorkflowManager._process_via_graph`` (or the
real LLM request method) around a fake graph. Before #17273 the graph ran as a
bare detached task: closing the consumer left it running, and the LLM request
carried no total timeout. Each assertion counts what the graph actually did
after the consumer was gone -- not the absence of an exception.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.eventually import eventually
from chat_workflow import graph as graph_module
from chat_workflow import turn_cancel_bus, turn_control
from chat_workflow.manager import ChatWorkflowManager
from tests.helpers._fake_pubsub_redis import FakeRedis


class _FakeGraph:
    """Emits one chunk, then 'calls the LLM' (a sleep) and counts what survives."""

    def __init__(self, llm_seconds: float = 30.0):
        self.llm_seconds = llm_seconds
        self.llm_started = asyncio.Event()
        self.llm_cancelled = False
        self.llm_finished = False
        self.tool_dispatches = 0

    async def ainvoke(self, _input, config):
        config["configurable"]["stream_callback"]({"type": "response", "content": "partial"})
        try:
            self.llm_started.set()
            await asyncio.sleep(self.llm_seconds)  # stands in for the streaming LLM request
            self.llm_finished = True
        except asyncio.CancelledError:
            self.llm_cancelled = True
            raise
        self.tool_dispatches += 1  # work that only happens if the run is NOT torn down
        return {}


@pytest.fixture(autouse=True)
def fake_bus_redis(monkeypatch):
    """The turn-cancel bus talks to Redis; these tests are about the turn, not the wire."""
    redis = FakeRedis()
    monkeypatch.setattr(turn_cancel_bus, "get_async_redis_client", AsyncMock(return_value=redis))
    return redis


@pytest.fixture
def drop_checkpoint(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(graph_module, "delete_thread_checkpoints", mock)
    return mock


def _manager(monkeypatch, fake: _FakeGraph) -> ChatWorkflowManager:
    mgr = ChatWorkflowManager()
    monkeypatch.setattr(graph_module, "get_compiled_graph", AsyncMock(return_value=fake))
    return mgr


async def _first_chunk_then_close(mgr: ChatWorkflowManager, session_id: str, fake: _FakeGraph):
    stream = mgr._process_via_graph(session_id, "hi", {})
    first = await stream.__anext__()
    await asyncio.wait_for(fake.llm_started.wait(), 2)
    await stream.aclose()  # what Starlette does when the SSE client disconnects
    return first


@pytest.mark.asyncio
async def test_disconnect_cancels_the_task_and_the_llm_call(monkeypatch, drop_checkpoint):
    fake = _FakeGraph()
    mgr = _manager(monkeypatch, fake)

    first = await _first_chunk_then_close(mgr, "s-disc", fake)

    assert first.content == "partial"
    assert fake.llm_cancelled is True, "the in-flight LLM call must receive the cancellation"
    assert fake.llm_finished is False
    assert fake.tool_dispatches == 0
    assert not turn_control.has_active_turn("s-disc"), "the registry must not leak a finished turn"
    drop_checkpoint.assert_awaited_once_with("s-disc")


@pytest.mark.asyncio
async def test_no_work_happens_after_the_consumer_is_gone(monkeypatch, drop_checkpoint):
    fake = _FakeGraph(llm_seconds=0.2)
    mgr = _manager(monkeypatch, fake)

    await _first_chunk_then_close(mgr, "s-after", fake)
    # fixed sleep on purpose (#16255): proving NO dispatch happens needs the LLM call's whole duration to pass
    await asyncio.sleep(0.4)

    assert fake.tool_dispatches == 0, "a detached task would have run on to dispatch tools"


@pytest.mark.asyncio
async def test_the_turn_timeout_fires(monkeypatch, drop_checkpoint):
    fake = _FakeGraph()
    mgr = _manager(monkeypatch, fake)
    monkeypatch.setattr(turn_control, "CHAT_TURN_TIMEOUT_SECONDS", 0.05)

    messages = [m async for m in mgr._process_via_graph("s-time", "hi", {})]

    assert [m.type for m in messages] == ["response", "error"]
    assert messages[-1].content == turn_control.TIMEOUT_MESSAGE
    assert fake.llm_cancelled is True, "the timeout must cancel the LLM call, not abandon it"
    drop_checkpoint.assert_awaited_once_with("s-time")


@pytest.mark.asyncio
async def test_a_normal_turn_completes_untouched(monkeypatch, drop_checkpoint):
    fake = _FakeGraph(llm_seconds=0)
    mgr = _manager(monkeypatch, fake)

    messages = [m async for m in mgr._process_via_graph("s-ok", "hi", {})]

    assert [m.content for m in messages] == ["partial"]
    assert fake.tool_dispatches == 1 and fake.llm_cancelled is False
    drop_checkpoint.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_turn_stops_the_running_turn_and_says_so(monkeypatch, drop_checkpoint):
    fake = _FakeGraph()
    mgr = _manager(monkeypatch, fake)
    stream = mgr._process_via_graph("s-cancel", "hi", {})
    await stream.__anext__()
    await asyncio.wait_for(fake.llm_started.wait(), 2)

    cancelled = await turn_control.cancel_turn("s-cancel")
    rest = [m async for m in stream]

    assert cancelled == 1
    assert fake.llm_cancelled is True
    assert [m.type for m in rest] == ["cancelled"], "the stream must end with a cancelled event, not an error"
    assert rest[0].metadata == {"reason": turn_control.REASON_CLIENT_CANCEL}
    assert not turn_control.has_active_turn("s-cancel")


@pytest.mark.asyncio
async def test_cancel_turn_with_no_turn_is_a_noop():
    assert await turn_control.cancel_turn("nobody-home") == 0
    assert await turn_control.cancel_turn("nobody-home") == 0


@pytest.mark.asyncio
async def test_cancel_only_touches_its_own_session(monkeypatch, drop_checkpoint):
    fake = _FakeGraph(llm_seconds=0.3)
    mgr = _manager(monkeypatch, fake)
    stream = mgr._process_via_graph("s-mine", "hi", {})
    await stream.__anext__()

    assert await turn_control.cancel_turn("s-someone-else") == 0
    rest = [m async for m in stream]

    assert rest == [] and fake.tool_dispatches == 1


@pytest.mark.asyncio
async def test_the_llm_request_carries_a_bounded_total_timeout(monkeypatch):
    mgr = ChatWorkflowManager()
    monkeypatch.setattr(mgr, "_get_llm_request_payload", MagicMock(return_value={}))
    seen = {}
    response = MagicMock(status=500)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    class _Http:
        async def post(self, _url, json, timeout):  # noqa: A002
            seen["timeout"] = timeout
            return response

        async def decrement_active(self):
            return None

    monkeypatch.setattr(turn_control, "CHAT_LLM_CALL_TIMEOUT_SECONDS", 123.0)
    monkeypatch.setattr("chat_workflow.manager.CHAT_LLM_CALL_TIMEOUT_SECONDS", 123.0)
    async for _ in mgr._process_single_llm_iteration(_Http(), "http://llm", "m", "p", "t", False, [], 1):
        pass

    assert seen["timeout"].total == 123.0, "total=None would let a stalled model hold the turn forever"


@pytest.mark.asyncio
async def test_a_real_asgi_disconnect_reaches_the_llm_call(monkeypatch, drop_checkpoint):
    """End to end through Starlette's StreamingResponse, not a hand-called aclose().

    The client reads one chunk and then sends ``http.disconnect`` -- the case the
    issue describes. Before #17273 the graph task survived it.
    """
    from api.chat import _create_streaming_response, _stream_chat_workflow_messages

    fake = _FakeGraph()
    mgr = _manager(monkeypatch, fake)
    monkeypatch.setattr(mgr, "_apply_session_role", AsyncMock(return_value={}))
    response = _create_streaming_response(_stream_chat_workflow_messages(mgr, "s-asgi", "hi", {}, "req-1"))
    sent = []
    first_chunk_out = asyncio.Event()

    async def receive():
        await first_chunk_out.wait()
        await asyncio.wait_for(fake.llm_started.wait(), 2)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and len(sent) >= 3:
            first_chunk_out.set()

    await response({"type": "http", "asgi": {"version": "3.0"}}, receive, send)
    await eventually(lambda: fake.llm_cancelled is True)

    assert fake.tool_dispatches == 0
    assert not turn_control.has_active_turn("s-asgi")


class _LegacyStream:
    """Stands in for the pre-LangGraph path: one chunk, then a long wait that counts cancellation."""

    def __init__(self, seconds: float = 30.0):
        self.seconds = seconds
        self.started = asyncio.Event()
        self.cancelled = False
        self.finished = False

    async def __call__(self, _session_id, _message, _context):
        from async_chat_workflow import WorkflowMessage

        yield WorkflowMessage(type="response", content="legacy-chunk")
        try:
            self.started.set()
            await asyncio.sleep(self.seconds)
            self.finished = True
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def _fallback_manager(monkeypatch, legacy: _LegacyStream) -> ChatWorkflowManager:
    """A manager whose graph cannot be built, so process_message_stream takes the fallback."""
    mgr = ChatWorkflowManager()
    monkeypatch.setattr(mgr, "_apply_session_role", AsyncMock(return_value={}))
    monkeypatch.setattr(graph_module, "get_compiled_graph", AsyncMock(side_effect=RuntimeError("no graph")))
    monkeypatch.setattr(mgr, "_process_message_stream_legacy", legacy)
    return mgr


@pytest.mark.asyncio
async def test_the_fallback_path_is_cancelled_on_disconnect(monkeypatch, drop_checkpoint):
    legacy = _LegacyStream()
    mgr = _fallback_manager(monkeypatch, legacy)
    stream = mgr.process_message_stream("s-fb-disc", "hi")

    first = await stream.__anext__()
    await asyncio.wait_for(legacy.started.wait(), 2)
    assert turn_control.has_active_turn("s-fb-disc"), "the fallback turn must be registered"
    await stream.aclose()

    assert first.content == "legacy-chunk"
    assert legacy.cancelled is True and legacy.finished is False
    assert not turn_control.has_active_turn("s-fb-disc")


@pytest.mark.asyncio
async def test_the_fallback_path_can_be_cancelled_by_the_client(monkeypatch, drop_checkpoint):
    legacy = _LegacyStream()
    mgr = _fallback_manager(monkeypatch, legacy)
    stream = mgr.process_message_stream("s-fb-cancel", "hi")
    await stream.__anext__()
    await asyncio.wait_for(legacy.started.wait(), 2)

    assert await turn_control.cancel_turn("s-fb-cancel") == 1
    rest = [m async for m in stream]

    assert legacy.cancelled is True
    assert [m.type for m in rest] == ["cancelled"]


@pytest.mark.asyncio
async def test_the_fallback_path_has_the_turn_timeout(monkeypatch, drop_checkpoint):
    legacy = _LegacyStream()
    mgr = _fallback_manager(monkeypatch, legacy)
    monkeypatch.setattr(turn_control, "CHAT_TURN_TIMEOUT_SECONDS", 0.05)

    messages = [m async for m in mgr.process_message_stream("s-fb-time", "hi")]

    assert [m.type for m in messages] == ["response", "error"]
    assert messages[-1].content == turn_control.TIMEOUT_MESSAGE
    assert legacy.cancelled is True


@pytest.mark.parametrize("bad", ["0", "-5", "nan", "inf", "-inf", "abc"])
def test_a_bad_timeout_value_falls_back_to_the_default(monkeypatch, bad):
    """0 or a negative would time out every turn; nan and inf would never time one out."""
    import importlib

    monkeypatch.setenv("AUTOBOT_CHAT_TURN_TIMEOUT_SECONDS", bad)
    monkeypatch.setenv("AUTOBOT_CHAT_LLM_CALL_TIMEOUT_SECONDS", bad)
    try:
        importlib.reload(turn_control)
        assert turn_control.CHAT_TURN_TIMEOUT_SECONDS == 1800.0
        assert turn_control.CHAT_LLM_CALL_TIMEOUT_SECONDS == 600.0
    finally:
        monkeypatch.delenv("AUTOBOT_CHAT_TURN_TIMEOUT_SECONDS")
        monkeypatch.delenv("AUTOBOT_CHAT_LLM_CALL_TIMEOUT_SECONDS")
        importlib.reload(turn_control)


def test_a_good_timeout_value_is_honoured(monkeypatch):
    import importlib

    monkeypatch.setenv("AUTOBOT_CHAT_TURN_TIMEOUT_SECONDS", "42.5")
    try:
        importlib.reload(turn_control)
        assert turn_control.CHAT_TURN_TIMEOUT_SECONDS == 42.5
    finally:
        monkeypatch.delenv("AUTOBOT_CHAT_TURN_TIMEOUT_SECONDS")
        importlib.reload(turn_control)
