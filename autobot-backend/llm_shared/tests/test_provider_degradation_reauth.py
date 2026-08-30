# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""needs_reauth coverage for ProviderDegradationStore (#15022).

Split out of test_provider_degradation.py, which stayed with the pre-#15022
baseline (Redis-backed / in-process-fallback marking, degraded_entries(),
the ModelFallbackCoordinator/ProviderRegistry integration tests). That file
hit 836 lines once this coverage was added — the repo caps a Python file at
600 lines — so this module holds everything specific to the needs_reauth
cause instead of trimming any assertion to fit under the cap:

- needs_reauth is non-expiring (Redis TTL == -1; in-process expires_at=None),
  contrasted against the transient cause's existing TTL behaviour.
- clear() — the only exit for a non-expiring mark — on a marked and an
  unmarked key, Redis-backed and in-process-fallback.
- degraded_entries() reports the cause per entry.
- The operator alert routes through the existing AlertCooldownManager
  (#1948): fires once per cooldown window, never fires for a transient mark.
- base_provider.BaseProvider._get_auth_token() wiring against the REAL
  class (not a test stub): TokenExpiredError -> mark needs_reauth, a
  successful vault-backed resolve -> clear, ApiKeyAuth success leaves the
  store untouched.

Shared store/global-injection fixtures live in conftest.py (fixtures, not
imports — llm_shared.tests has no __init__.py, so a plain import fails
collection; see conftest.py's docstring). This file keeps its own
one-line guarded fakeredis import instead of sharing it.
"""

from __future__ import annotations

import pytest

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:
    fakeredis_async = None  # type: ignore[assignment]

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
async def test_transient_mark_has_positive_ttl(_require_fakeredis, _make_store_with_fake_server):
    """Default (transient) marks keep today's TTL — the baseline this contrasts with."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.mark_degraded("openai", "gpt-4o")

    redis = await store._get_redis()
    ttl = await redis.ttl("autobot:llm:deg:openai:gpt-4o")
    assert ttl > 0


@pytest.mark.asyncio
async def test_needs_reauth_mark_has_no_ttl(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
    """needs_reauth is non-expiring in Redis (ttl() == -1, not merely a long TTL)."""
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
async def test_clear_removes_needs_reauth_mark(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
    """clear() is the only exit for a non-expiring needs_reauth mark."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)
    from llm_shared.provider_degradation import DegradationCause

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("anthropic", cause=DegradationCause.NEEDS_REAUTH)
    assert await store.is_degraded("anthropic") is True

    await store.clear("anthropic")

    assert await store.is_degraded("anthropic") is False


@pytest.mark.asyncio
async def test_clear_on_unmarked_key_is_a_noop(_require_fakeredis, _make_store_with_fake_server):
    """clear() on a key that was never marked does not raise."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.clear("never-marked")

    assert await store.is_degraded("never-marked") is False


@pytest.mark.asyncio
async def test_degraded_entries_reports_cause(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
    """degraded_entries() reports why each entry is degraded (#15022)."""
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
async def test_no_redis_needs_reauth_fallback_has_no_expiry(_inject_globals):
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
async def test_no_redis_clear_removes_local_entry(_inject_globals):
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
async def test_needs_reauth_mark_emits_exactly_one_alert_per_cooldown(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """A repeated needs_reauth mark is deduped by AlertCooldownManager itself —
    not by a second de-dup set in the degradation store (explicit AC in #15022).
    """
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
async def test_transient_mark_does_not_alert(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
    """A transient mark never reaches the operator-alert path — only needs_reauth does."""
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
async def test_get_auth_token_marks_needs_reauth_on_token_expired(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """TokenExpiredError from the auth strategy -> needs_reauth, not generic degraded."""
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
async def test_get_auth_token_successful_vault_resolve_clears_needs_reauth(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """A successful vault-backed resolve is the explicit clear (#15022)."""
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
async def test_get_auth_token_apikey_success_does_not_touch_degradation_store(
    _require_fakeredis,
    _make_store_with_fake_server,
    _inject_globals,
):
    """ApiKeyAuth (is_vault_backed()==False) never calls the degradation store —
    it can never have raised TokenExpiredError, so there is nothing to clear.
    """
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
