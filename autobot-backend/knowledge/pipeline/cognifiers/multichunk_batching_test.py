# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for shared multi-chunk cognifier batching (#10598).

Extends the fact_extractor batching (#10647) to entity/event/causal extractors
via the shared ``batched_chunk_extract`` helper:

- A batch of chunks is extracted in ONE LLM call (N sequential -> 1 batch).
- Facts/entities/edges map back to their source chunk (order + isolation kept).
- Batched calls pass ``llm_type="extraction"`` + ``structured_output=True``.
- A malformed / disjoint batched response falls back to per-chunk extraction.
- A single-chunk batch skips batching; the config flag can force the legacy path.
"""

from __future__ import annotations

import json
import types
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from knowledge.pipeline.cognifiers import llm_utils
from knowledge.pipeline.cognifiers.causal_relationship_extractor import CausalRelationshipExtractor
from knowledge.pipeline.cognifiers.entity_extractor import EntityExtractor
from knowledge.pipeline.cognifiers.event_extractor import EventExtractor


def _chunk(tag: str = ""):
    return types.SimpleNamespace(id=uuid4(), content=f"text for {tag}", document_id=None)


def _ctx():
    return types.SimpleNamespace(document_id=uuid4())


def _resp(payload: str):
    return types.SimpleNamespace(content=payload)


# ---------------------------------------------------------------------------
# Shared helper — pure, no domain models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_helper_single_call_maps_items_per_chunk():
    c0, c1 = _chunk("c0"), _chunk("c1")
    resp = json.dumps({"0": [{"v": "A"}], "1": [{"v": "B"}]})
    llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(resp)))

    seen: dict = {}

    def convert(raw, chunk):
        seen[chunk.id] = [r["v"] for r in raw]
        return [(chunk.id, r["v"]) for r in raw]

    async def extract_one(chunk):  # pragma: no cover - must not run in happy path
        raise AssertionError("per-chunk fallback should not run")

    items = await llm_utils.batched_chunk_extract(
        [c0, c1],
        llm=llm,
        batch_prompt_template="prefix {chunks}",
        llm_type="extraction",
        max_chunk_chars=2000,
        convert=convert,
        extract_one=extract_one,
    )

    assert llm.chat.call_count == 1  # ONE batched call, not one per chunk
    assert seen == {c0.id: ["A"], c1.id: ["B"]}  # per-chunk mapping preserved
    assert items == [(c0.id, "A"), (c1.id, "B")]  # order preserved
    _, kwargs = llm.chat.call_args
    assert kwargs.get("llm_type") == "extraction"
    assert kwargs.get("structured_output") is True


@pytest.mark.asyncio
async def test_helper_malformed_falls_back_to_per_chunk():
    c0, c1 = _chunk("c0"), _chunk("c1")
    llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp("not json")))
    calls: list = []

    async def extract_one(chunk):
        calls.append(chunk.id)
        return [chunk.id]

    items = await llm_utils.batched_chunk_extract(
        [c0, c1],
        llm=llm,
        batch_prompt_template="{chunks}",
        llm_type="extraction",
        max_chunk_chars=0,
        convert=lambda raw, chunk: raw,
        extract_one=extract_one,
    )

    assert llm.chat.call_count == 1  # the failed batch call
    assert calls == [c0.id, c1.id]  # both chunks fell back
    assert items == [c0.id, c1.id]


@pytest.mark.asyncio
async def test_helper_disjoint_keys_falls_back():
    c0, c1 = _chunk("c0"), _chunk("c1")
    llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(json.dumps({"x": [1]}))))
    called: list = []

    async def extract_one(chunk):
        called.append(chunk.id)
        return []

    await llm_utils.batched_chunk_extract(
        [c0, c1],
        llm=llm,
        batch_prompt_template="{chunks}",
        llm_type="extraction",
        max_chunk_chars=0,
        convert=lambda raw, chunk: raw,
        extract_one=extract_one,
    )

    assert called == [c0.id, c1.id]  # disjoint keys -> per-chunk fallback


@pytest.mark.asyncio
async def test_helper_single_chunk_skips_batching():
    c0 = _chunk("c0")
    llm = types.SimpleNamespace(chat=AsyncMock())  # must NOT be called for batch path

    async def extract_one(chunk):
        return ["one"]

    items = await llm_utils.batched_chunk_extract(
        [c0],
        llm=llm,
        batch_prompt_template="{chunks}",
        llm_type="extraction",
        max_chunk_chars=0,
        convert=lambda raw, chunk: raw,
        extract_one=extract_one,
    )

    assert llm.chat.call_count == 0  # batch call skipped; extract_one used
    assert items == ["one"]


def test_indexed_blocks_truncate_and_label():
    blocks = llm_utils.build_indexed_chunk_blocks(["abcdef", "xyz"], max_chars=3)
    assert blocks == "Chunk 0:\nabc\n\nChunk 1:\nxyz"


def test_parse_indexed_batch_response_coerces_single_object():
    parsed = llm_utils.parse_indexed_batch_response(json.dumps({"0": {"v": 1}, "1": [{"v": 2}]}), 2)
    assert parsed == {0: [{"v": 1}], 1: [{"v": 2}]}


# ---------------------------------------------------------------------------
# Entity extractor — one batched call, entities mapped to source chunk
# ---------------------------------------------------------------------------


def _entity(name: str):
    return {"name": name, "type": "CONCEPT", "description": "", "confidence": 0.9}


@pytest.mark.asyncio
async def test_entity_extractor_batches_and_maps():
    ext = EntityExtractor.__new__(EntityExtractor)
    c0, c1 = _chunk("c0"), _chunk("c1")
    resp = json.dumps({"0": [_entity("Redis")], "1": [_entity("Postgres")]})
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(resp)))

    entities = await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 1  # ONE batched call
    by_name = {e.name: e for e in entities}
    assert by_name["Redis"].source_chunk_ids == [c0.id]
    assert by_name["Postgres"].source_chunk_ids == [c1.id]
    _, kwargs = ext.llm.chat.call_args
    assert kwargs.get("llm_type") == "extraction"
    assert kwargs.get("structured_output") is True


@pytest.mark.asyncio
async def test_entity_extractor_malformed_batch_falls_back(monkeypatch):
    ext = EntityExtractor.__new__(EntityExtractor)
    c0, c1 = _chunk("c0"), _chunk("c1")
    bad = _resp("not json")  # batched -> raise
    per_chunk = _resp(json.dumps([_entity("X")]))
    ext.llm = types.SimpleNamespace(chat=AsyncMock(side_effect=[bad, per_chunk, per_chunk]))

    entities = await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 3  # 1 failed batch + 2 per-chunk fallback
    assert {e.source_chunk_ids[0] for e in entities} == {c0.id, c1.id}


@pytest.mark.asyncio
async def test_entity_extractor_flag_off_uses_per_chunk_loop(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config, "cognifier_multichunk_batching", False)
    ext = EntityExtractor.__new__(EntityExtractor)
    c0, c1 = _chunk("c0"), _chunk("c1")
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(json.dumps([_entity("A")]))))

    await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 2  # one call per chunk (legacy path)


# ---------------------------------------------------------------------------
# Event extractor — one batched call, events mapped to source chunk
# ---------------------------------------------------------------------------


def _event(name: str):
    return {
        "name": name,
        "description": "",
        "temporal_expression": "2024-01-15",
        "temporal_type": "point",
        "event_type": "occurrence",
        "participants": [],
        "confidence": 0.9,
    }


@pytest.mark.asyncio
async def test_event_extractor_batches_and_maps():
    ext = EventExtractor.__new__(EventExtractor)
    c0, c1 = _chunk("c0"), _chunk("c1")
    resp = json.dumps({"0": [_event("Launch")], "1": [_event("Release")]})
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(resp)))

    events = await ext._process_batch([c0, c1], {}, _ctx())

    assert ext.llm.chat.call_count == 1
    by_name = {e.name: e for e in events}
    assert by_name["Launch"].source_chunk_ids == [c0.id]
    assert by_name["Release"].source_chunk_ids == [c1.id]
    _, kwargs = ext.llm.chat.call_args
    assert kwargs.get("llm_type") == "extraction"
    assert kwargs.get("structured_output") is True


# ---------------------------------------------------------------------------
# Causal extractor — one batched call, edges mapped to source chunk
# ---------------------------------------------------------------------------


def _edge(src: str, tgt: str):
    return {
        "source_name": src,
        "target_name": tgt,
        "effect_type": "REDUCES",
        "condition": "",
        "evidence_text": f"{src} reduces {tgt}.",
        "confidence": 0.95,
    }


@pytest.mark.asyncio
async def test_causal_extractor_batches_and_maps():
    ext = CausalRelationshipExtractor.__new__(CausalRelationshipExtractor)
    ext.min_confidence = 0.7
    c0, c1 = _chunk("c0"), _chunk("c1")
    resp = json.dumps({"0": [_edge("ttl", "latency")], "1": [_edge("cache", "load")]})
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(resp)))

    edges = await ext._process_batch([c0, c1], _ctx())

    assert ext.llm.chat.call_count == 1
    chunk_ids = {cid for e in edges for cid in e.source_chunk_ids}
    assert chunk_ids == {c0.id, c1.id}
    _, kwargs = ext.llm.chat.call_args
    assert kwargs.get("llm_type") == "extraction"
    assert kwargs.get("structured_output") is True


# ---------------------------------------------------------------------------
# #11012 — partial/truncated batch response must not silently drop chunks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_helper_partial_response_recovers_missing_chunks_per_chunk():
    """A truncated batch (index 1 absent) recovers chunk 1 via per-chunk fallback,
    instead of silently yielding zero items for it (#11012)."""
    c0, c1 = _chunk("c0"), _chunk("c1")
    resp = json.dumps({"0": [{"v": "A"}]})  # "1" missing — response truncated
    llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(resp)))
    fallback: list = []

    async def extract_one(chunk):
        fallback.append(chunk.id)
        return [(chunk.id, "recovered")]

    items = await llm_utils.batched_chunk_extract(
        [c0, c1],
        llm=llm,
        batch_prompt_template="{chunks}",
        llm_type="extraction",
        max_chunk_chars=0,
        convert=lambda raw, chunk: [(chunk.id, r["v"]) for r in raw],
        extract_one=extract_one,
    )

    assert llm.chat.call_count == 1  # still one batched call
    assert fallback == [c1.id]  # ONLY the missing chunk fell back
    assert items == [(c0.id, "A"), (c1.id, "recovered")]  # no chunk dropped


