# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15022 AC1 / AC4 / AC7: registry selection, per-credential alerting, Redis-down.

Kept apart from test_provider_degradation_reauth.py (374 lines, store-level
needs_reauth coverage) so each file stays well under the 600-line cap.

Each test is written so it FAILS on the pre-change code:

- AC1: a provider-level needs_reauth mark was invisible to the model-scoped
  ``is_degraded(name, model)`` the registry asks, and the all-degraded
  fall-through selected a dead credential anyway.
- AC4: ``alert_cooldown`` collapses standalone numbers to ``<N>``, so the old
  alert text for ``acct-1`` and ``acct-2`` shared one fingerprint.
- AC7: a needs_reauth mark made on a healthy Redis vanished when Redis went
  down (the local dict was never populated), and a mark made while Redis was
  down was never replayed once it came back.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import fakeredis
except ImportError:
    fakeredis = None  # type: ignore[assignment]


class _NoopCooldown:
    def should_send(self, *_a, **_k) -> bool:
        return True

    def record_sent(self, *_a, **_k) -> None:
        pass


def _provider(name: str) -> MagicMock:
    prov = MagicMock()
    prov.provider_name = name
    prov.is_available = AsyncMock(return_value=True)
    return prov


def _registry(*names: str):
    from llm_shared.provider_registry import ProviderRegistry

    registry = ProviderRegistry()
    providers = {n: _provider(n) for n in names}
    for prov in providers.values():
        registry.register(prov)
    registry.set_fallback_chain(list(names))
    return registry, providers


def _request(model: str):
    from llm_shared.models import LLMRequest

    req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    req.model_name = model
    return req


# ---------------------------------------------------------------------------
# AC1 -- the registry never selects a needs_reauth credential (decision: option C)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_scoped_selection_skips_provider_level_needs_reauth(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """A provider-level needs_reauth mark applies to every model of that provider."""
    from llm_shared.provider_degradation import DegradationCause
    from llm_shared.provider_registry import ProviderRegistry

    store = _make_store_with_fake_server(fakeredis.FakeServer())
    registry, providers = _registry("openai", "anthropic")
    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)

    with _inject_globals(ProviderRegistry.get_provider_for_request, get_degradation_store=lambda: store):
        chosen = await registry.get_provider_for_request(request=_request("gpt-4o"))

    assert chosen is providers["anthropic"]


@pytest.mark.asyncio
async def test_all_needs_reauth_raises_typed_error_not_none(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """Nothing selectable -> AllCredentialsNeedReauthError naming the candidates (not None, not a dead pick)."""
    from llm_shared.provider_degradation import AllCredentialsNeedReauthError, DegradationCause
    from llm_shared.provider_registry import ProviderRegistry

    store = _make_store_with_fake_server(fakeredis.FakeServer())
    registry, _ = _registry("openai", "anthropic")
    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
        await store.mark_degraded("anthropic", "claude-opus-4", cause=DegradationCause.NEEDS_REAUTH)

    with _inject_globals(ProviderRegistry.get_provider_for_request, get_degradation_store=lambda: store):
        with pytest.raises(AllCredentialsNeedReauthError) as excinfo:
            await registry.get_provider_for_request(request=_request("claude-opus-4"))

    assert excinfo.value.providers == ["openai", "anthropic"]
    assert "need re-auth" in str(excinfo.value)


@pytest.mark.asyncio
async def test_all_transient_still_falls_through(_require_fakeredis, _make_store_with_fake_server, _inject_globals):
    """The #11519 fall-through is unchanged for TRANSIENT marks (the contrast case)."""
    from llm_shared.provider_registry import ProviderRegistry

    store = _make_store_with_fake_server(fakeredis.FakeServer())
    registry, providers = _registry("openai", "anthropic")
    await store.mark_degraded("openai", "gpt-4o")
    await store.mark_degraded("anthropic", "gpt-4o")

    with _inject_globals(ProviderRegistry.get_provider_for_request, get_degradation_store=lambda: store):
        chosen = await registry.get_provider_for_request(request=_request("gpt-4o"))

    assert chosen is providers["openai"]


@pytest.mark.asyncio
async def test_provider_level_transient_mark_still_does_not_imply_models(
    _require_fakeredis, _make_store_with_fake_server
):
    """The tested #11519 invariant survives: only NEEDS_REAUTH is credential-scoped."""
    store = _make_store_with_fake_server(fakeredis.FakeServer())
    await store.mark_degraded("groq")

    assert await store.is_degraded("groq", "llama3") is False
    assert await store.needs_reauth("groq", "llama3") is False


@pytest.mark.asyncio
async def test_needs_reauth_does_not_return_after_the_degradation_ttl(monkeypatch, _inject_globals):
    """Past the transient TTL (in-process path) a transient mark has lapsed; a needs_reauth one has not."""
    import time

    from llm_shared import provider_degradation as pd

    store = pd.ProviderDegradationStore()
    store._get_redis = AsyncMock(side_effect=ConnectionError("down"))  # type: ignore[method-assign]
    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=pd.DegradationCause.NEEDS_REAUTH)
    await store.mark_degraded("anthropic")

    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + pd._DEGRADATION_TTL_SECONDS + 1)

    assert await store.is_degraded("anthropic") is False  # transient: back in the pool
    assert await store.needs_reauth("openai", "gpt-4o") is True  # dead credential: still out


