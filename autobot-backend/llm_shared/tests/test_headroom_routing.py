# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15028: route on observed headroom before dispatch.

Covers the pre-emptive switch (zero rate-limited round-trips), the no-data
passthrough, stale-observation rejection, the all-exhausted chain, the
observed-limit override of the rate limiter's guessed RPM, and the
needs_reauth skip (also in test_provider_degradation_reauth_selection.py).
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from llm_shared.fallback_chain import FallbackChain, FallbackChainManager
from llm_shared.model_fallback_coordinator import ModelFallbackCoordinator
from llm_shared.models import LLMRequest, LLMResponse, ProviderType
from llm_shared.optimization.rate_limiter import RateLimitError
from llm_shared.quota_headroom import QuotaHeadroomEntry, QuotaHeadroomStore


def _store() -> QuotaHeadroomStore:
    store = QuotaHeadroomStore()

    async def _raise():
        raise RedisConnectionError("down")

    store._get_redis = _raise  # type: ignore[method-assign]
    return store


def _put(store: QuotaHeadroomStore, provider: str, *, remaining, limit=500.0, age=0.0, resets_in=60.0, window="rpm"):
    """Seed an observation straight into the in-process store (so ``observed_at`` can be aged)."""
    now = time.time()
    entry = QuotaHeadroomEntry(
        provider=provider,
        window=window,
        account_id="default",
        limit=limit,
        remaining=remaining,
        resets_at=None if resets_in is None else now + resets_in,
        observed_at=now - age,
        source="test",
    )
    store._local[f"autobot:llm:headroom:{provider}:default:{window}"] = (entry, time.monotonic() + 3600)


class _World:
    """Two providers behind a fake registry, a gpt-4o -> claude-sonnet-4 chain, and the seams injected."""

    def __init__(self, inject, store: QuotaHeadroomStore, openai_effect=None):
        self.calls = {"openai": 0, "anthropic": 0}
        self.events: list[dict] = []
        self.store = store
        self.openai_effect = openai_effect

        def make(name):
            async def chat(request):
                self.calls[name] += 1
                if name == "openai" and self.openai_effect is not None:
                    raise self.openai_effect
                return LLMResponse(content="ok", model=request.model_name, provider=name)

            prov = MagicMock()
            prov.provider_name = name
            prov.chat_completion = chat
            return prov

        self.providers = {n: make(n) for n in ("openai", "anthropic")}

        async def select(provider_name=None, request=None, **_k):
            name = request.provider.value if request.provider else "openai"
            request.metadata["selected_provider"] = name
            return self.providers[name]

        self.registry = MagicMock()
        self.registry.get_provider_for_request = select

        mgr = FallbackChainManager.__new__(FallbackChainManager)
        mgr._chains = {
            "gpt-4o": FallbackChain(
                primary_model="gpt-4o",
                fallback_models=["claude-sonnet-4"],
                primary_provider="openai",
                fallback_providers=["anthropic"],
            )
        }
        degradation = MagicMock()
        degradation.mark_degraded = AsyncMock()
        degradation.is_degraded = AsyncMock(return_value=False)  # a hop is skipped while degraded (#19753)

        async def emit(**kw):
            self.events.append(kw)

        from llm_shared import headroom_routing as hr

        self._ctx = [
            inject(ModelFallbackCoordinator.execute_with_fallback, get_fallback_chain_manager=lambda: mgr,
                   get_degradation_store=lambda: degradation, emit_fallback_event=emit),
            inject(hr.exhausted_window, get_quota_headroom_store=lambda: store),
        ]  # fmt: skip

    def __enter__(self):
        for c in self._ctx:
            c.__enter__()
        return self

    def __exit__(self, *exc):
        for c in reversed(self._ctx):
            c.__exit__(*exc)

    async def run(self) -> LLMResponse:
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        req.model_name = "gpt-4o"
        req.provider = ProviderType("openai")
        return await ModelFallbackCoordinator().execute_with_fallback(req, self.registry)


@pytest.mark.asyncio
async def test_preemptive_switch_pays_zero_rate_limited_round_trips(_inject_globals):
    store = _store()
    _put(store, "openai", remaining=2)  # 0.4% left, floor is 5%

    with _World(_inject_globals, store) as world:
        resp = await world.run()

    assert world.calls == {"openai": 0, "anthropic": 1}  # the exhausted provider was never called
    assert resp.model == "claude-sonnet-4" and resp.fallback_used is True
    meta = resp.provider_metadata
    assert meta["fallback_reason"] == "headroom_preempt"
    assert meta["preemptive_switches"] == [
        {"from_model": "gpt-4o", "from_provider": "openai", "window": "rpm",
         "to_model": "claude-sonnet-4", "to_provider": "anthropic"}
    ]  # fmt: skip
    assert [e["reason"] for e in world.events] == ["headroom_preempt"]  # one fallback event, distinguishable


