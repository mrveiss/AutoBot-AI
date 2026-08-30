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
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import fakeredis.aioredis as fakeredis_async

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_fakeredis():
    """Skip the test when fakeredis is not installed."""
    if not _FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed — skipping Redis-backed tests")


def _make_store_with_fake_server(server):
    """Return a ProviderDegradationStore whose Redis calls hit *server*."""
    from llm_shared.provider_degradation import ProviderDegradationStore

    store = ProviderDegradationStore()

    async def _fake_redis(*_args, **_kwargs):
        return fakeredis_async.FakeRedis(server=server, decode_responses=True)

    store._get_redis = _fake_redis  # type: ignore[method-assign]
    return store


@contextmanager
def _inject_globals(func, **replacements):
    """Swap names in *func*'s own module globals for the duration of the block.

    ``unittest.mock.patch("llm_shared.X.name")`` resolves the target through
    ``sys.modules``, which the conftest stub machinery can leave pointing at a
    MagicMock module while the real class lives in a separately loaded module
    object — silently patching the wrong namespace.  Injecting through
    ``func.__globals__`` always hits the dict the executing code reads.
    """
    g = func.__globals__
    saved = {k: g[k] for k in replacements}
    g.update(replacements)
    try:
        yield
    finally:
        g.update(saved)


# ---------------------------------------------------------------------------
# Redis-backed tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_then_is_degraded_redis():
    """mark_degraded → is_degraded returns True within TTL (Redis path)."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("openai", "gpt-4o")

    assert await store.is_degraded("openai", "gpt-4o") is True


@pytest.mark.asyncio
async def test_not_degraded_without_mark_redis():
    """is_degraded returns False when no mark has been set."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    assert await store.is_degraded("anthropic", "claude-opus-4") is False


@pytest.mark.asyncio
async def test_provider_only_key_redis():
    """Provider-only mark (no model) is correctly stored and retrieved."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("groq")

    assert await store.is_degraded("groq") is True
    # Model-scoped key must NOT match a provider-only mark.
    assert await store.is_degraded("groq", "llama3") is False


@pytest.mark.asyncio
async def test_cross_worker_mark_visible_to_second_store():
    """Two stores sharing a FakeServer (simulating two workers) share state."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    worker_a = _make_store_with_fake_server(server)
    worker_b = _make_store_with_fake_server(server)

    await worker_a.mark_degraded("openai", "gpt-4o")

    # Worker B must see worker A's mark without any direct call.
    assert await worker_b.is_degraded("openai", "gpt-4o") is True


@pytest.mark.asyncio
async def test_ttl_expiry_restores_provider():
    """After TTL expiry (simulated by deleting the key), is_degraded returns False."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("openai", "gpt-4o")
    assert await store.is_degraded("openai", "gpt-4o") is True

    # Simulate TTL expiry by directly deleting the key from Redis.
    redis = await store._get_redis()
    await redis.delete("autobot:llm:deg:openai:gpt-4o")

    assert await store.is_degraded("openai", "gpt-4o") is False


@pytest.mark.asyncio
async def test_degraded_entries_returns_marked_keys():
    """degraded_entries() lists all currently-marked keys."""
    _require_fakeredis()
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
# #15022: needs_reauth cause — non-expiry, explicit clear, cause reporting,
# and the alert wired through the existing AlertCooldownManager (#1948).
# ---------------------------------------------------------------------------


class _NoopCooldown:
    """Alert-cooldown double for tests that mark needs_reauth incidentally.

    Keeps these tests hermetic — no real ``AlertCooldownManager`` construction
    (which would try a real sync Redis client) for tests that are not
    themselves exercising the alert path.
    """

    def should_send(self, *_args, **_kwargs) -> bool:
        return True

    def record_sent(self, *_args, **_kwargs) -> None:
        pass


@pytest.mark.asyncio
async def test_transient_mark_has_positive_ttl():
    """Default (transient) marks keep today's TTL — the baseline this contrasts with."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("openai", "gpt-4o")

    redis = await store._get_redis()
    ttl = await redis.ttl("autobot:llm:deg:openai:gpt-4o")
    assert ttl > 0


@pytest.mark.asyncio
async def test_needs_reauth_mark_has_no_ttl():
    """needs_reauth is non-expiring in Redis (ttl() == -1, not merely a long TTL)."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)
    from llm_shared.provider_degradation import DegradationCause

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)

    redis = await store._get_redis()
    ttl = await redis.ttl("autobot:llm:deg:openai")
    assert ttl == -1  # Redis convention: key exists, no expiry set.
    assert await store.is_degraded("openai") is True


@pytest.mark.asyncio
async def test_clear_removes_needs_reauth_mark():
    """clear() is the only exit for a non-expiring needs_reauth mark."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)
    from llm_shared.provider_degradation import DegradationCause

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("anthropic", cause=DegradationCause.NEEDS_REAUTH)
    assert await store.is_degraded("anthropic") is True

    await store.clear("anthropic")

    assert await store.is_degraded("anthropic") is False


