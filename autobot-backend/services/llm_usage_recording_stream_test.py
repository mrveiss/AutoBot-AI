# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every streamed LLM call records its spend (#16924).

Three live call sites reached a provider and recorded nothing: ``/api/chat/compare``,
the transcript-analysis WebSocket and the transcriber's ``ai/ask``. They now stream
through ``services.llm_usage_recording.recorded_stream`` -- directly (compare) or via
``LLMService.stream()`` (both transcript surfaces), which records too.

These tests drive the recorder and each site end to end against a tracker double,
and fail if the recording is removed. ``llm_spend_call_sites_test.py`` is the guard
that catches the next unrecorded site on arrival.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from llm_shared.models import LLMRequest
from services.llm_cost_tracker import LLMCostTracker
from services.llm_usage_recording import ESTIMATED_TOKENS, STREAM_ABANDONED, recorded_stream, spend_attribution
from testkit.real_llm_service import load_real_llm_service

_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "autobot-backend"


class _StreamingProvider:
    """Yields fixed chunks; optionally fails after them, the way a dropped connection does."""

    provider_name = "fake"
    settings = {"default_model": "fake-default"}

    def __init__(self, chunks=("Hello ", "world"), fail_after: Exception | None = None) -> None:
        self.chunks = chunks
        self.fail_after = fail_after
        self.requests: list[LLMRequest] = []

    async def stream_completion(self, request: LLMRequest):
        self.requests.append(request)
        for chunk in self.chunks:
            yield chunk
        if self.fail_after is not None:
            raise self.fail_after


class _Registry:
    def __init__(self, provider) -> None:
        self.provider = provider

    async def get_provider_for_request(self, provider_name=None, conversation_id=None, request=None, org_id=None):
        return self.provider


@pytest.fixture
def tracker():
    """A tracker double that accepts only methods the real class defines."""
    double = create_autospec(LLMCostTracker, instance=True)
    with patch("services.llm_usage_recording.get_cost_tracker", return_value=double):
        yield double


@pytest.fixture
def service(monkeypatch):
    """A real LLMService over a one-provider registry, so the stream() path is the production one."""
    llm_service_mod = load_real_llm_service()
    provider = _StreamingProvider()
    svc = llm_service_mod.LLMService(registry=_Registry(provider))
    monkeypatch.setattr(llm_service_mod, "get_fallback_chain_manager", lambda: MagicMock())
    return SimpleNamespace(svc=svc, provider=provider)


def _recorded(tracker) -> dict:
    tracker.track_usage.assert_awaited_once()
    return tracker.track_usage.await_args.kwargs


async def _drain(stream) -> list[str]:
    return [chunk async for chunk in stream]


# ---------------------------------------------------------------------------
# recorded_stream -- the one recorder every streamed site goes through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_finished_stream_records_estimated_tokens_once_against_the_named_caller(tracker) -> None:
    request = LLMRequest(
        messages=[{"role": "user", "content": "count these words"}],
        metadata=spend_attribution(user_id="alice", endpoint="/x", recording_id=7),
    )
    chunks = await _drain(recorded_stream(_StreamingProvider(), request, session_id="conv-1"))

    assert chunks == ["Hello ", "world"]
    kwargs = _recorded(tracker)
    assert (kwargs["provider"], kwargs["model"]) == ("fake", "fake-default")
    assert (kwargs["user_id"], kwargs["endpoint"], kwargs["session_id"]) == ("alice", "/x", "conv-1")
    assert kwargs["input_tokens"] > 0 and kwargs["output_tokens"] > 0
    assert kwargs["metadata"] == {**ESTIMATED_TOKENS, "recording_id": 7}
    assert kwargs["success"] is True


@pytest.mark.asyncio
async def test_a_stream_failing_midway_records_the_spent_tokens_as_unsuccessful_and_reraises(tracker) -> None:
    provider = _StreamingProvider(chunks=("partial",), fail_after=RuntimeError("connection reset"))
    with pytest.raises(RuntimeError, match="connection reset"):
        await _drain(recorded_stream(provider, LLMRequest(messages=[{"role": "user", "content": "hi"}])))

    kwargs = _recorded(tracker)
    assert kwargs["success"] is False and kwargs["error_message"] == "connection reset"


