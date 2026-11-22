# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Editing a long fact keeps it searchable, and the embedding backend probe answers truthfully (#20076)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from background_vectorization import BackgroundVectorizer
from knowledge import facts as facts_module
from knowledge.facts import FactsMixin
from knowledge.long_fact_embedding import WINDOW_CHARS

_MARKER = {"embedding_window_chars": 1, "embedding_windows": 9}


@pytest.fixture
def setup(monkeypatch):
    space = MagicMock(model="m")
    monkeypatch.setattr(facts_module, "current_space", AsyncMock(return_value=space))
    calls = []

    async def embed(text, **_kwargs):
        calls.append(text)
        return [1.0, 0.0]

    monkeypatch.setattr(facts_module, "_generate_embedding_with_npu_fallback", embed)
    kb = MagicMock()
    kb._write_vector = AsyncMock(return_value=True)
    kb._mark_vectorization_succeeded = AsyncMock()
    kb._record_failed_vectorization = AsyncMock()
    return kb, calls


def _written_metadata(kb) -> dict:
    return kb._write_vector.await_args.args[4]


@pytest.mark.asyncio
async def test_an_edit_past_the_context_embeds_in_windows_and_is_marked(setup) -> None:
    kb, calls = setup
    await FactsMixin._revectorize_fact(kb, "f", "a" * (WINDOW_CHARS * 2), {})
    assert len(calls) == 2 and all(len(window) == WINDOW_CHARS for window in calls)
    assert _written_metadata(kb)["embedding_windows"] == 2
    kb._mark_vectorization_succeeded.assert_awaited_once_with("f")
    kb._record_failed_vectorization.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_edit_from_long_to_short_drops_the_marker(setup) -> None:
    kb, calls = setup
    await FactsMixin._revectorize_fact(kb, "f", "short", {"title": "t", **_MARKER})
    written = _written_metadata(kb)
    assert calls == ["short"]
    assert written["title"] == "t" and not set(_MARKER) & set(written)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (AsyncMock(return_value=[0.1]), True),
        (AsyncMock(return_value=[]), False),
        (AsyncMock(side_effect=OSError), False),
    ],
    ids=["answer", "empty", "exception"],
)
@pytest.mark.asyncio
async def test_the_backend_probe(monkeypatch, answer, expected) -> None:
    monkeypatch.setattr("knowledge.embedding_space_binding.current_space", AsyncMock(return_value=MagicMock(model="m")))
    monkeypatch.setattr(facts_module, "_generate_embedding_with_npu_fallback", answer)
    assert await BackgroundVectorizer()._embedding_backend_answers(MagicMock()) is expected
    assert answer.await_args.kwargs["max_attempts"] == 1
