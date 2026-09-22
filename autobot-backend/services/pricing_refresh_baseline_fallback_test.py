# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The hardcoded baselines are the last resort, and only the last resort (#16230).

Owner ruling during #16230: the five `BaselinePricingSource` tables stay and get
wired in, rather than being deleted as superseded. Without them, a first boot
while both vendor catalogues are unreachable leaves the store empty, `sync_cache`
cold, and `budget.py` raising `UnpricedModel` for every model — every LLC agent
run blocked until a vendor comes back.

Wiring a hardcoded table back into a migration whose whole point was to remove
hardcoded tables is only safe if two things are true, and neither is visible in
a diff. This file is those two things:

1. **Unreachable while anything live answers.** One live catalogue responding is
   enough to keep the baselines out of the path entirely.
2. **Never written over real data.** A store holding prices that were fetched
   from a real catalogue at *some* point beats literals frozen in a source file,
   however recently the outage started.

Plus the third, which is about how the answer is labelled rather than which
answer it is: a baseline price must be impossible to mistake for a live one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_shared.pricing.sources import ModelPricing


def _store(existing=None):
    store = MagicMock()
    for name in ("set_refresh_status", "retain_refresh_status", "set_crosscheck"):
        setattr(store, name, AsyncMock())
    store.get_all_by_model = AsyncMock(return_value=existing or {})
    store.renew_price_ttls = AsyncMock(return_value=len(existing or {}) * 2)
    store.set_many = AsyncMock(side_effect=lambda merged: len(merged))
    store.set_model_index = AsyncMock(side_effect=lambda merged: len(merged))
    return store


def _mp(provider, model_id, inp, out, source):
    return ModelPricing(provider=provider, model_id=model_id, input_per_1m=inp, output_per_1m=out, source=source)


def _source(provider, prices=None, raises=None):
    src = MagicMock()
    src.provider = provider
    src.fetch = AsyncMock(side_effect=raises) if raises else AsyncMock(return_value=prices or {})
    return src


async def _refresh(primary, secondary, store):
    from services.pricing_refresh import refresh_all

    with (
        patch("services.pricing_refresh._build_sources", return_value=(primary, secondary)),
        patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store),
    ):
        return await refresh_all()


# --- rule 1: unreachable while anything live answers -----------------------


@pytest.mark.asyncio
async def test_a_working_primary_never_reaches_the_baselines():
    store = _store()
    summary = await _refresh(
        _source("litellm", {"gpt-4o": _mp("openai", "gpt-4o", 2.5, 10.0, "litellm")}),
        _source("openrouter", {}),
        store,
    )

    [merged] = store.set_many.call_args.args
    assert {p.source for p in merged.values()} == {"litellm"}
    assert "baseline_fallback" not in summary


@pytest.mark.asyncio
async def test_a_working_secondary_alone_still_does_not_reach_the_baselines():
    """The cross-check catalogue is not a catalogue, but it *is* a live answer.

    OpenRouter alone writes nothing — that rule predates #16230 and is unchanged.
    What must not happen is the baselines sliding in underneath it: frozen
    literals are a worse answer than "wait for the source of record", and this
    is the one ordering a reader is most likely to get wrong.
    """
    store = _store()
    summary = await _refresh(
        _source("litellm", {}),
        _source("openrouter", {"x/y": _mp("x", "y", 1.0, 1.0, "openrouter")}),
        store,
    )

    store.set_many.assert_not_called()
    assert "baseline_fallback" not in summary


@pytest.mark.asyncio
async def test_both_catalogues_down_and_an_empty_store_seeds_from_the_baselines():
    store = _store(existing={})
    summary = await _refresh(_source("litellm", {}), _source("openrouter", {}), store)

    assert summary["baseline_fallback"]["used"] is True
    [merged] = store.set_many.call_args.args
    assert merged, "the fallback wrote an empty catalogue"
    store.set_model_index.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_raising_source_counts_as_down_too():
    """`_fetch` swallows the exception into an empty dict; the fallback must see that."""
    store = _store(existing={})
    summary = await _refresh(
        _source("litellm", raises=RuntimeError("dns")),
        _source("openrouter", raises=RuntimeError("dns")),
        store,
    )

    assert summary["baseline_fallback"]["used"] is True