@pytest.mark.asyncio
async def test_a_stream_that_yielded_nothing_records_nothing(tracker) -> None:
    provider = _StreamingProvider(chunks=(), fail_after=RuntimeError("429 rate limit exceeded"))
    with pytest.raises(RuntimeError):
        await _drain(recorded_stream(provider, LLMRequest(messages=[{"role": "user", "content": "hi"}])))

    tracker.track_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_recording_failure_is_logged_loudly_and_the_stream_still_completes(tracker) -> None:
    tracker.track_usage.side_effect = ConnectionError("redis down")
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    with patch("services.llm_usage_recording.logger") as logger:
        chunks = await _drain(recorded_stream(_StreamingProvider(), request))

    assert chunks == ["Hello ", "world"]
    logger.exception.assert_called_once()
    logger.debug.assert_not_called()


@pytest.mark.asyncio
async def test_llm_service_stream_records_against_the_conversation(tracker, service) -> None:
    chunks = await _drain(service.svc.stream([{"role": "user", "content": "hi"}], conversation_id="conv-9"))

    assert chunks == ["Hello ", "world"]
    assert _recorded(tracker)["session_id"] == "conv-9"


# ---------------------------------------------------------------------------
# The three #16924 call sites, end to end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_compare_records_each_models_spend_against_the_caller(tracker) -> None:
    from api import chat_compare

    provider = _StreamingProvider()
    with patch("llm_shared.get_provider_registry", return_value=_Registry(provider)):
        stream = chat_compare._stream_single_model("fake/model-a", [{"role": "user", "content": "hi"}], "alice")
        events = await _drain(stream)

    assert events[-1] == chat_compare._sse({"model": "fake/model-a", "done": True})
    kwargs = _recorded(tracker)
    assert (kwargs["user_id"], kwargs["model"], kwargs["endpoint"]) == ("alice", "model-a", "/api/chat/compare")


@pytest.mark.asyncio
async def test_transcript_analysis_records_against_the_caller_and_recording(tracker, service) -> None:
    from api import transcripts
    from api.schemas_transcripts import AnalysisType, TranscriptAnalyzeRequest

    request = TranscriptAnalyzeRequest(analysis_type=AnalysisType.SUMMARIZE)
    with patch.object(transcripts, "get_llm_service", return_value=service.svc):
        tokens = await _drain(transcripts._stream_analysis("A: hi", request, user_id="alice", recording_id=456))

    assert tokens == ["Hello ", "world"]
    kwargs = _recorded(tracker)
    assert kwargs["user_id"] == "alice" and kwargs["metadata"]["recording_id"] == 456
    _assert_analysis_budget(service.provider.requests)


@pytest.mark.asyncio
async def test_transcriber_ask_records_against_the_caller_and_recording(tracker, service) -> None:
    from transcriber.models import AiAskRequest
    from transcriber.routes import ai

    db = SimpleNamespace(get_recording=AsyncMock(return_value={"id": 7, "user_id": "alice"}))
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="alice", is_admin=False)))
    with (
        patch.object(ai, "get_llm_service", return_value=service.svc),
        patch.object(ai, "build_segment_list", AsyncMock(return_value=[])),
    ):
        response = await ai.ai_ask(7, AiAskRequest(action="summarize"), request, db)
        body = "".join([chunk async for chunk in response.body_iterator])

    assert "Hello " in body and "error" not in body
    kwargs = _recorded(tracker)
    assert kwargs["user_id"] == "alice" and kwargs["metadata"]["recording_id"] == 7
    _assert_analysis_budget(service.provider.requests)


def _assert_analysis_budget(requests: list[LLMRequest]) -> None:
    """The analysis asks for ANALYSIS_MAX_TOKENS, never the general task default that cut answers off."""
    from transcriber.ai.prompts import ANALYSIS_MAX_TOKENS

    assert [r.max_tokens for r in requests] == [ANALYSIS_MAX_TOKENS]
    assert ANALYSIS_MAX_TOKENS >= 4096, "below the providers' own default the analyses had before #16924"


def test_each_endpoint_label_is_the_route_it_is_mounted_at() -> None:
    """The labels are the mounted route templates, so spend groups by the URL a client actually calls."""
    from api import transcriber, transcripts
    from autobot_shared.api_routing.router_routes import effective_routes
    from transcriber.routes import ai

    # app_factory.py mounts both with include_router(router, prefix=f"/api{prefix}") and prefix "".
    # effective_routes, not router.routes: fastapi>=0.139 defers included routers (#15093).
    transcriber_paths = {"/api" + mounted.path for mounted in effective_routes(transcriber.router)}
    transcripts_paths = {"/api" + mounted.path for mounted in effective_routes(transcripts.router)}
    assert ai._ASK_ENDPOINT in transcriber_paths
    assert transcripts._ANALYZE_ENDPOINT in transcripts_paths


