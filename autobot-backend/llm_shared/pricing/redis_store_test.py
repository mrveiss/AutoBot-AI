# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`PricingRedisStore`'s read and renewal contracts (#16230 review).

Three properties, each of which was wrong and each of which fails silently:

* An operator override must reach the synchronous consumers. `get_all_by_model`
  scanned only the by-model index, while `set_override` writes to its own
  prefix -- so the emergency lever every cold-cache warning tells an operator to
  reach for did nothing for `budget.py` or `calculate_cost`.
* A record that will not parse must fail the whole read. Dropping it let
  `refresh_snapshot` install the remainder with a fresh `fetched_at`, making an
  incomplete catalogue indistinguishable from a complete one.
* Prices preserved through a failed refresh must have their TTL re-armed. Not
  overwriting them is not the same as keeping them: they carry a TTL of the
  refresh cadence plus one hour and would otherwise expire through the outage.
"""

from __future__ import annotations

import json

import pytest

from llm_shared.pricing.redis_store import PricingRedisStore
from llm_shared.pricing.sources import ModelPricing


class _FakeRedis:
    """Enough Redis for these reads: scan_iter, mget, expire."""

    def __init__(self, data: dict[str, str]):
        self.data = dict(data)
        self.expired: list[tuple[str, int]] = []

    async def scan_iter(self, pattern):  # noqa: ANN001 - mirrors the real signature
        prefix = pattern.rstrip("*")
        for key in list(self.data):
            if key.startswith(prefix):
                yield key

    async def mget(self, *keys):
        return [self.data.get(k) for k in keys]

    async def expire(self, key, ttl):  # noqa: ANN001
        self.expired.append((key, ttl))
        return key in self.data


def _store(data: dict[str, str]) -> tuple[PricingRedisStore, _FakeRedis]:
    store = PricingRedisStore()
    fake = _FakeRedis(data)

    async def _redis():
        return fake

    store._redis = _redis  # type: ignore[method-assign]
    return store, fake


def _json(model_id: str, inp: float, out: float, source: str = "litellm") -> str:
    return json.dumps(
        ModelPricing(provider="test", model_id=model_id, input_per_1m=inp, output_per_1m=out, source=source).to_dict()
    )


# --- overrides -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_catalogue_price_is_returned_when_no_override_exists():
    """The baseline, so the override test below is not passing on an empty read."""
    store, _ = _store({"model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0)})
    assert (await store.get_all_by_model())["gpt-4o"].input_per_1m == 2.5


@pytest.mark.asyncio
async def test_an_operator_override_reaches_the_mirrored_set():
    store, _ = _store(
        {
            "model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0),
            "model_pricing:override:gpt-4o": _json("gpt-4o", 99.0, 99.0, source="override"),
        }
    )
    result = await store.get_all_by_model()
    assert result["gpt-4o"].input_per_1m == 99.0, "the catalogue price won; the override did nothing"


@pytest.mark.asyncio
async def test_an_override_for_a_model_absent_from_the_catalogue_is_still_returned():
    """An override is how an operator prices a model the catalogue never carried."""
    store, _ = _store({"model_pricing:override:some-new-model": _json("some-new-model", 1.0, 2.0)})
    assert "some-new-model" in await store.get_all_by_model()


# --- partial reads ---------------------------------------------------------


@pytest.mark.asyncio
async def test_a_malformed_record_fails_the_whole_read():
    store, _ = _store(
        {
            "model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0),
            "model_pricing:by_model:broken": "{not json",
        }
    )
    with pytest.raises(ValueError, match="unparseable pricing record"):
        await store.get_all_by_model()


@pytest.mark.asyncio
async def test_the_error_names_the_key_so_the_bad_record_can_be_found():
    store, _ = _store({"model_pricing:by_model:broken": "{not json"})
    with pytest.raises(ValueError, match="broken"):
        await store.get_all_by_model()


@pytest.mark.asyncio
async def test_a_missing_value_is_skipped_rather_than_failing():
    """A key that vanished between SCAN and MGET is a race, not a corrupt record."""
    store, fake = _store({"model_pricing:by_model:gone": _json("gone", 1.0, 1.0)})
    fake.data["model_pricing:by_model:gone"] = None  # type: ignore[assignment]
    assert await store.get_all_by_model() == {}


# --- TTL renewal -----------------------------------------------------------


@pytest.mark.asyncio
async def test_renewal_re_arms_price_keys():
    store, fake = _store(
        {
            "model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0),
            "model_pricing:openai:gpt-4o": _json("gpt-4o", 2.5, 10.0),
        }
    )
    assert await store.renew_price_ttls() == 2
    assert {k for k, _ in fake.expired} == set(fake.data)


@pytest.mark.asyncio
async def test_renewal_skips_the_status_records():
    """`refresh_status` and `crosscheck` say WHEN a refresh last succeeded.

    Renewing them through a failed refresh would make the failure report itself
    as recent -- the manufactured freshness this whole area exists to prevent.
    """
    store, fake = _store(
        {
            "model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0),
            "model_pricing:refresh_status": "{}",
            "model_pricing:crosscheck": "{}",
        }
    )
    assert await store.renew_price_ttls() == 1
    assert [k for k, _ in fake.expired] == ["model_pricing:by_model:gpt-4o"]


@pytest.mark.asyncio
async def test_renewal_counts_each_key_once():
    """by_model keys are nested under the provider prefix; a per-prefix scan
    double-counted them and issued a redundant EXPIRE for each."""
    store, fake = _store(
        {
            "model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0),
            "model_pricing:by_model:gpt-4.1": _json("gpt-4.1", 2.0, 8.0),
            "model_pricing:openai:gpt-4o": _json("gpt-4o", 2.5, 10.0),
        }
    )
    assert await store.renew_price_ttls() == 3
    assert len(fake.expired) == 3, "a key was expired more than once"


@pytest.mark.asyncio
async def test_renewal_leaves_overrides_alone():
    """Overrides carry no TTL by design; an EXPIRE would give one a deadline."""
    store, fake = _store(
        {
            "model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0),
            "model_pricing:override:gpt-4o": _json("gpt-4o", 99.0, 99.0),
        }
    )
    await store.renew_price_ttls()
    assert all("override" not in key for key, _ in fake.expired), "an operator override was given an expiry"


@pytest.mark.asyncio
async def test_renewal_does_not_rewrite_values():
    """EXPIRE only. A renewal that rewrote would make stale prices look refetched."""
    data = {"model_pricing:by_model:gpt-4o": _json("gpt-4o", 2.5, 10.0)}
    store, fake = _store(data)
    before = dict(fake.data)
    await store.renew_price_ttls()
    assert fake.data == before
