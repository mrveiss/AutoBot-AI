# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider-outage failover through the one coordinator (#19753).

A 503 (not only a 429) fails over; the not-acted guard, once-per-model, the skip window / quota hold,
and the local-to-external rule are decided inside ``ModelFallbackCoordinator``, not at its callers.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_shared.fallback_chain import FallbackChain, FallbackChainManager
from llm_shared.model_fallback_coordinator import ModelFallbackCoordinator
from llm_shared.models import LLMRequest, LLMResponse, ProviderType
from llm_shared.provider_error_category import ProviderErrorCategory, ProviderFailure

MODULE = "llm_shared.model_fallback_coordinator"
UNAVAILABLE = ProviderFailure(ProviderErrorCategory.PROVIDER_UNAVAILABLE, "HTTP 503")


class _Store:
    """In-memory stand-in for the degradation store: records marks, answers ``is_degraded``."""

    def __init__(self, degraded=()):
        self.marks: list[tuple] = []
        self.degraded = set(degraded)

    async def mark_degraded(self, provider, model=None, **kwargs):
        self.marks.append((provider, model, kwargs))

    async def is_degraded(self, provider, model=None):
        return (provider, model) in self.degraded


def _request(model="claude-opus-4", provider="anthropic", **kwargs) -> LLMRequest:
    req = LLMRequest(messages=[{"role": "user", "content": "hi"}], **kwargs)
    req.model_name = model
    req.provider = ProviderType(provider)
    return req


def _registry(*effects):
    """Registry whose provider answers ``effects`` in order (an Exception is raised); records the models asked."""
    asked: list[str] = []

    async def dispatch(request):
        asked.append(request.model_name)
        effect = effects[min(len(asked) - 1, len(effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect

    provider = MagicMock(provider_name="anthropic", chat_completion=dispatch)
    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(return_value=provider)
    registry.asked = asked
    return registry


def _ok(model="claude-sonnet-4"):
    return LLMResponse(content="backup answer", model=model, provider="anthropic")


def _error(text):
    return LLMResponse(content="", error=text, model="claude-opus-4", provider="anthropic")


def _chains(primary, fallbacks, providers, *, operator=False, primary_provider="anthropic"):
    mgr = FallbackChainManager.__new__(FallbackChainManager)
    chain = FallbackChain(primary, fallbacks, primary_provider, providers, operator_configured=operator)
    mgr._chains = {primary.lower(): chain}
    return mgr


@contextmanager
def _env(mgr, store=None):
    store = store or _Store()
    with (
        patch(f"{MODULE}.get_fallback_chain_manager", return_value=mgr),
        patch(f"{MODULE}.get_degradation_store", return_value=store),
        patch(f"{MODULE}.emit_fallback_event", new=AsyncMock()) as emitted,
        patch(f"{MODULE}.exhausted_window", new=AsyncMock(return_value=None)),
    ):
        yield store, emitted


# --------------------------------------------------------------------------------------------------
# AC1: a 503 from the primary, then a completed answer from the backup
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_503_from_the_primary_is_followed_by_a_completed_answer_from_the_backup():
    registry = _registry(_error("LLM service error: HTTP 503"), _ok())
    mgr = _chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])
    with _env(mgr) as (store, emitted):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)

    assert result.content == "backup answer"
    assert registry.asked == ["claude-opus-4", "claude-sonnet-4"]
    assert result.provider_metadata["fallback_used"] is True
    assert result.provider_metadata["fallback_reason"] == "provider_unavailable"
    assert store.marks == [("anthropic", "claude-opus-4", {})]  # skipped for the plain window: no ttl override
    assert emitted.await_args.kwargs["reason"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_an_error_nobody_can_classify_is_surfaced_not_failed_over():
    registry = _registry(_error("the model produced garbage"), _ok())
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)
    assert result.error == "the model produced garbage"
    assert registry.asked == ["claude-opus-4"]


@pytest.mark.asyncio
async def test_a_permanent_error_is_not_failed_over():
    registry = _registry(_error("HTTP 400 invalid request"), _ok())
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)
    assert result.error == "HTTP 400 invalid request"
    assert registry.asked == ["claude-opus-4"]


@pytest.mark.asyncio
async def test_failover_off_returns_the_error_as_before():
    registry = _registry(_error("HTTP 503"), _ok())
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(fallback_enabled=False), registry)
    assert result.error == "HTTP 503"
    assert registry.asked == ["claude-opus-4"]


# --------------------------------------------------------------------------------------------------
# AC2: the not-acted guard
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_turn_that_already_acted_does_not_fail_over():
    registry = _registry(_ok())
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])) as (store, _):
        result = await ModelFallbackCoordinator().fail_over(_request(), registry, UNAVAILABLE, acted=True)
    assert result is None
    assert registry.asked == []
    assert store.marks == []


@pytest.mark.asyncio
async def test_a_turn_that_has_not_acted_continues_on_the_next_model():
    registry = _registry(_ok())
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])) as (store, emitted):
        result = await ModelFallbackCoordinator().fail_over(_request(), registry, UNAVAILABLE, acted=False)
    assert result.content == "backup answer"
    assert registry.asked == ["claude-sonnet-4"]  # the caller already tried the primary itself
    assert store.marks == [("anthropic", "claude-opus-4", {})]
    assert emitted.await_count == 1


