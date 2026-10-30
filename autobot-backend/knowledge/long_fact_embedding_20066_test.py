# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A fact too long for the embedding model still gets one vector, over all of its text (#20066)."""

from __future__ import annotations

import math

import pytest

from knowledge import long_fact_embedding as lfe


def _embed_recording(calls):
    async def embed(text, **kwargs):
        calls.append((text, kwargs))
        return [1.0, 0.0] if text.startswith("a") else [0.0, 1.0]

    return embed


@pytest.mark.asyncio
async def test_a_short_fact_is_embedded_as_it_is():
    calls = []
    assert await lfe.embed_in_windows(_embed_recording(calls), "a short fact", model_name="m") == [1.0, 0.0]
    assert calls == [("a short fact", {"model_name": "m"})]


@pytest.mark.asyncio
async def test_no_window_passes_the_limit_and_the_whole_text_counts(monkeypatch):
    monkeypatch.setattr(lfe, "WINDOW_CHARS", 4)
    calls = []
    vector = await lfe.embed_in_windows(_embed_recording(calls), "aaaabbbb", max_attempts=3)
    assert [text for text, _ in calls] == ["aaaa", "bbbb"]
    assert all(kwargs == {"max_attempts": 3} for _, kwargs in calls)
    assert vector == pytest.approx([1 / math.sqrt(2), 1 / math.sqrt(2)])


@pytest.mark.asyncio
async def test_one_failed_window_is_a_failed_embedding(monkeypatch):
    monkeypatch.setattr(lfe, "WINDOW_CHARS", 4)

    async def embed(text, **_kwargs):
        return [] if text.startswith("b") else [1.0]

    assert await lfe.embed_in_windows(embed, "aaaabbbb") == []


@pytest.mark.asyncio
async def test_past_the_window_cap_only_the_leading_ones_are_embedded(monkeypatch):
    monkeypatch.setattr(lfe, "WINDOW_CHARS", 2)
    monkeypatch.setattr(lfe, "MAX_WINDOWS", 2)
    calls = []
    await lfe.embed_in_windows(_embed_recording(calls), "aabbcc")
    assert [text for text, _ in calls] == ["aa", "bb"]