@pytest.mark.asyncio
async def test_helper_present_but_empty_index_does_not_fall_back():
    """An index present with an explicit empty list is a real 'no items' answer —
    it must NOT trigger per-chunk fallback (#11012)."""
    c0, c1 = _chunk("c0"), _chunk("c1")
    resp = json.dumps({"0": [{"v": "A"}], "1": []})  # "1" present, explicitly empty
    llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(resp)))

    async def extract_one(chunk):  # pragma: no cover - must not run
        raise AssertionError("present-but-empty index must not fall back")

    items = await llm_utils.batched_chunk_extract(
        [c0, c1],
        llm=llm,
        batch_prompt_template="{chunks}",
        llm_type="extraction",
        max_chunk_chars=0,
        convert=lambda raw, chunk: [(chunk.id, r["v"]) for r in raw],
        extract_one=extract_one,
    )

    assert items == [(c0.id, "A")]  # chunk 1 legitimately contributed nothing


@pytest.mark.asyncio
async def test_helper_scales_max_tokens_with_batch_size():
    """The batched call raises max_tokens with the batch size (capped) so packing
    K chunks doesn't truncate the response (#11012)."""
    chunks = [_chunk(str(i)) for i in range(3)]
    resp = json.dumps({str(i): [] for i in range(3)})
    llm = types.SimpleNamespace(chat=AsyncMock(return_value=_resp(resp)))

    await llm_utils.batched_chunk_extract(
        chunks,
        llm=llm,
        batch_prompt_template="{chunks}",
        llm_type="extraction",
        max_chunk_chars=0,
        convert=lambda raw, chunk: [],
        extract_one=AsyncMock(return_value=[]),
    )

    _, kwargs = llm.chat.call_args
    assert kwargs.get("max_tokens") == llm_utils._BATCH_MAX_TOKENS_PER_CHUNK * 3