@pytest.mark.asyncio
async def test_coordinator_dispatch_returns_a_distinguishable_error_response():
    """The coordinator answers the typed error with an error response (not an exception) and no fallback hop."""
    from llm_shared.model_fallback_coordinator import ModelFallbackCoordinator
    from llm_shared.provider_degradation import AllCredentialsNeedReauthError

    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(side_effect=AllCredentialsNeedReauthError(["openai"]))

    response = await ModelFallbackCoordinator().execute_with_fallback(_request("gpt-4o"), registry)

    assert response.content == "" and "need re-auth" in response.error
    assert registry.get_provider_for_request.await_count == 1  # no retry against a dead credential


@pytest.mark.asyncio
async def test_llm_service_attempt_resolution_reports_the_reauth_reason():
    """LLMService's per-attempt provider resolution turns the typed error into a reason, not a crash."""
    from llm_shared.provider_degradation import AllCredentialsNeedReauthError
    from services.llm_fallback_chain import resolve_attempt_provider

    dead = MagicMock()
    dead.get_provider_for_request = AsyncMock(side_effect=AllCredentialsNeedReauthError(["openai"]))
    none = MagicMock()
    none.get_provider_for_request = AsyncMock(return_value=None)

    assert await resolve_attempt_provider(dead, None, None) == (None, "all credentials need re-auth: openai")
    assert await resolve_attempt_provider(none, None, None) == (None, None)  # plain "no capacity" is unchanged


@pytest.mark.asyncio
async def test_openai_and_anthropic_compat_answer_503_with_the_reauth_reason():
    """HTTP callers get 503 whose detail tells re-auth from capacity (both compat routes share this helper)."""
    from fastapi import HTTPException

    from api.openai_compat import _select_provider_or_503
    from llm_shared.provider_degradation import AllCredentialsNeedReauthError

    dead = MagicMock()
    dead.get_provider_for_request = AsyncMock(side_effect=AllCredentialsNeedReauthError(["openai"]))
    none = MagicMock()
    none.get_provider_for_request = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as reauth:
        await _select_provider_or_503(dead, _request("gpt-4o"))
    with pytest.raises(HTTPException) as capacity:
        await _select_provider_or_503(none, _request("gpt-4o"))

    assert reauth.value.status_code == capacity.value.status_code == 503
    assert "need re-auth" in reauth.value.detail and reauth.value.detail != capacity.value.detail