# ---------------------------------------------------------------------------
# A consumer going away: abandoned, cancelled, cancelled again
# ---------------------------------------------------------------------------


class _HangingProvider:
    """Yields one chunk, then waits forever -- a model still generating when the client leaves."""

    provider_name = "fake"
    settings = {"default_model": "fake-default"}

    async def stream_completion(self, request: LLMRequest):
        yield "first"
        await asyncio.Event().wait()


def _hi() -> LLMRequest:
    return LLMRequest(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_a_stream_closed_midway_is_recorded_as_abandoned_not_successful(tracker) -> None:
    stream = recorded_stream(_StreamingProvider(), _hi())
    assert await anext(stream) == "Hello "
    await stream.aclose()

    kwargs = _recorded(tracker)
    assert kwargs["success"] is False and kwargs["error_message"] == STREAM_ABANDONED
    assert kwargs["output_tokens"] > 0


@pytest.mark.asyncio
async def test_a_cancelled_consumer_is_recorded_as_abandoned(tracker) -> None:
    started = asyncio.Event()

    async def consume() -> None:
        async for _ in recorded_stream(_HangingProvider(), _hi()):
            started.set()

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _recorded(tracker)["error_message"] == STREAM_ABANDONED


@pytest.mark.asyncio
async def test_a_second_cancel_during_recording_does_not_lose_the_record(tracker) -> None:
    started, store_reached, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    stored: list[dict] = []

    async def slow_store(**kwargs) -> None:
        store_reached.set()
        await release.wait()
        stored.append(kwargs)

    tracker.track_usage.side_effect = slow_store

    async def consume() -> None:
        async for _ in recorded_stream(_HangingProvider(), _hi()):
            started.set()

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    await store_reached.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    for _ in range(5):
        await asyncio.sleep(0)

    assert [record["error_message"] for record in stored] == [STREAM_ABANDONED], "the store was cut off"


# ---------------------------------------------------------------------------
# What gets counted, and who it is counted against
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_form_content_counts_its_text_parts_not_their_repr(tracker) -> None:
    text = "describe this picture please"
    multipart = [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": "data:" + "A" * 4000}}]
    plain = LLMRequest(messages=[{"role": "user", "content": text}])
    parts = LLMRequest(messages=[{"role": "user", "content": multipart}])
    await _drain(recorded_stream(_StreamingProvider(), plain))
    await _drain(recorded_stream(_StreamingProvider(), parts))

    first, second = (call.kwargs["input_tokens"] for call in tracker.track_usage.await_args_list)
    assert first == second


@pytest.mark.asyncio
async def test_an_attributed_endpoint_with_no_user_warns(tracker) -> None:
    attribution = spend_attribution(user_id=None, endpoint="/x")
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], metadata=attribution)
    with patch("services.llm_usage_recording.logger") as logger:
        await _drain(recorded_stream(_StreamingProvider(), request))

    logger.warning.assert_called_once()
    assert "/x" in logger.warning.call_args.args
    assert _recorded(tracker)["user_id"] is None


@pytest.mark.asyncio
async def test_a_failure_preparing_the_record_cannot_mask_the_streams_own_error(tracker) -> None:
    provider = _StreamingProvider(chunks=("partial",), fail_after=RuntimeError("connection reset"))
    with (
        patch("services.llm_usage_recording._prompt_text", side_effect=ValueError("unreadable message")),
        patch("services.llm_usage_recording.logger") as logger,
        pytest.raises(RuntimeError, match="connection reset"),
    ):
        await _drain(recorded_stream(provider, _hi()))

    logger.exception.assert_called_once()
    tracker.track_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_slow_store_bounds_the_streams_wait_and_the_record_still_lands(tracker) -> None:
    release, stored = asyncio.Event(), []

    async def slow_store(**kwargs) -> None:
        await release.wait()
        stored.append(kwargs)

    tracker.track_usage.side_effect = slow_store
    with (
        patch("services.llm_usage_recording.SPEND_RECORD_TIMEOUT_SECONDS", 0.05),
        patch("services.llm_usage_recording.logger") as logger,
    ):
        chunks = await _drain(recorded_stream(_StreamingProvider(), _hi()))

    assert chunks == ["Hello ", "world"] and not stored
    logger.warning.assert_called_once()
    release.set()
    for _ in range(5):
        await asyncio.sleep(0)
    assert len(stored) == 1, "the record was dropped when the wait timed out"
