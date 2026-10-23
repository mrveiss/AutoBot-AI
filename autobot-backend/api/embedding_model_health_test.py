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
    for _ in range(5):
        await asyncio.sleep(0)


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
    assert result.status == "ok" and result.data == {"embedding_model": "nomic-embed-text:latest"}


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