def test_every_registry_caller_handles_the_typed_error():
    """Every production ``get_provider_for_request`` caller references the typed error (#15022 AC1).

    A caller left unaware would turn "all credentials need re-auth" into an
    unhandled exception (HTTP 500) instead of a distinguishable answer.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    callers = [
        "api/openai_compat.py",  # also serves api/anthropic_compat.py, which imports the helper
        "api/chat_compare.py",
        "llm_shared/model_fallback_coordinator.py",
    ]
    for rel in callers:
        text = (root / rel).read_text(encoding="utf-8")
        assert re.search(r"get_provider_for_request", text), rel
        assert "AllCredentialsNeedReauthError" in text, f"{rel} does not handle AllCredentialsNeedReauthError"
    # LLMService reaches the registry through this helper (behavioural test below).
    assert "AllCredentialsNeedReauthError" in (root / "services/llm_fallback_chain.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC4 -- exactly one alert per credential per cooldown tier, via the REAL alert_cooldown
# ---------------------------------------------------------------------------


@pytest.fixture
def _real_cooldown(monkeypatch):
    """A real AlertCooldownManager over fakeredis -- not a double."""
    pytest.importorskip("fakeredis")
    from autobot_shared import alert_cooldown

    client = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(alert_cooldown, "get_redis_client", lambda **_k: client)
    return alert_cooldown.AlertCooldownManager()


class _SpyLogger:
    """Collects the operator-alert warnings; independent of logging-handler configuration."""

    def __init__(self) -> None:
        self.alerts: list[str] = []

    def warning(self, fmt, *args, **_k) -> None:
        self.alerts.append(fmt % args if args else fmt)

    def info(self, *_a, **_k) -> None:
        pass

    def debug(self, *_a, **_k) -> None:
        pass


@pytest.mark.asyncio
async def test_repeat_mark_alerts_once_and_distinct_numbered_credentials_each_alert(_real_cooldown, _inject_globals):
    """Real cooldown: same credential twice -> 1 alert; ``acct-1`` and ``acct-2`` -> 1 each.

    Contrast: with the pre-change text ("...needs re-auth: acct-1" / "...acct-2")
    the normaliser rewrote both to "...<N>", so the second dead credential was
    suppressed and never reported.
    """
    from llm_shared.provider_degradation import DegradationCause, ProviderDegradationStore

    store = ProviderDegradationStore()
    store._get_redis = AsyncMock(side_effect=ConnectionError("no redis"))  # type: ignore[method-assign]
    spy = _SpyLogger()

    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _real_cooldown, logger=spy):
        await store.mark_degraded("acct-1", cause=DegradationCause.NEEDS_REAUTH)
        await store.mark_degraded("acct-1", cause=DegradationCause.NEEDS_REAUTH)
        await store.mark_degraded("acct-2", cause=DegradationCause.NEEDS_REAUTH)

    assert len(spy.alerts) == 2
    assert "acct-1" in spy.alerts[0] and "acct-2" in spy.alerts[1]


def test_alert_text_fingerprint_is_unique_per_target():
    """The fingerprint ``alert_cooldown`` computes differs for targets that differ only in a number."""
    from autobot_shared.alert_cooldown import _fingerprint
    from llm_shared.provider_degradation import _reauth_alert_text

    assert _fingerprint(_reauth_alert_text("claude-3")) != _fingerprint(_reauth_alert_text("claude-4"))
    assert _fingerprint(_reauth_alert_text("openai:gpt-4")) != _fingerprint(_reauth_alert_text("openai:gpt-5"))
    assert _fingerprint(_reauth_alert_text("openai")) == _fingerprint(_reauth_alert_text("openai"))


# ---------------------------------------------------------------------------
# AC7 -- the in-process fallback preserves needs_reauth across a Redis outage
# ---------------------------------------------------------------------------


def _down(store):
    """Make *store*'s Redis unreachable; returns a callable restoring the original."""
    original = store._get_redis

    async def _raise(*_a, **_k):
        raise ConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    def _restore() -> None:
        store._get_redis = original  # type: ignore[method-assign]

    return _restore


@pytest.mark.asyncio
async def test_needs_reauth_marked_on_healthy_redis_survives_an_outage(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """Marked while Redis is up, still enforced (and still non-expiring) after it goes down."""
    from llm_shared.provider_degradation import DegradationCause

    store = _make_store_with_fake_server(fakeredis.FakeServer())
    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)

    _down(store)

    assert await store.needs_reauth("openai", "gpt-4o") is True
    assert store._local["autobot:llm:deg:openai"][1] is None