@pytest.mark.asyncio
async def test_no_headroom_data_is_todays_reactive_path(_inject_globals):
    with _World(_inject_globals, _store(), openai_effect=RateLimitError("quota")) as world:
        resp = await world.run()

    assert world.calls == {"openai": 1, "anthropic": 1}  # paid the 429 first, as today
    assert resp.provider_metadata["fallback_reason"] == "rate_limit_429"
    assert "preemptive_switches" not in resp.provider_metadata
    assert [e["reason"] for e in world.events] == ["rate_limit_429"]


@pytest.mark.asyncio
async def test_headroom_with_room_does_not_switch(_inject_globals):
    store = _store()
    _put(store, "openai", remaining=400)  # 80% left

    with _World(_inject_globals, store) as world:
        resp = await world.run()

    assert world.calls == {"openai": 1, "anthropic": 0}
    assert resp.fallback_used is False and "preemptive_switches" not in resp.provider_metadata


@pytest.mark.asyncio
async def test_stale_observation_is_rejected(_inject_globals):
    store = _store()
    _put(store, "openai", remaining=0, age=10_000.0)  # exhausted, but observed long ago

    with _World(_inject_globals, store) as world:
        await world.run()

    assert world.calls == {"openai": 1, "anthropic": 0}


@pytest.mark.asyncio
async def test_already_reset_window_is_not_exhausted(_inject_globals):
    store = _store()
    _put(store, "openai", remaining=0, resets_in=-5.0)

    with _World(_inject_globals, store) as world:
        await world.run()

    assert world.calls["openai"] == 1


@pytest.mark.asyncio
async def test_all_exhausted_chain_degrades_to_the_reactive_path(_inject_globals):
    """Every member near-exhausted: no cycling, the original target is dispatched once."""
    store = _store()
    _put(store, "openai", remaining=0)
    _put(store, "anthropic", remaining=0)

    with _World(_inject_globals, store) as world:
        resp = await world.run()

    assert world.calls == {"openai": 1, "anthropic": 0}
    assert resp.fallback_used is False and "preemptive_switches" not in resp.provider_metadata


@pytest.mark.asyncio
async def test_unreadable_store_reads_as_no_data(_inject_globals):
    store = _store()
    store.all_entries = AsyncMock(side_effect=RuntimeError("corrupt"))  # type: ignore[method-assign]

    with _World(_inject_globals, store) as world:
        await world.run()

    assert world.calls == {"openai": 1, "anthropic": 0}


# ---------------------------------------------------------------------------
# Rate limiter: observed limits replace the guess, only while fresh
# ---------------------------------------------------------------------------


@pytest.fixture
def _limiter(_inject_globals, monkeypatch):
    from llm_shared import cross_worker_rate_limiter as rl

    store = _store()
    for var in ("AUTOBOT_LLM_RL_OPENAI_RPM", "AUTOBOT_LLM_RL_OPENAI_BURST"):
        monkeypatch.delenv(var, raising=False)
    with _inject_globals(rl._effective_limits, get_quota_headroom_store=lambda: store):
        yield rl, store


@pytest.mark.asyncio
async def test_fresh_observed_limit_replaces_guessed_default(_limiter):
    rl, store = _limiter
    _put(store, "openai", remaining=10, limit=2000.0)

    capacity, rate = await rl._effective_limits("openai")

    assert (capacity, rate) == (2000.0, 2000.0 / 60.0)  # the guess was 500


@pytest.mark.asyncio
async def test_stale_observation_never_widens_the_bucket(_limiter):
    rl, store = _limiter
    _put(store, "openai", remaining=10, limit=100_000.0, age=10_000.0)

    assert await rl._effective_limits("openai") == (500.0, 500.0 / 60.0)


@pytest.mark.asyncio
async def test_no_observation_keeps_the_guess(_limiter):
    rl, _ = _limiter

    assert await rl._effective_limits("openai") == (500.0, 500.0 / 60.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"AUTOBOT_LLM_RL_OPENAI_RPM": "120"}, (500.0, 2.0)),  # RPM only: whole bucket stays configured
        ({"AUTOBOT_LLM_RL_OPENAI_BURST": "40"}, (40.0, 500.0 / 60.0)),  # BURST only
        ({"AUTOBOT_LLM_RL_OPENAI_RPM": "120", "AUTOBOT_LLM_RL_OPENAI_BURST": "120"}, (120.0, 2.0)),
        ({}, (2000.0, 2000.0 / 60.0)),  # neither set: observation applies
    ],
)
async def test_observation_applies_only_when_neither_rpm_nor_burst_is_set(_limiter, monkeypatch, env, expected):
    rl, store = _limiter
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    _put(store, "openai", remaining=10, limit=2000.0)

    assert await rl._effective_limits("openai") == expected
