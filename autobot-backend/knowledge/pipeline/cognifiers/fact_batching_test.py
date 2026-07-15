# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for multi-chunk fact-extraction batching (#10647).

- A batch of chunks is extracted in ONE LLM call, with facts mapped back to
  their source chunk.
- A malformed (non-object) batched response falls back to per-chunk extraction.
- A single-chunk batch skips batching.
"""

from __future__ import annotations

import json
import types
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from knowledge.pipeline.cognifiers.fact_extractor import FactExtractor


def _chunk(label: str = ""):
    return types.SimpleNamespace(id=uuid4(), content=f"text for {label}", document_id=None)


def _ctx():
    return types.SimpleNamespace(document_id=uuid4(), facts=[])


def _fact(subject: str):
    return {
        "subject": subject,
        "predicate": "is",
        "object": "thing",
        "fact_type": "statement",
        "description": "",
        "context": "",
        "confidence": 0.9,
    }


def _extractor():
    ext = FactExtractor.__new__(FactExtractor)  # bypass heavy __init__
    ext.batch_size = 5
    return ext


@pytest.mark.asyncio
async def test_batched_extraction_one_call_maps_facts_to_chunks():
    ext = _extractor()
    c0, c1 = _chunk("c0"), _chunk("c1")
    resp = json.dumps({"0": [_fact("A")], "1": [_fact("B")]})
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content=resp)))

    facts = await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 1  # ONE batched call, not one per chunk
    by_subject = {f.subject: f for f in facts}
    assert by_subject["A"].source_chunk_ids == [c0.id]  # facts mapped to correct chunk
    assert by_subject["B"].source_chunk_ids == [c1.id]
    # the batched call passes the extraction task type
    _, kwargs = ext.llm.chat.call_args
    assert kwargs.get("llm_type") == "extraction"


@pytest.mark.asyncio
async def test_malformed_batch_falls_back_to_per_chunk():
    ext = _extractor()
    bad = types.SimpleNamespace(content="not json at all")  # batched call → non-dict → raise
    per_chunk = types.SimpleNamespace(content=json.dumps([_fact("X")]))
    ext.llm = types.SimpleNamespace(chat=AsyncMock(side_effect=[bad, per_chunk, per_chunk]))
    c0, c1 = _chunk("c0"), _chunk("c1")

    facts = await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 3  # 1 failed batch + 2 per-chunk fallback
    assert len(facts) == 2
    assert {f.source_chunk_ids[0] for f in facts} == {c0.id, c1.id}


@pytest.mark.asyncio
async def test_single_fact_dict_value_is_coerced_to_list():
    ext = _extractor()
    c0, c1 = _chunk("c0"), _chunk("c1")
    # chunk 0 returns a single fact object instead of a list — should be tolerated.
    resp = json.dumps({"0": _fact("A"), "1": [_fact("B")]})
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content=resp)))

    facts = await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 1  # no fallback; coerced, not dropped
    assert {f.subject for f in facts} == {"A", "B"}


@pytest.mark.asyncio
async def test_disjoint_keys_fall_back_to_per_chunk():
    ext = _extractor()
    c0, c1 = _chunk("c0"), _chunk("c1")
    # valid object, but keys don't match chunk indices (e.g. model used names)
    bad = types.SimpleNamespace(content=json.dumps({"chunk_a": [_fact("A")]}))
    per_chunk = types.SimpleNamespace(content=json.dumps([_fact("X")]))
    ext.llm = types.SimpleNamespace(chat=AsyncMock(side_effect=[bad, per_chunk, per_chunk]))

    facts = await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 3  # disjoint keys → fallback to per-chunk
    assert len(facts) == 2


@pytest.mark.asyncio
async def test_single_chunk_skips_batching():
    ext = _extractor()
    ext.llm = types.SimpleNamespace(
        chat=AsyncMock(return_value=types.SimpleNamespace(content=json.dumps([_fact("S")])))
    )

    c0 = _chunk("c0")
    facts = await ext._process_batch([c0], _ctx())

    assert ext.llm.chat.call_count == 1
    assert len(facts) == 1
    assert facts[0].source_chunk_ids == [c0.id]


# ---------------------------------------------------------------------------
# #11017 — fact_extractor routes through the shared helper: honors config flag,
# derives allowed types from the FactType Literal, inherits partial-response fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_uses_legacy_per_chunk(monkeypatch):
    """cognifier_multichunk_batching=False → one LLM call PER chunk (no batching)."""
    import knowledge.pipeline.cognifiers.fact_extractor as fx

    monkeypatch.setattr(fx.config, "cognifier_multichunk_batching", False)
    c0, c1 = _chunk("c0"), _chunk("c1")
    ext = _extractor()
    ext.llm = types.SimpleNamespace(
        chat=AsyncMock(
            side_effect=[
                types.SimpleNamespace(content=json.dumps([_fact("A")])),
                types.SimpleNamespace(content=json.dumps([_fact("B")])),
            ]
        )
    )
    facts = await ext._process_batch([c0, c1], _ctx())
    assert ext.llm.chat.call_count == 2  # per-chunk, not batched
    assert {f.subject for f in facts} == {"A", "B"}


@pytest.mark.asyncio
async def test_partial_batch_recovers_missing_chunk(monkeypatch):
    """A batch response missing an index recovers that chunk via per-chunk fallback
    instead of silently dropping it — inherited from the shared helper (#11012/#11017)."""
    import knowledge.pipeline.cognifiers.fact_extractor as fx

    monkeypatch.setattr(fx.config, "cognifier_multichunk_batching", True)
    c0, c1 = _chunk("c0"), _chunk("c1")
    ext = _extractor()
    # Batch reply omits index "1"; the per-chunk fallback for c1 returns a fact.
    ext.llm = types.SimpleNamespace(
        chat=AsyncMock(
            side_effect=[
                types.SimpleNamespace(content=json.dumps({"0": [_fact("A")]})),
                types.SimpleNamespace(content=json.dumps([_fact("recovered")])),
            ]
        )
    )
    facts = await ext._process_batch([c0, c1], _ctx())
    subjects = {f.subject for f in facts}
    assert "A" in subjects and "recovered" in subjects  # c1 not dropped


def test_valid_fact_types_derived_from_literal():
    """VALID_FACT_TYPES and the prompt fragment come from the FactType Literal (#11017)."""
    from typing import get_args

    from knowledge.pipeline.cognifiers import fact_extractor as fx
    from knowledge.pipeline.models.fact import FactType

    expected = set(get_args(FactType))
    assert set(fx.VALID_FACT_TYPES) == expected
    for value in expected:
        assert value in fx.FACT_EXTRACTION_PROMPT
        assert value in fx.FACT_EXTRACTION_BATCH_PROMPT
