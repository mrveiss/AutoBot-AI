# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the live pricing sources (#16229).

Samples mirror the real response shapes measured on 10 Sep 2026 (LiteLLM:
``input_cost_per_token``/``output_cost_per_token``/``litellm_provider``;
OpenRouter: ``data[].pricing.prompt``/``completion`` as per-token strings).
They are built through helpers rather than literal price tables, so the
repo-wide pricing-table sweep never mistakes a fixture for a price table.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from llm_shared.pricing import live_sources
from llm_shared.pricing.live_sources import (
    LiteLLMPricingSource,
    OpenRouterPricingSource,
    parse_litellm,
    parse_openrouter,
    per_1m,
)

_NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def _litellm_entry(inp, out, provider, cache_read=None):
    entry = {"litellm_provider": provider, "input_cost_per_token": inp, "output_cost_per_token": out}
    if cache_read is not None:
        entry["cache_read_input_token_cost"] = cache_read
    return entry


def _or_model(model_id, prompt, completion, cache_read=None):
    pricing = {"prompt": prompt, "completion": completion}
    if cache_read is not None:
        pricing["input_cache_read"] = cache_read
    return {"id": model_id, "pricing": pricing}


def _client(status, body=None, raises=None):
    """A shared-client stand-in whose tracked_request yields one response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.tracked_request = MagicMock(side_effect=raises) if raises else MagicMock(return_value=cm)
    return client


def test_per_1m_never_turns_an_unknown_into_zero():
    assert per_1m("0.000001") == pytest.approx(1.0)
    assert per_1m("0") == 0.0, "a stated zero is a real (free) price"
    for unknown in (None, True, "-1", -1, "n/a", {}, float("nan")):
        assert per_1m(unknown) is None, f"{unknown!r} must be unknown, not a price"


def test_litellm_keeps_only_fully_priced_entries_in_per_1m():
    doc = {
        "sample_spec": {"litellm_provider": "spec", "input_cost_per_token": 0, "output_cost_per_token": 0},
        "claude-haiku-4-5": _litellm_entry(1e-06, 5e-06, "anthropic", cache_read=1e-07),
        "no-output-price": {"litellm_provider": "x", "input_cost_per_token": 1e-06},
        "no-provider": {"input_cost_per_token": 1e-06, "output_cost_per_token": 1e-06},
        "negative": _litellm_entry(-1, 1e-06, "x"),
        "not-a-dict": "text",
    }
    parsed = parse_litellm(doc, _NOW)
    assert list(parsed) == ["claude-haiku-4-5"]
    p = parsed["claude-haiku-4-5"]
    assert (p.provider, p.source, p.updated_at) == ("anthropic", "litellm", _NOW)
    assert (p.input_per_1m, p.output_per_1m, p.cache_read_per_1m) == pytest.approx((1.0, 5.0, 0.1))
    assert p.cache_write_per_1m is None, "an unstated cache-write price is unknown, not free"


def test_openrouter_sentinels_free_and_unknown_are_told_apart():
    doc = {
        "data": [
            _or_model("anthropic/claude-haiku-4.5", "0.000001", "0.000005"),
            _or_model("openrouter/auto-beta", "-1", "-1"),
            _or_model("vendor/some-model:free", "0", "0"),
            _or_model("no-vendor-prefix", "0.1", "0.1"),
            {"id": "vendor/unpriced"},
        ]
    }
    parsed = parse_openrouter(doc, _NOW)
    assert sorted(parsed) == ["anthropic/claude-haiku-4.5", "vendor/some-model:free"]
    haiku = parsed["anthropic/claude-haiku-4.5"]
    assert (haiku.provider, haiku.model_id, haiku.source) == ("anthropic", "claude-haiku-4.5", "openrouter")
    assert (haiku.input_per_1m, haiku.output_per_1m) == pytest.approx((1.0, 5.0))
    assert haiku.cache_read_per_1m is None
    assert parsed["vendor/some-model:free"].input_per_1m == 0.0


@pytest.mark.parametrize("doc", [None, [], {}, {"data": "not-a-list"}, {"data": [None, 3]}])
def test_a_document_of_the_wrong_shape_parses_to_nothing(doc):
    assert parse_litellm(doc, _NOW) == {}
    assert parse_openrouter(doc, _NOW) == {}


@pytest.mark.asyncio
async def test_fetch_goes_through_the_guarded_client_without_redirects():
    client = _client(200, {"claude-haiku-4-5": _litellm_entry(1e-06, 5e-06, "anthropic")})
    with patch.object(live_sources, "get_http_client", return_value=client):
        parsed = await LiteLLMPricingSource().fetch()
    assert list(parsed) == ["claude-haiku-4-5"]
    _args, kwargs = client.tracked_request.call_args
    assert kwargs["guard_egress"] is False, "public-only egress guard (CLAUDE rule 8)"
    assert "allow_redirects" not in kwargs, "a redirect would escape the egress check"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client",
    [
        _client(500, {"claude-haiku-4-5": _litellm_entry(1e-06, 5e-06, "anthropic")}),
        _client(200, {}),
        _client(200, None, raises=aiohttp.ClientError("connection reset")),
    ],
    ids=["http-error", "200-with-empty-body", "transport-error"],
)
async def test_every_failed_fetch_yields_nothing(client):
    """A 200 with an empty body is a failed price fetch too -- it must not count as fresh prices."""
    with patch.object(live_sources, "get_http_client", return_value=client):
        assert await LiteLLMPricingSource().fetch() == {}
        assert await OpenRouterPricingSource().fetch() == {}