@pytest.mark.asyncio
async def test_clear_on_unmarked_key_is_a_noop():
    """clear() on a key that was never marked does not raise."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.clear("never-marked")

    assert await store.is_degraded("never-marked") is False


@pytest.mark.asyncio
async def test_degraded_entries_reports_cause():
    """degraded_entries() reports why each entry is degraded (#15022)."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)
    from llm_shared.provider_degradation import DegradationCause

    await store.mark_degraded("openai", "gpt-4o")
    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("anthropic", cause=DegradationCause.NEEDS_REAUTH)

    causes = {e["key"]: e["cause"] for e in await store.degraded_entries()}
    assert causes["autobot:llm:deg:openai:gpt-4o"] == "transient"
    assert causes["autobot:llm:deg:anthropic"] == "needs_reauth"


@pytest.mark.asyncio
async def test_no_redis_needs_reauth_fallback_has_no_expiry():
    """In-process fallback: needs_reauth stores expires_at=None (never expires)."""
    from llm_shared.provider_degradation import DegradationCause, ProviderDegradationStore

    store = ProviderDegradationStore()

    async def _raise(*_args, **_kwargs):
        raise ConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)

    cause, expires_at = store._local["autobot:llm:deg:openai"]
    assert cause is DegradationCause.NEEDS_REAUTH
    assert expires_at is None
    assert await store.is_degraded("openai") is True


@pytest.mark.asyncio
async def test_no_redis_clear_removes_local_entry():
    """clear() removes the in-process fallback entry too."""
    from llm_shared.provider_degradation import DegradationCause, ProviderDegradationStore

    store = ProviderDegradationStore()

    async def _raise(*_args, **_kwargs):
        raise ConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    assert await store.is_degraded("openai") is True

    await store.clear("openai")

    assert "autobot:llm:deg:openai" not in store._local
    assert await store.is_degraded("openai") is False


@pytest.mark.asyncio
async def test_needs_reauth_mark_emits_exactly_one_alert_per_cooldown():
    """A repeated needs_reauth mark is deduped by AlertCooldownManager itself —
    not by a second de-dup set in the degradation store (explicit AC in #15022).
    """
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)
    from llm_shared.provider_degradation import DegradationCause

    class _FakeCooldown:
        def __init__(self):
            self.should_send_calls = []
            self.sent = []

        def should_send(self, text, tier):
            self.should_send_calls.append((text, tier))
            return len(self.sent) == 0

        def record_sent(self, text, tier):
            self.sent.append((text, tier))

    fake = _FakeCooldown()

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: fake):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)

    # Both marks consulted alert_cooldown (no separate de-dup); it allowed
    # exactly one of them through.
    assert len(fake.should_send_calls) == 2
    assert len(fake.sent) == 1