# --- rule 2: never written over real data ----------------------------------


@pytest.mark.asyncio
async def test_a_populated_store_is_not_overwritten_when_both_catalogues_are_down():
    """Yesterday's live prices beat literals frozen in a source file."""
    store = _store(existing={"gpt-4o": _mp("openai", "gpt-4o", 2.5, 10.0, "litellm")})
    summary = await _refresh(_source("litellm", {}), _source("openrouter", {}), store)

    store.set_many.assert_not_called()
    store.set_model_index.assert_not_called()
    assert summary["baseline_fallback"]["used"] is False
    assert summary["baseline_fallback"]["reason"] == "store already populated"


@pytest.mark.asyncio
async def test_a_populated_store_has_its_ttls_renewed_rather_than_being_left_to_expire():
    """Not overwriting is not the same as keeping (#16230 review).

    Prices carry a TTL of the refresh cadence plus one hour, so they survive
    exactly one missed refresh. Writing nothing on this path let them expire
    about an hour after the failed refresh and the store emptied itself anyway
    -- the outcome the no-overwrite rule exists to prevent. The earlier version
    of this test asserted `set_many` was not called and stopped there, which
    passed throughout the defect.
    """
    store = _store(existing={"gpt-4o": _mp("openai", "gpt-4o", 2.5, 10.0, "litellm")})
    summary = await _refresh(_source("litellm", {}), _source("openrouter", {}), store)

    store.renew_price_ttls.assert_awaited_once()
    assert summary["baseline_fallback"]["ttls_renewed"] == 2
    # EXPIRE only -- renewal must not become a rewrite, or a stale price would
    # come back looking freshly fetched.
    store.set_many.assert_not_called()


@pytest.mark.asyncio
async def test_an_empty_store_seeds_baselines_instead_of_renewing_nothing():
    """The contrast: renewal is for a store that HAS something to renew."""
    store = _store(existing={})
    summary = await _refresh(_source("litellm", {}), _source("openrouter", {}), store)

    store.renew_price_ttls.assert_not_awaited()
    assert summary["baseline_fallback"]["used"] is True


# --- rule 3: a baseline price can never read as a live one ------------------


@pytest.mark.asyncio
async def test_every_seeded_price_is_labelled_baseline_and_stale():
    store = _store(existing={})
    await _refresh(_source("litellm", {}), _source("openrouter", {}), store)

    [merged] = store.set_many.call_args.args
    assert {p.source for p in merged.values()} == {"baseline"}
    assert {p.crosscheck for p in merged.values()} == {"stale"}


@pytest.mark.asyncio
async def test_no_seeded_price_claims_a_fetch_date():
    """The literals were written at an unknown time; `updated_at` must not say "now".

    `BaselinePricingSource.fetch` used to stamp `self._now()`, so a price frozen
    two years ago reported as fetched this second — and `/cost/pricing`
    published that as the catalogue's real freshness. That is the same
    manufactured-freshness defect as the `"pricing_date": "2025-01-01"` literal
    this PR removed, just harder to see.
    """
    store = _store(existing={})
    await _refresh(_source("litellm", {}), _source("openrouter", {}), store)

    [merged] = store.set_many.call_args.args
    assert all(p.updated_at is None for p in merged.values())


@pytest.mark.asyncio
async def test_the_seeded_catalogue_covers_all_five_providers():
    """A fallback missing a provider is an outage for that provider's models only.

    Counted by provider rather than by model: a model count would pass on four
    sources plus one that happens to be large.
    """
    store = _store(existing={})
    await _refresh(_source("litellm", {}), _source("openrouter", {}), store)

    [merged] = store.set_many.call_args.args
    assert {p.provider for p in merged.values()} == {
        "anthropic",
        "openai",
        "google",
        "deepseek",
        "vertexai",
    }
