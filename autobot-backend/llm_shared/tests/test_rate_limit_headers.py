# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15026: harvesting provider rate-limit headers into the headroom store.

Covers the header->window mapping and the BaseProvider harvest hook:
harvest-on-success, harvest-on-429, absent headers, Redis-down, and that
harvesting issues no request of its own. The store itself (cross-worker,
expiry, in-process fallback) is covered by test_quota_headroom.py.
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import List

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from llm_shared.quota_headroom import QuotaHeadroomStore
from llm_shared.rate_limit_headers import has_header_mapping, parse_rate_limit_headers

_OPENAI_HEADERS = {
    "x-ratelimit-limit-requests": "500",
    "x-ratelimit-remaining-requests": "42",
    "x-ratelimit-reset-requests": "1m30s",
    "x-ratelimit-limit-tokens": "30000",
    "x-ratelimit-remaining-tokens": "0",
    "x-ratelimit-reset-tokens": "250ms",
}


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def test_openai_headers_map_to_rpm_and_tpm():
    now = 1_000.0
    obs = {o.window: o for o in parse_rate_limit_headers("openai", _OPENAI_HEADERS, now=now)}

    assert set(obs) == {"rpm", "tpm"}
    assert (obs["rpm"].limit, obs["rpm"].remaining, obs["rpm"].resets_at) == (500.0, 42.0, now + 90.0)
    assert obs["rpm"].source == "x-ratelimit-remaining-requests"
    assert obs["tpm"].resets_at == pytest.approx(now + 0.25)


def test_zero_remaining_is_a_real_entry_distinct_from_absent():
    obs = {o.window: o for o in parse_rate_limit_headers("openai", _OPENAI_HEADERS)}

    assert obs["tpm"].remaining == 0.0  # the header said 0
    assert parse_rate_limit_headers("openai", {}) == []  # nothing said -> nothing recorded


def test_anthropic_headers_use_rfc3339_reset():
    headers = {
        "anthropic-ratelimit-requests-limit": "50",
        "anthropic-ratelimit-requests-remaining": "49",
        "anthropic-ratelimit-requests-reset": "2030-01-01T00:00:00Z",
        "anthropic-ratelimit-output-tokens-remaining": "8000",
    }
    obs = {o.window: o for o in parse_rate_limit_headers("anthropic", headers)}

    assert set(obs) == {"rpm", "output_tpm"}
    assert obs["rpm"].resets_at == 1893456000.0
    assert obs["output_tpm"].limit is None  # absent stays None, never a fabricated 0


def test_unmapped_provider_and_garbage_values_yield_nothing():
    assert has_header_mapping("openai") and not has_header_mapping("ollama")
    assert parse_rate_limit_headers("ollama", _OPENAI_HEADERS) == []
    junk = {"x-ratelimit-limit-requests": "lots", "x-ratelimit-reset-requests": "soon"}
    assert parse_rate_limit_headers("openai", junk) == []


def test_non_finite_numbers_are_not_a_reading():
    """nan / inf parse as floats but are not a quota; they must yield no entry."""
    bad = {
        "x-ratelimit-limit-requests": "inf",
        "x-ratelimit-remaining-requests": "nan",
        "x-ratelimit-limit-tokens": "-inf",
    }
    assert parse_rate_limit_headers("openai", bad) == []


# ---------------------------------------------------------------------------
# Harvest hook (BaseProvider._headroom_http_client)
# ---------------------------------------------------------------------------


def _provider(name: str):
    from typing import AsyncIterator

    from llm_shared.base_provider import BaseProvider
    from llm_shared.models import LLMRequest, LLMResponse

    class _P(BaseProvider):
        async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
            raise NotImplementedError

        async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
            yield ""

        async def is_available(self) -> bool:
            return True

        async def list_models(self) -> List[str]:
            return []

    p = _P({})
    p.provider_name = name
    return p