@pytest.mark.asyncio
async def test_transient_mark_does_not_alert():
    """A transient mark never reaches the operator-alert path — only needs_reauth does."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    class _FailIfCalledCooldown:
        def should_send(self, *_args, **_kwargs):
            raise AssertionError("transient marks must not consult alert_cooldown")

        def record_sent(self, *_args, **_kwargs):
            raise AssertionError("transient marks must not record an alert")

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _FailIfCalledCooldown()):
        await store.mark_degraded("openai", "gpt-4o")


# ---------------------------------------------------------------------------
# #15022: base_provider._get_auth_token wiring — TokenExpiredError -> mark
# needs_reauth; a subsequent successful vault-backed resolve clears it.
# ---------------------------------------------------------------------------


class _FakeAuthStrategy:
    """Minimal ProviderAuthStrategy double — duck-types the two methods
    ``_get_auth_token`` actually calls, so these tests don't need a DB
    session or the vault machinery real OAuthAuth/SessionAuth require."""

    def __init__(self, *, vault_backed, resolve):
        self._vault_backed = vault_backed
        self._resolve = resolve

    def is_vault_backed(self) -> bool:
        return self._vault_backed

    async def resolve_token(self, session=None):
        return await self._resolve(session)


def _auth_probe_provider(name: str, auth_strategy):
    """Return a minimal concrete BaseProvider for exercising _get_auth_token.

    Mirrors ``base_provider_breaker_test.py``'s ``_ScriptedProvider`` — the
    established minimal-subclass pattern in this package.
    """
    from typing import AsyncIterator, List

    from llm_shared.base_provider import BaseProvider
    from llm_shared.models import LLMRequest, LLMResponse

    class _Provider(BaseProvider):
        async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
            raise NotImplementedError

        async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
            yield ""

        async def is_available(self) -> bool:
            return True

        async def list_models(self) -> List[str]:
            return []

    provider = _Provider({}, auth_strategy=auth_strategy)
    provider.provider_name = name
    return provider


@pytest.mark.asyncio
async def test_get_auth_token_marks_needs_reauth_on_token_expired():
    """TokenExpiredError from the auth strategy -> needs_reauth, not generic degraded."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store_instance = _make_store_with_fake_server(server)

    from llm_shared.base_provider import BaseProvider
    from llm_shared.provider_auth import TokenExpiredError

    async def _raise(_session):
        raise TokenExpiredError("dead credential")

    auth = _FakeAuthStrategy(vault_backed=True, resolve=_raise)
    provider = _auth_probe_provider("deadcred", auth)

    with _inject_globals(BaseProvider._get_auth_token, get_degradation_store=lambda: store_instance):
        with _inject_globals(store_instance.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
            with pytest.raises(TokenExpiredError):
                await provider._get_auth_token()

    assert await store_instance.is_degraded("deadcred") is True
    causes = {e["key"]: e["cause"] for e in await store_instance.degraded_entries()}
    assert causes["autobot:llm:deg:deadcred"] == "needs_reauth"


@pytest.mark.asyncio
async def test_get_auth_token_successful_vault_resolve_clears_needs_reauth():
    """A successful vault-backed resolve is the explicit clear (#15022)."""
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store_instance = _make_store_with_fake_server(server)

    from llm_shared.base_provider import BaseProvider
    from llm_shared.provider_degradation import DegradationCause

    with _inject_globals(store_instance.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store_instance.mark_degraded("revived", cause=DegradationCause.NEEDS_REAUTH)
    assert await store_instance.is_degraded("revived") is True

    async def _ok(_session):
        return "fresh-token"

    auth = _FakeAuthStrategy(vault_backed=True, resolve=_ok)
    provider = _auth_probe_provider("revived", auth)

    with _inject_globals(BaseProvider._get_auth_token, get_degradation_store=lambda: store_instance):
        token = await provider._get_auth_token()

    assert token == "fresh-token"
    assert await store_instance.is_degraded("revived") is False


@pytest.mark.asyncio
async def test_get_auth_token_apikey_success_does_not_touch_degradation_store():
    """ApiKeyAuth (is_vault_backed()==False) never calls the degradation store —
    it can never have raised TokenExpiredError, so there is nothing to clear.
    """
    _require_fakeredis()
    server = fakeredis_async.FakeServer()
    store_instance = _make_store_with_fake_server(server)

    from llm_shared.base_provider import BaseProvider
    from llm_shared.provider_degradation import DegradationCause

    # Pre-mark needs_reauth for a DIFFERENT reason to prove ApiKeyAuth's
    # success path leaves existing store state alone.
    with _inject_globals(store_instance.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store_instance.mark_degraded("static", cause=DegradationCause.NEEDS_REAUTH)

    async def _ok(_session):
        return "sk-static"

    auth = _FakeAuthStrategy(vault_backed=False, resolve=_ok)
    provider = _auth_probe_provider("static", auth)

    with _inject_globals(BaseProvider._get_auth_token, get_degradation_store=lambda: store_instance):
        token = await provider._get_auth_token()

    assert token == "sk-static"
    # is_vault_backed() is False, so _get_auth_token never calls clear() —
    # the pre-existing mark is untouched.
    assert await store_instance.is_degraded("static") is True


# ---------------------------------------------------------------------------
# ModelFallbackCoordinator integration: mark on exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_marks_degraded_on_rate_limit():
    """execute_with_fallback marks a provider degraded when rate-limited."""
    _require_fakeredis()
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
async def test_registry_skips_degraded_provider():
    """get_provider_for_request skips a degraded provider and picks the next."""
    _require_fakeredis()
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
async def test_registry_all_degraded_proceeds():
    """When all providers are degraded, the registry still returns one (no hard fail)."""
    _require_fakeredis()
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
async def test_coordinator_marks_final_provider_on_exhaustion():
    """The provider failing on the LAST attempt is marked too (mark before break)."""
    _require_fakeredis()
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
async def test_coordinator_marks_registry_resolved_provider_when_request_has_none():
    """A request without a provider still produces a matchable mark via selected_provider."""
    _require_fakeredis()
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
async def test_registry_stamps_selected_provider_and_skips_model_scoped_mark():
    """End-to-end: a model-scoped coordinator mark is honored by registry selection."""
    _require_fakeredis()
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
