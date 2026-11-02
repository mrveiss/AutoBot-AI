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
from llm_shared.run_credentials import llm_principal_scope

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


def _registry(*effects, provider_name="anthropic"):
    """Registry whose provider answers ``effects`` in order (an Exception is raised); records the models asked.

    Like the real registry, it records the provider it resolved on ``request.metadata["selected_provider"]``.
    """
    asked: list[str] = []

    async def dispatch(request):
        request.metadata["selected_provider"] = request.provider.value if request.provider else provider_name
        asked.append(request.model_name)
        effect = effects[min(len(asked) - 1, len(effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect

    provider = MagicMock(provider_name=provider_name, chat_completion=dispatch)
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


# --------------------------------------------------------------------------------------------------
# Whose failure it is: the degradation mark is shared by every user and worker
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_callers_expired_credential_surfaces_as_before_on_a_compat_route():
    """A principal is in scope on the compat routes: a 401 may be that user's own token, not the provider's."""
    registry = _registry(_error("HTTP 401 Unauthorized"), _ok("gpt-4o"))
    with _env(_chains("claude-opus-4", ["gpt-4o"], ["openai"])) as (store, emitted), llm_principal_scope("u1", "o1"):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)
    assert result.error == "HTTP 401 Unauthorized"
    assert registry.asked == ["claude-opus-4"]  # no hop to another provider
    assert store.marks == []  # and no shared mark that would change another user's route
    assert emitted.await_count == 0 or emitted.await_args.kwargs.get("exhausted") is True


@pytest.mark.asyncio
async def test_a_system_credential_failure_with_no_principal_fails_over_and_is_marked_for_the_window():
    registry = _registry(_error("HTTP 401 Unauthorized"), _ok("gpt-4o"))
    with _env(_chains("claude-opus-4", ["gpt-4o"], ["openai"])) as (store, _):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)
    assert result.content == "backup answer"
    assert store.marks == [("anthropic", "claude-opus-4", {})]


@pytest.mark.asyncio
@pytest.mark.parametrize("category", [ProviderErrorCategory.PROVIDER_UNAVAILABLE, ProviderErrorCategory.TIMEOUT])
async def test_one_local_request_that_fails_does_not_degrade_the_local_model_for_everyone(category):
    """A local server answers 500 / times out for the one request it cannot serve; it still serves the rest."""
    registry = _registry(_ok("llama3-small"), provider_name="ollama")
    mgr = _chains("llama3", ["llama3-small"], ["ollama"], primary_provider="ollama")
    failure = ProviderFailure(category, "HTTP 500")
    with _env(mgr) as (store, _):
        result = await ModelFallbackCoordinator().fail_over(
            _request("llama3", "ollama"), registry, failure, acted=False
        )
        assert result.content == "backup answer"  # this request is still answered by the backup
        assert store.marks == []  # but nobody else's route changes
        assert await store.is_degraded("ollama", "llama3") is False


@pytest.mark.asyncio
async def test_a_local_server_that_is_unreachable_is_marked_because_it_is_down_for_everyone():
    registry = _registry(_ok("llama3-small"), provider_name="ollama")
    mgr = _chains("llama3", ["llama3-small"], ["ollama"], primary_provider="ollama")
    network = ProviderFailure(ProviderErrorCategory.NETWORK, "connection refused")
    with _env(mgr) as (store, _):
        await ModelFallbackCoordinator().fail_over(_request("llama3", "ollama"), registry, network, acted=False)
    assert store.marks == [("ollama", "llama3", {})]


@pytest.mark.asyncio
async def test_a_hosted_providers_outage_is_marked_for_everyone():
    registry = _registry(_ok())
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])) as (store, _):
        await ModelFallbackCoordinator().fail_over(_request(), registry, UNAVAILABLE, acted=False)
    assert store.marks == [("anthropic", "claude-opus-4", {})]


# --------------------------------------------------------------------------------------------------
# Locality: unknown origin, provider-less hop; and what the metadata, event and log say about the hop
# --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unresolved_origin_cannot_hop_to_an_external_provider_on_a_default_chain():
    registry = _registry(_ok("gpt-4o"))
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    request.model_name = "m-a"  # no provider on the request, none selected by a registry
    with _env(_chains("m-a", ["gpt-4o"], ["openai"], primary_provider=None)):
        assert await ModelFallbackCoordinator().fail_over(request, registry, UNAVAILABLE, acted=False) is None
    assert registry.asked == []


@pytest.mark.asyncio
async def test_a_hop_with_no_provider_is_external_for_a_local_origin_unless_the_operator_wrote_it():
    for operator, expected in ((False, None), (True, "backup answer")):
        registry = _registry(_ok("m-b"), provider_name="ollama")
        mgr = _chains("m-a", ["m-b"], [None], primary_provider="ollama", operator=operator)
        with _env(mgr):
            result = await ModelFallbackCoordinator().fail_over(
                _request("m-a", "ollama"), registry, UNAVAILABLE, acted=False
            )
        assert (result.content if result else None) == expected


@pytest.mark.asyncio
async def test_the_selected_provider_the_registry_records_is_what_locality_is_judged_against():
    """On the compat path the request has no provider; the registry's ``selected_provider`` is the origin."""
    registry = _registry(_error("HTTP 503"), _ok("gpt-4o"), provider_name="ollama")
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    request.model_name = "llama3"  # no provider on the request
    with _env(_chains("llama3", ["gpt-4o"], ["openai"], primary_provider=None)):
        result = await ModelFallbackCoordinator().execute_with_fallback(request, registry)
    assert result.error == "HTTP 503"  # the primary resolved to a local provider: no hop to openai
    assert registry.asked == ["llama3"]


@pytest.mark.asyncio
async def test_the_hop_names_its_destination_provider_and_chain_author_in_metadata_event_and_log():
    registry = _registry(_error("HTTP 503"), _ok("gpt-4o"))
    mgr = _chains("claude-opus-4", ["gpt-4o"], ["openai"], operator=True)
    with _env(mgr) as (_, emitted), patch(f"{MODULE}.logger") as log:
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)
    meta = result.provider_metadata
    assert (meta["fallback_provider"], meta["operator_configured"]) == ("openai", True)
    assert emitted.await_args.kwargs["fallback_provider"] == "openai"
    assert emitted.await_args.kwargs["operator_configured"] is True
    hop_lines = [c.args[0] % c.args[1:] for c in log.warning.call_args_list if c.args[0].startswith("failover:")]
    assert any("provider='openai'" in m and "operator_configured=True" in m for m in hop_lines)


@pytest.mark.asyncio
async def test_a_response_that_did_not_fail_over_names_no_destination():
    registry = _registry(_ok("claude-opus-4"))
    with _env(_chains("claude-opus-4", ["claude-sonnet-4"], ["anthropic"])):
        result = await ModelFallbackCoordinator().execute_with_fallback(_request(), registry)
    assert result.provider_metadata["fallback_provider"] is None
    assert result.provider_metadata["operator_configured"] is None