def _local_store(down: Exception | None = None) -> QuotaHeadroomStore:
    store = QuotaHeadroomStore()

    async def _raise():
        raise down or RedisConnectionError("down")

    store._get_redis = _raise  # type: ignore[method-assign]
    return store


async def _drain() -> None:
    """Let fire-and-forget harvest tasks finish."""
    for _ in range(3):
        await asyncio.sleep(0)
    pending = [t for t in asyncio.all_tasks() if t.get_name() == "quota-headroom-harvest"]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def _client_through(provider, status: int, headers: dict):
    """An httpx client built by the provider hook, served by a counting MockTransport."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers=headers, json={})

    client = provider._headroom_http_client(
        functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler))
    )
    assert client is not None
    return client, calls


@pytest.fixture
def _store(_inject_globals):
    store = _local_store()
    from llm_shared.base_provider import BaseProvider

    with _inject_globals(BaseProvider._record_headroom, get_quota_headroom_store=lambda: store):
        yield store


@pytest.mark.asyncio
async def test_harvest_on_success_response(_store):
    client, calls = await _client_through(_provider("openai"), 200, _OPENAI_HEADERS)
    async with client:
        await client.post("http://provider.invalid/v1/chat")
    await _drain()

    rpm = await _store.get("openai", "rpm")
    assert rpm is not None and rpm.remaining == 42 and rpm.limit == 500
    assert time.time() - rpm.observed_at < 5  # observed_at lets a consumer judge freshness
    assert len(calls) == 1  # harvesting added no request


@pytest.mark.asyncio
async def test_harvest_on_429_response(_store):
    headers = dict(_OPENAI_HEADERS, **{"x-ratelimit-remaining-requests": "0"})
    client, calls = await _client_through(_provider("openai"), 429, headers)
    async with client:
        resp = await client.post("http://provider.invalid/v1/chat")
    await _drain()

    assert resp.status_code == 429
    entry = await _store.get("openai", "rpm")
    assert entry is not None and entry.remaining == 0
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_no_headers_means_no_entry(_store):
    client, _ = await _client_through(_provider("openai"), 200, {})
    async with client:
        await client.post("http://provider.invalid/v1/chat")
    await _drain()

    assert await _store.all_entries("openai") == []
    assert await _store.get("openai", "rpm") is None


@pytest.mark.asyncio
async def test_unmapped_provider_gets_no_hook():
    assert _provider("ollama")._headroom_http_client(httpx.AsyncClient) is None
    assert _provider("openai")._headroom_http_client(None) is None  # SDK without the class: no hook, no failure


@pytest.mark.asyncio
async def test_store_failure_never_reaches_the_response_path(_inject_globals):
    """A store that raises something other than 'Redis down' must not fail the response."""
    from llm_shared.base_provider import BaseProvider

    store = _local_store(down=RuntimeError("boom"))
    with _inject_globals(BaseProvider._record_headroom, get_quota_headroom_store=lambda: store):
        client, _ = await _client_through(_provider("openai"), 200, _OPENAI_HEADERS)
        async with client:
            resp = await client.post("http://provider.invalid/v1/chat")
        await _drain()

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_redis_down_falls_back_in_process(_store):
    """Redis unreachable -> the in-process fallback holds the reading; the caller sees no exception."""
    client, _ = await _client_through(_provider("openai"), 200, _OPENAI_HEADERS)
    async with client:
        await client.post("http://provider.invalid/v1/chat")
    await _drain()

    assert (await _store.get("openai", "tpm")) is not None
    assert any(k.endswith(":openai:default:tpm") for k in _store._local)


@pytest.mark.asyncio
async def test_real_sdk_clients_carry_the_hook():
    """OpenAI's provider hands the SDK a client whose response hooks include the harvester."""
    pytest.importorskip("openai")
    from llm_shared.providers.openai import OpenAIProvider

    client = OpenAIProvider({"api_key": "sk-test"})._create_client()

    assert client._client.event_hooks["response"], "no response hook installed on the SDK client"