@pytest.mark.asyncio
async def test_a_failure_that_no_model_can_fix_is_not_failed_over():
    registry = _registry(_ok())
    permanent = ProviderFailure(ProviderErrorCategory.PERMANENT, "HTTP 400")
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])):
        assert await ModelFallbackCoordinator().fail_over(_request(), registry, permanent, acted=False) is None
    assert registry.asked == []


# --------------------------------------------------------------------------------------------------
# AC3: once per failed model; skip window; quota hold
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_model_is_tried_at_most_once_per_request():
    registry = _registry(_error("HTTP 503"))
    mgr = _chains("m-a", ["m-b", "m-a", "m-b"], ["anthropic"] * 3, primary_provider="anthropic")
    with _env(mgr):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request("m-a"), registry)
    assert registry.asked == ["m-a", "m-b"]
    assert result.error == "HTTP 503"
    assert result.provider_metadata["fallback_exhausted"] is True


@pytest.mark.asyncio
async def test_a_model_inside_its_skip_window_is_not_offered():
    registry = _registry(_ok("m-c"))
    mgr = _chains("m-a", ["m-b", "m-c"], ["anthropic", "anthropic"])
    with _env(mgr, _Store(degraded={("anthropic", "m-b")})):
        result = await ModelFallbackCoordinator().fail_over(_request("m-a"), registry, UNAVAILABLE, acted=False)
    assert result.content == "backup answer"
    assert registry.asked == ["m-c"]


@pytest.mark.asyncio
async def test_a_held_primary_is_not_marked_again():
    """The skip window must not stretch each time a message arrives while the model is already out."""
    registry = _registry(_ok())
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])) as (store, _):
        await ModelFallbackCoordinator().fail_over(_request(), registry, UNAVAILABLE, acted=False, held=True)
    assert store.marks == []


@pytest.mark.asyncio
async def test_a_plan_limit_holds_the_model_until_the_provider_reset():
    registry = _registry(_ok())
    quota = ProviderFailure(ProviderErrorCategory.BILLING, "insufficient_quota", retry_after=7200)
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])) as (store, _):
        await ModelFallbackCoordinator().fail_over(_request(), registry, quota, acted=False)
    assert store.marks == [("anthropic", "claude-opus-4", {"ttl_seconds": 7200})]


# --------------------------------------------------------------------------------------------------
# AC4: authentication is announced; local never leaves the machine on a default chain
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_authentication_failover_is_announced_with_its_reason():
    registry = _registry(_error("HTTP 401 Unauthorized"), _ok("gpt-4o"))
    mgr = _chains("claude-opus-4", ["gpt-4o"], ["openai"])
    with _env(mgr) as (_, emitted):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)
    assert result.content == "backup answer"
    assert result.provider_metadata["fallback_reason"] == "authentication"
    assert emitted.await_args.kwargs["reason"] == "authentication"
    assert emitted.await_args.kwargs["fallback_provider"] == "openai"


@pytest.mark.asyncio
async def test_local_never_fails_over_to_an_external_provider_on_a_default_chain():
    registry = _registry(_ok("gpt-4o"))
    mgr = _chains("llama3", ["gpt-4o"], ["openai"], primary_provider="ollama", operator=False)
    with _env(mgr) as (store, _):
        result = await ModelFallbackCoordinator().fail_over(
            _request("llama3", "ollama"), registry, UNAVAILABLE, acted=False
        )
    assert result is None
    assert registry.asked == []  # no prompt left the machine


@pytest.mark.asyncio
async def test_local_fails_over_to_an_external_provider_when_the_operator_wrote_the_chain():
    registry = _registry(_ok("gpt-4o"))
    mgr = _chains("llama3", ["gpt-4o"], ["openai"], primary_provider="ollama", operator=True)
    with _env(mgr):
        result = await ModelFallbackCoordinator().fail_over(
            _request("llama3", "ollama"), registry, UNAVAILABLE, acted=False
        )
    assert result.content == "backup answer"
    assert registry.asked == ["gpt-4o"]


@pytest.mark.asyncio
async def test_local_fails_over_to_another_local_model_on_a_default_chain():
    registry = _registry(_ok("llama3-small"))
    mgr = _chains("llama3", ["llama3-small"], ["ollama"], primary_provider="ollama", operator=False)
    with _env(mgr):
        result = await ModelFallbackCoordinator().fail_over(
            _request("llama3", "ollama"), registry, UNAVAILABLE, acted=False
        )
    assert result.content == "backup answer"


@pytest.mark.asyncio
async def test_the_operator_chain_loader_marks_a_chain_as_configured(monkeypatch):
    monkeypatch.setenv("AUTOBOT_FALLBACK_CHAIN_LLAMA3", "openai:gpt-4o")
    hop = FallbackChainManager().get_next_hop("llama3", "ollama")
    assert (hop.model, hop.provider, hop.operator_configured) == ("gpt-4o", "openai", True)


def test_the_default_chains_are_never_operator_configured(monkeypatch):
    for key in [k for k in __import__("os").environ if k.startswith("AUTOBOT_FALLBACK_CHAIN_")]:
        monkeypatch.delenv(key)
    manager = FallbackChainManager()
    assert not any(chain.operator_configured for chain in manager._chains.values())
