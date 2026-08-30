# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ProviderDegradationStore (Issue #11519).

Coverage:
- mark → is_degraded returns True within TTL (Redis-backed via fakeredis).
- Two store instances sharing a FakeServer simulate two workers sharing state.
- TTL expiry restores the provider (time-travel via manual key deletion).
- No-Redis fallback (mocked _get_redis raises): in-process dict tracks marks.
- All-degraded chain in provider_registry still proceeds (no hard failure).
- mark_degraded in coordinator sets the Redis key after fallback exhaustion.

#15022 split the needs_reauth-cause coverage (non-expiry, explicit clear,
cause reporting, the Redis-down path, the alert-cooldown wiring, and the
base_provider._get_auth_token wiring) into
test_provider_degradation_reauth.py — this file plus that split module
together exceeded the repo's 600-line cap. This file kept the pre-#15022
baseline coverage above and the ModelFallbackCoordinator/ProviderRegistry
integration tests below. Shared store/global-injection fixtures live in
conftest.py (fixtures, not imports — llm_shared.tests has no __init__.py,
so a plain import fails collection; see conftest.py's docstring). Each
file keeps its own one-line guarded fakeredis import instead of sharing it.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:
    fakeredis_async = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Redis-backed tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_then_is_degraded_redis(_require_fakeredis, _make_store_with_fake_server):
    """mark_degraded → is_degraded returns True within TTL (Redis path)."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("openai", "gpt-4o")

    assert await store.is_degraded("openai", "gpt-4o") is True


@pytest.mark.asyncio
async def test_not_degraded_without_mark_redis(_require_fakeredis, _make_store_with_fake_server):
    """is_degraded returns False when no mark has been set."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    assert await store.is_degraded("anthropic", "claude-opus-4") is False


@pytest.mark.asyncio
async def test_provider_only_key_redis(_require_fakeredis, _make_store_with_fake_server):
    """Provider-only mark (no model) is correctly stored and retrieved."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("groq")

    assert await store.is_degraded("groq") is True
    # Model-scoped key must NOT match a provider-only mark.
    assert await store.is_degraded("groq", "llama3") is False


@pytest.mark.asyncio
async def test_cross_worker_mark_visible_to_second_store(_require_fakeredis, _make_store_with_fake_server):
    """Two stores sharing a FakeServer (simulating two workers) share state."""
    server = fakeredis_async.FakeServer()
    worker_a = _make_store_with_fake_server(server)
    worker_b = _make_store_with_fake_server(server)

    await worker_a.mark_degraded("openai", "gpt-4o")

    # Worker B must see worker A's mark without any direct call.
    assert await worker_b.is_degraded("openai", "gpt-4o") is True


@pytest.mark.asyncio
async def test_ttl_expiry_restores_provider(_require_fakeredis, _make_store_with_fake_server):
    """After TTL expiry (simulated by deleting the key), is_degraded returns False."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("openai", "gpt-4o")
    assert await store.is_degraded("openai", "gpt-4o") is True

    # Simulate TTL expiry by directly deleting the key from Redis.
    redis = await store._get_redis()
    await redis.delete("autobot:llm:deg:openai:gpt-4o")

    assert await store.is_degraded("openai", "gpt-4o") is False


@pytest.mark.asyncio
async def test_degraded_entries_returns_marked_keys(_require_fakeredis, _make_store_with_fake_server):
    """degraded_entries() lists all currently-marked keys."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("openai", "gpt-4o")
    await store.mark_degraded("anthropic")

    entries = await store.degraded_entries()
    keys = [e["key"] for e in entries]
    assert "autobot:llm:deg:openai:gpt-4o" in keys
    assert "autobot:llm:deg:anthropic" in keys


# ---------------------------------------------------------------------------
# In-process fallback (no Redis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_redis_fallback_mark_and_check():
    """When Redis is unavailable, in-process dict tracks marks correctly."""
    from llm_shared.provider_degradation import ProviderDegradationStore

    store = ProviderDegradationStore()

    async def _raise(*_args, **_kwargs):
        raise ConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    await store.mark_degraded("openai", "gpt-4o")
    assert await store.is_degraded("openai", "gpt-4o") is True


@pytest.mark.asyncio
async def test_no_redis_fallback_expiry():
    """In-process fallback respects expiry timestamps (time-travel via monkeypatch)."""
    from llm_shared.provider_degradation import DegradationCause, ProviderDegradationStore

    store = ProviderDegradationStore()

    async def _raise(*_args, **_kwargs):
        raise ConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    await store.mark_degraded("openai", "gpt-4o")
    assert await store.is_degraded("openai", "gpt-4o") is True

    # Force expiry by back-dating the timestamp. #15022: _local now stores
    # (cause, expires_at) — a bare float here would no longer unpack.
    store._local["autobot:llm:deg:openai:gpt-4o"] = (DegradationCause.TRANSIENT, time.monotonic() - 1.0)
    assert await store.is_degraded("openai", "gpt-4o") is False


@pytest.mark.asyncio
async def test_no_redis_degraded_entries_fallback():
    """degraded_entries() uses in-process dict when Redis is unavailable."""
    from llm_shared.provider_degradation import ProviderDegradationStore

    store = ProviderDegradationStore()

    async def _raise(*_args, **_kwargs):
        raise ConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    await store.mark_degraded("openai", "gpt-4o")
    entries = await store.degraded_entries()
    assert "autobot:llm:deg:openai:gpt-4o" in [e["key"] for e in entries]


# ---------------------------------------------------------------------------
# ModelFallbackCoordinator integration: mark on exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_marks_degraded_on_rate_limit(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """execute_with_fallback marks a provider degraded when rate-limited."""
    server = fakeredis_async.FakeServer()
    store_instance = _make_store_with_fake_server(server)

    from llm_shared.fallback_chain import FallbackChain, FallbackChainManager
    from llm_shared.model_fallback_coordinator import ModelFallbackCoordinator
    from llm_shared.models import LLMRequest, LLMResponse
    from llm_shared.optimization.rate_limiter import RateLimitError

    coordinator = ModelFallbackCoordinator()

    req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    req.model_name = "claude-opus-4"
    from llm_shared.models import ProviderType

    req.provider = ProviderType("anthropic")

    fallback_response = LLMResponse(content="ok", model="claude-sonnet-4", provider="anthropic")
    call_count = [0]

    async def _dispatch(r):
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            raise RateLimitError("quota")
        return fallback_response

    provider = MagicMock()
    provider.chat_completion = _dispatch
    provider.provider_name = "anthropic"
    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(return_value=provider)

    mgr = FallbackChainManager.__new__(FallbackChainManager)
    mgr._chains = {}
    chain = FallbackChain(
        primary_model="claude-opus-4",
        fallback_models=["claude-sonnet-4"],
        primary_provider="anthropic",
        fallback_providers=["anthropic"],
    )
    mgr._chains["claude-opus-4"] = chain

    with _inject_globals(
        ModelFallbackCoordinator.execute_with_fallback,
        get_fallback_chain_manager=lambda: mgr,
        get_degradation_store=lambda: store_instance,
    ):
        result = await coordinator.execute_with_fallback(req, registry)

    assert result.content == "ok"
    # The primary provider:model must now be marked degraded.
    assert await store_instance.is_degraded("anthropic", "claude-opus-4") is True


# ---------------------------------------------------------------------------
# ProviderRegistry: skip degraded, all-degraded fallthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_skips_degraded_provider(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
    """get_provider_for_request skips a degraded provider and picks the next."""
    server = fakeredis_async.FakeServer()
    store_a = _make_store_with_fake_server(server)

    # Mark openai degraded from another "worker".
    await store_a.mark_degraded("openai")

    from llm_shared.provider_registry import ProviderRegistry

    registry = ProviderRegistry()

    # Register two providers; openai is degraded.
    openai_prov = MagicMock()
    openai_prov.provider_name = "openai"
    openai_prov.is_available = AsyncMock(return_value=True)

    anthropic_prov = MagicMock()
    anthropic_prov.provider_name = "anthropic"
    anthropic_prov.is_available = AsyncMock(return_value=True)

    registry.register(openai_prov)
    registry.register(anthropic_prov)
    registry.set_fallback_chain(["openai", "anthropic"])

    store_b = _make_store_with_fake_server(server)
    with _inject_globals(
        ProviderRegistry.get_provider_for_request,
        get_degradation_store=lambda: store_b,
    ):
        chosen = await registry.get_provider_for_request()

    # Should skip openai (degraded) and return anthropic.
    assert chosen is anthropic_prov


@pytest.mark.asyncio
async def test_registry_all_degraded_proceeds(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
    """When all providers are degraded, the registry still returns one (no hard fail)."""
    server = fakeredis_async.FakeServer()
    store_a = _make_store_with_fake_server(server)

    await store_a.mark_degraded("openai")
    await store_a.mark_degraded("anthropic")

    from llm_shared.provider_registry import ProviderRegistry

    registry = ProviderRegistry()

    openai_prov = MagicMock()
    openai_prov.provider_name = "openai"
    openai_prov.is_available = AsyncMock(return_value=True)

    registry.register(openai_prov)
    registry.set_fallback_chain(["openai"])

    store_b = _make_store_with_fake_server(server)
    with _inject_globals(
        ProviderRegistry.get_provider_for_request,
        get_degradation_store=lambda: store_b,
    ):
        chosen = await registry.get_provider_for_request()

    # All-degraded → proceed anyway; openai is still returned.
    assert chosen is openai_prov


# ---------------------------------------------------------------------------
# Review follow-ups (#11519): exhaustion marking, provider resolution,
# coordinator→registry end-to-end key match.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_marks_final_provider_on_exhaustion(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """The provider failing on the LAST attempt is marked too (mark before break)."""
    server = fakeredis_async.FakeServer()
    store_instance = _make_store_with_fake_server(server)

    from llm_shared.fallback_chain import FallbackChain, FallbackChainManager
    from llm_shared.model_fallback_coordinator import ModelFallbackCoordinator
    from llm_shared.models import LLMRequest, ProviderType
    from llm_shared.optimization.rate_limiter import RateLimitError

    coordinator = ModelFallbackCoordinator()
    req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    req.model_name = "claude-opus-4"
    req.provider = ProviderType("anthropic")

    async def _always_rate_limited(r):
        raise RateLimitError("quota")

    provider = MagicMock()
    provider.chat_completion = _always_rate_limited
    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(return_value=provider)

    mgr = FallbackChainManager.__new__(FallbackChainManager)
    mgr._chains = {}
    mgr._chains["claude-opus-4"] = FallbackChain(
        primary_model="claude-opus-4",
        fallback_models=["claude-sonnet-4"],
        primary_provider="anthropic",
        fallback_providers=["anthropic"],
    )
    mgr._chains["claude-sonnet-4"] = FallbackChain(
        primary_model="claude-sonnet-4",
        fallback_models=["claude-haiku-4"],
        primary_provider="anthropic",
        fallback_providers=["anthropic"],
    )

    with _inject_globals(
        ModelFallbackCoordinator.execute_with_fallback,
        get_fallback_chain_manager=lambda: mgr,
        get_degradation_store=lambda: store_instance,
    ):
        result = await coordinator.execute_with_fallback(req, registry, max_attempts=1)

    assert result.error  # exhausted
    # BOTH the primary and the final (exhausted) fallback model are marked.
    assert await store_instance.is_degraded("anthropic", "claude-opus-4") is True
    assert await store_instance.is_degraded("anthropic", "claude-sonnet-4") is True


@pytest.mark.asyncio
async def test_coordinator_marks_registry_resolved_provider_when_request_has_none(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """A request without a provider still produces a matchable mark via selected_provider."""
    server = fakeredis_async.FakeServer()
    store_instance = _make_store_with_fake_server(server)

    from llm_shared.fallback_chain import FallbackChainManager
    from llm_shared.model_fallback_coordinator import ModelFallbackCoordinator
    from llm_shared.models import LLMRequest
    from llm_shared.optimization.rate_limiter import RateLimitError

    coordinator = ModelFallbackCoordinator()
    req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    req.model_name = "gpt-4o"
    assert req.provider is None

    async def _rate_limited(r):
        raise RateLimitError("quota")

    provider = MagicMock()
    provider.chat_completion = _rate_limited

    async def _resolve(provider_name=None, request=None):
        # Emulate the real registry stamping the resolved provider (#11519).
        if request is not None:
            request.metadata["selected_provider"] = "openai"
        return provider

    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(side_effect=_resolve)

    mgr = FallbackChainManager.__new__(FallbackChainManager)
    mgr._chains = {}  # no fallback registered → break after first failure

    with _inject_globals(
        ModelFallbackCoordinator.execute_with_fallback,
        get_fallback_chain_manager=lambda: mgr,
        get_degradation_store=lambda: store_instance,
    ):
        result = await coordinator.execute_with_fallback(req, registry)

    assert result.error
    # The mark uses the registry-resolved provider, so the registry's own
    # is_degraded("openai", "gpt-4o") check matches the key.
    assert await store_instance.is_degraded("openai", "gpt-4o") is True
    # No junk empty-provider key was written.
    entries = await store_instance.degraded_entries()
    assert all(":deg::" not in e["key"] for e in entries)


@pytest.mark.asyncio
async def test_registry_stamps_selected_provider_and_skips_model_scoped_mark(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """End-to-end: a model-scoped coordinator mark is honored by registry selection."""
    server = fakeredis_async.FakeServer()
    store_a = _make_store_with_fake_server(server)

    # Coordinator-style mark from another worker: provider:model scoped.
    await store_a.mark_degraded("openai", "gpt-4o")

    from llm_shared.models import LLMRequest
    from llm_shared.provider_registry import ProviderRegistry

    registry = ProviderRegistry()
    openai_prov = MagicMock()
    openai_prov.provider_name = "openai"
    openai_prov.is_available = AsyncMock(return_value=True)
    anthropic_prov = MagicMock()
    anthropic_prov.provider_name = "anthropic"
    anthropic_prov.is_available = AsyncMock(return_value=True)
    registry.register(openai_prov)
    registry.register(anthropic_prov)
    registry.set_fallback_chain(["openai", "anthropic"])

    req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    req.model_name = "gpt-4o"

    store_b = _make_store_with_fake_server(server)
    with _inject_globals(
        ProviderRegistry.get_provider_for_request,
        get_degradation_store=lambda: store_b,
    ):
        chosen = await registry.get_provider_for_request(request=req)

    # Model-scoped mark on openai:gpt-4o → anthropic chosen.
    assert chosen is anthropic_prov
    # Resolved provider stamped for the coordinator's mark path.
    assert req.metadata["selected_provider"] == "anthropic"
    assert req.metadata["degraded_skipped"] == ["openai"]