@pytest.mark.asyncio
async def test_needs_reauth_observed_from_another_worker_survives_an_outage(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """A worker that only READ the mark from Redis also keeps enforcing it when Redis dies."""
    from llm_shared.provider_degradation import DegradationCause

    server = fakeredis.FakeServer()
    worker_a, worker_b = _make_store_with_fake_server(server), _make_store_with_fake_server(server)
    with _inject_globals(worker_a.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await worker_a.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    assert await worker_b.needs_reauth("openai") is True  # observed -> mirrored

    _down(worker_b)

    assert await worker_b.needs_reauth("openai") is True


@pytest.mark.asyncio
async def test_mark_made_during_outage_is_replayed_when_redis_returns(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """Contrast: pre-change, a mark written to the local dict never reached Redis, so peers never saw it."""
    from llm_shared.provider_degradation import DegradationCause

    server = fakeredis.FakeServer()
    store, peer = _make_store_with_fake_server(server), _make_store_with_fake_server(server)
    restore = _down(store)
    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    restore()

    assert await store.needs_reauth("openai") is True  # first Redis-up access flushes the mark
    assert await peer.needs_reauth("openai") is True
    assert await (await peer._get_redis()).ttl("autobot:llm:deg:openai") == -1


@pytest.mark.asyncio
async def test_clear_made_during_outage_is_replayed_when_redis_returns(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """Contrast: pre-change, a failed Redis delete left a revived credential parked forever (non-expiring)."""
    from llm_shared.provider_degradation import DegradationCause

    server = fakeredis.FakeServer()
    store, peer = _make_store_with_fake_server(server), _make_store_with_fake_server(server)
    with _inject_globals(store.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    restore = _down(store)
    await store.clear("openai")
    assert await store.needs_reauth("openai") is False  # outage view already cleared
    restore()

    assert await store.needs_reauth("openai") is False
    assert await peer.needs_reauth("openai") is False


@pytest.mark.asyncio
async def test_clear_by_another_worker_drops_the_local_mirror(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """A mirrored mark that was cleared elsewhere is not resurrected by a later outage."""
    from llm_shared.provider_degradation import DegradationCause

    server = fakeredis.FakeServer()
    worker_a, worker_b = _make_store_with_fake_server(server), _make_store_with_fake_server(server)
    with _inject_globals(worker_a.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await worker_a.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    assert await worker_b.needs_reauth("openai") is True
    await worker_a.clear("openai")
    assert await worker_b.needs_reauth("openai") is False  # Redis up: mirror refreshed

    _down(worker_b)

    assert await worker_b.needs_reauth("openai") is False


@pytest.mark.asyncio
async def test_replayed_clear_does_not_erase_a_newer_mark_from_another_worker(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """Two writers: A clears during an outage, B then marks anew; A's replay must leave B's mark.

    Contrast: an unconditional replayed DELETE removed B's newer mark, putting a
    dead credential back in the pool with no TTL to heal it.
    """
    from llm_shared.provider_degradation import DegradationCause

    server = fakeredis.FakeServer()
    worker_a, worker_b = _make_store_with_fake_server(server), _make_store_with_fake_server(server)
    with _inject_globals(worker_a.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await worker_a.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    restore = _down(worker_a)
    await worker_a.clear("openai")  # A re-authed, but Redis is unreachable: the clear is deferred
    with _inject_globals(worker_b.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await worker_b.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)  # newer, dead again
    restore()

    assert await worker_a.needs_reauth("openai") is True  # replay ran and left B's mark in place
    assert await worker_b.needs_reauth("openai") is True


@pytest.mark.asyncio
async def test_replayed_clear_still_removes_the_mark_it_saw(
    _require_fakeredis, _make_store_with_fake_server, _inject_globals
):
    """The compare-and-delete does not break the single-writer case: the seen mark is removed."""
    from llm_shared.provider_degradation import DegradationCause

    server = fakeredis.FakeServer()
    worker_a, peer = _make_store_with_fake_server(server), _make_store_with_fake_server(server)
    with _inject_globals(worker_a.mark_degraded, _get_alert_cooldown=lambda: _NoopCooldown()):
        await worker_a.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    restore = _down(worker_a)
    await worker_a.clear("openai")
    restore()

    assert await worker_a.needs_reauth("openai") is False
    assert await peer.needs_reauth("openai") is False
