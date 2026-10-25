# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The embedding_model health probe names a model that cannot embed (#18834)."""

from __future__ import annotations

import asyncio

import pytest

import api.embedding_model_health as probe


@pytest.fixture(autouse=True)
def _fresh_cache():
    probe._last_probe.clear()
    probe._refreshing.clear()
    yield
    probe._last_probe.clear()
    probe._refreshing.clear()


async def _settle():
    """Await every scheduled background refresh, rather than guessing a number of loop turns."""
    tasks = list(probe._refresh_tasks)
    if tasks:
        await asyncio.gather(*tasks)
    assert not probe._refresh_tasks, "each finished refresh drops its strong reference"


@pytest.mark.asyncio
async def test_a_chat_model_configured_as_the_embedding_model_is_degraded(monkeypatch):
    """The live #18834 install: the pre-2026-10-11 template wrote the light chat model."""
    monkeypatch.setattr(probe, "active_embedding_model", lambda: "phi3:mini")
    called = []
    monkeypatch.setattr(probe, "probe_one_embedding", lambda m: called.append(m))

    result = await probe._embedding_model_health_probe()

    assert result.status == "degraded"
    assert "'phi3:mini' is not an embedding model" in result.detail and "#19373" in result.detail
    assert called == [], "no embedding is attempted with a model that cannot be one"


@pytest.mark.asyncio
async def test_an_embedding_model_that_embeds_is_ok(monkeypatch):
    monkeypatch.setattr(probe, "active_embedding_model", lambda: "nomic-embed-text:latest")

    async def ok(model):
        return None

    monkeypatch.setattr(probe, "probe_one_embedding", ok)
    await probe._embedding_model_health_probe()
    await _settle()

    result = await probe._embedding_model_health_probe()
    assert result.status == "ok" and result.detail is None
    assert result.data == {"embedding_model": "nomic-embed-text:latest", "embedding_measured": True}


@pytest.mark.asyncio
async def test_an_embedding_model_that_fails_to_embed_is_degraded_after_the_background_probe(monkeypatch):
    """Identity is not enough: the model may not be pulled, or the server may not embed."""
    monkeypatch.setattr(probe, "active_embedding_model", lambda: "nomic-embed-text:latest")
    calls = []

    async def fails(model):
        calls.append(model)
        return "no vector returned"

    monkeypatch.setattr(probe, "probe_one_embedding", fails)
    first = await probe._embedding_model_health_probe()
    await _settle()
    second = await probe._embedding_model_health_probe()
    await _settle()

    assert first.status == "ok", "the first call answers before the background probe finishes"
    assert first.data["embedding_measured"] is False
    assert first.detail == "identity checked; test embedding not yet measured (runs in the background)"
    assert second.status == "degraded" and "could not embed (no vector returned)" in second.detail
    assert calls == ["nomic-embed-text:latest"], "cached for the TTL: one probe, not one per call"


@pytest.mark.asyncio
async def test_switching_the_model_probes_the_new_one(monkeypatch):
    current = {"m": "nomic-embed-text:latest"}
    monkeypatch.setattr(probe, "active_embedding_model", lambda: current["m"])
    calls = []

    async def ok(model):
        calls.append(model)
        return None

    monkeypatch.setattr(probe, "probe_one_embedding", ok)
    await probe._embedding_model_health_probe()
    await _settle()
    current["m"] = "mxbai-embed-large:latest"
    await probe._embedding_model_health_probe()
    await _settle()

    assert calls == ["nomic-embed-text:latest", "mxbai-embed-large:latest"]


def _age(model, seconds):
    """Move *model*'s cached result *seconds* into the past (the clock itself is the loop's too)."""
    measured_at, error = probe._last_probe[model]
    probe._last_probe[model] = (measured_at - seconds, error)


@pytest.mark.asyncio
async def test_a_result_older_than_the_ttl_is_probed_again(monkeypatch):
    model = "nomic-embed-text:latest"
    monkeypatch.setattr(probe, "active_embedding_model", lambda: model)
    calls = []

    async def ok(m):
        calls.append(m)
        return None

    monkeypatch.setattr(probe, "probe_one_embedding", ok)
    await probe._embedding_model_health_probe()
    await _settle()
    _age(model, probe.EMBEDDING_PROBE_TTL_S - 5)
    await probe._embedding_model_health_probe()
    await _settle()
    assert calls == [model], "inside the TTL the cached result is reused"

    _age(model, 10)
    await probe._embedding_model_health_probe()
    await _settle()
    assert calls == [model, model], "past the TTL it re-probes"


@pytest.mark.asyncio
async def test_a_background_embedding_that_hangs_is_recorded_as_timed_out(monkeypatch):
    monkeypatch.setattr(probe, "active_embedding_model", lambda: "nomic-embed-text:latest")
    monkeypatch.setattr(probe, "EMBEDDING_PROBE_TIMEOUT_S", 0.01)

    async def hangs(model):
        await asyncio.sleep(60)

    monkeypatch.setattr(probe, "probe_one_embedding", hangs)
    await probe._embedding_model_health_probe()
    await _settle()

    result = await probe._embedding_model_health_probe()
    assert result.status == "degraded" and "could not embed (timed out)" in result.detail
    assert result.data["embedding_measured"] is True


def _patch_embedder(monkeypatch, embedder):
    """Patch the real fallback embedder that ``probe_one_embedding`` imports at call time."""
    monkeypatch.setattr("services.npu_client.generate_embedding_with_fallback", embedder)


@pytest.mark.asyncio
async def test_the_real_probe_reports_the_exception_type_name(monkeypatch):
    async def raises(text, model_name=None):
        raise ConnectionError("server at a private address refused")

    _patch_embedder(monkeypatch, raises)
    assert await probe.probe_one_embedding("nomic-embed-text:latest") == "ConnectionError"


@pytest.mark.asyncio
async def test_the_real_probe_reports_an_empty_vector(monkeypatch):
    async def empty(text, model_name=None):
        return []

    _patch_embedder(monkeypatch, empty)
    assert await probe.probe_one_embedding("nomic-embed-text:latest") == "no vector returned"


@pytest.mark.asyncio
async def test_the_real_probe_passes_a_returned_vector(monkeypatch):
    """The contrast: a vector is success, so the two failure answers above are not constant."""

    async def vector(text, model_name=None):
        return [0.1, 0.2]

    _patch_embedder(monkeypatch, vector)
    assert await probe.probe_one_embedding("nomic-embed-text:latest") is None
