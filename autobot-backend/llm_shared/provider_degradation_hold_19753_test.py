# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A quota hold outlasts the transient skip window; a transient mark is unchanged (#19753)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_shared import provider_degradation
from llm_shared.provider_degradation import DegradationCause, ProviderDegradationStore


def _store(*, redis_up=True):
    store = ProviderDegradationStore()
    redis = MagicMock(set=AsyncMock())
    store._get_redis = AsyncMock(return_value=redis) if redis_up else AsyncMock(side_effect=ConnectionError("down"))
    return store, redis


@pytest.mark.asyncio
async def test_a_transient_mark_keeps_the_configured_window():
    store, redis = _store()
    await store.mark_degraded("ollama", "m")
    assert redis.set.await_args.kwargs["ex"] == provider_degradation._DEGRADATION_TTL_SECONDS


@pytest.mark.asyncio
async def test_a_quota_hold_lasts_as_long_as_it_is_given():
    store, redis = _store()
    await store.mark_degraded("ollama", "m", ttl_seconds=7200)
    assert redis.set.await_args.kwargs["ex"] == 7200


@pytest.mark.asyncio
async def test_a_needs_reauth_mark_never_expires_whatever_ttl_is_passed():
    store, redis = _store()
    await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH, ttl_seconds=60)
    assert redis.set.await_args.kwargs["ex"] is None


@pytest.mark.asyncio
async def test_the_in_process_copy_honours_the_hold_when_redis_is_down(monkeypatch):
    store, _ = _store(redis_up=False)
    now = [1000.0]
    monkeypatch.setattr(provider_degradation.time, "monotonic", lambda: now[0])
    await store.mark_degraded("ollama", "m", ttl_seconds=7200)

    now[0] += provider_degradation._DEGRADATION_TTL_SECONDS + 1  # past the transient window, inside the hold
    assert await store.is_degraded("ollama", "m") is True
    now[0] += 7200  # past the hold
    assert await store.is_degraded("ollama", "m") is False
