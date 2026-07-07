# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for RelationshipExtractor NLP-mode additions.

Issue #2026: Dual-mode relationship extraction — LLM + NLP.
"""

import contextlib
import sys
from types import ModuleType
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


@contextlib.contextmanager
def _stubbed_import_modules():
    """Install lightweight ``sys.modules`` stubs only while importing cognifiers.

    ``llm_shared`` and ``autobot_shared.redis_client`` pull heavy runtime deps at
    import time, so they are stubbed before the cognifier module loads.  These stubs
    previously lived at module top level and leaked process-wide — the leaked
    ``autobot_shared.redis_client`` stub lacked ``get_async_redis_client`` and broke
    ``services/chat_knowledge_service_test.py`` when co-collected (#10879).  Scope them
    to the import window and restore whatever the parent conftest installed on exit.

    Only the ``autobot_shared.redis_client`` submodule is stubbed — never the
    ``autobot_shared`` package itself — so sibling imports like
    ``autobot_shared.logging_manager`` keep resolving through the real package.
    """
    saved = {name: sys.modules.get(name) for name in ("llm_shared", "autobot_shared.redis_client")}

    _mock_llm = ModuleType("llm_shared")
    _mock_llm.LLMInterface = MagicMock
    sys.modules["llm_shared"] = _mock_llm

    _mock_redis_mod = ModuleType("autobot_shared.redis_client")
    _mock_redis_mod.get_redis_client = MagicMock()

    async def _get_async_redis_client_stub(*_a, **_k):
        return None

    _mock_redis_mod.get_async_redis_client = _get_async_redis_client_stub
    sys.modules["autobot_shared.redis_client"] = _mock_redis_mod

    try:
        yield
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


with _stubbed_import_modules():
    from knowledge.pipeline.cognifiers.relationship_extractor import (
        NLP_KEYWORD_PATTERNS,
        RelationshipExtractor,
    )
    from knowledge.pipeline.models.chunk import ProcessedChunk
    from knowledge.pipeline.models.entity import Entity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entity(name: str, doc_id=None) -> Entity:
    """Build a minimal Entity with canonical_name = name.lower()."""
    return Entity(
        name=name,
        canonical_name=name.lower(),
        entity_type="TECHNOLOGY",
        source_document_id=doc_id or uuid4(),
    )


def _chunk(content: str) -> ProcessedChunk:
    """Build a minimal ProcessedChunk."""
    return ProcessedChunk(content=content, document_id=uuid4(), chunk_index=0)


@pytest.fixture
def extractor() -> RelationshipExtractor:
    return RelationshipExtractor(mode="nlp")


# ---------------------------------------------------------------------------
# Test: co-occurrence creates a RELATES_TO relationship
# ---------------------------------------------------------------------------


class TestCoOccurrenceCreatesRelationship:
    """Issue #2026: two entities in same chunk yield CO_OCCURS (RELATES_TO)."""

    def test_co_occurrence_creates_relationship(self, extractor):
        chunk = _chunk("FastAPI and Redis are used together in this service.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "RELATES_TO"
        assert rels[0].confidence == 0.6

    def test_single_entity_produces_no_relationship(self, extractor):
        chunk = _chunk("FastAPI is a web framework.")
        entities = [_entity("FastAPI")]

        rels = extractor._nlp_extract([chunk], entities)

        assert rels == []

    def test_entity_absent_from_chunk_excluded(self, extractor):
        chunk = _chunk("FastAPI is fast.")
        entities = [_entity("FastAPI"), _entity("Celery")]

        rels = extractor._nlp_extract([chunk], entities)

        # "celery" not in chunk text -> only FastAPI present -> no pair
        assert rels == []


# ---------------------------------------------------------------------------
# Test: keyword pattern creates typed relationship
# ---------------------------------------------------------------------------


class TestKeywordPatternCreatesTypedRelationship:
    """Issue #2026: keyword in chunk text overrides default RELATES_TO type."""

    def test_import_keyword_creates_uses(self, extractor):
        chunk = _chunk("FastAPI import Redis for caching.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "USES"

    def test_extend_keyword_creates_extends(self, extractor):
        chunk = _chunk("AuthService extend BaseService configuration.")
        entities = [_entity("AuthService"), _entity("BaseService")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "EXTENDS"

    def test_depend_keyword_creates_depends_on(self, extractor):
        chunk = _chunk("Celery depend on Redis broker.")
        entities = [_entity("Celery"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "DEPENDS_ON"

    def test_trigger_keyword_creates_triggers(self, extractor):
        chunk = _chunk("Workflow trigger Celery task execution.")
        entities = [_entity("Workflow"), _entity("Celery")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "TRIGGERS"

    def test_call_keyword_creates_triggers(self, extractor):
        chunk = _chunk("FastAPI call Redis directly.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert rels[0].relationship_type == "TRIGGERS"

    def test_all_patterns_map_to_valid_relation_types(self):
        """Ensure every NLP_KEYWORD_PATTERNS value is a valid RelationType."""
        from knowledge.pipeline.models.relationship import RelationType

        valid = set(RelationType.__args__)
        for keyword, rel_type in NLP_KEYWORD_PATTERNS.items():
            assert rel_type in valid, f"Keyword '{keyword}' maps to '{rel_type}' which is not a valid RelationType"


# ---------------------------------------------------------------------------
# Test: auto mode selects NLP for large input
# ---------------------------------------------------------------------------


class TestAutoSelectsNlpForLargeInput:
    """Issue #2052: auto mode switches to NLP when the chunk count exceeds the threshold.

    ``nlp_threshold`` is a *chunk count*, not a character count — RelationshipExtractor
    uses the same unit as EntityExtractor so both extractors pick the same mode for the
    same input (see ``RelationshipExtractor._select_mode``).  These cases were originally
    written for the superseded #2026 char-count semantics; #10880 realigns them with the
    chunk-count contract the code actually implements.
    """

    def test_auto_selects_nlp_above_threshold(self):
        extractor = RelationshipExtractor(mode="auto", nlp_threshold=5)
        chunks = [_chunk(f"chunk {i}") for i in range(10)]  # 10 chunks > threshold 5

        mode = extractor._select_mode(chunks)

        assert mode == "nlp"

    def test_auto_selects_llm_below_threshold(self):
        extractor = RelationshipExtractor(mode="auto", nlp_threshold=500)
        chunks = [_chunk("Short chunk.")]  # 1 chunk < threshold 500

        mode = extractor._select_mode(chunks)

        assert mode == "llm"

    def test_auto_selects_nlp_multi_chunk_cumulative(self):
        extractor = RelationshipExtractor(mode="auto", nlp_threshold=2)
        chunks = [_chunk("A"), _chunk("B"), _chunk("C")]  # 3 chunks > threshold 2

        mode = extractor._select_mode(chunks)

        assert mode == "nlp"

    def test_explicit_nlp_mode_bypasses_select(self):
        extractor = RelationshipExtractor(mode="nlp", nlp_threshold=500)
        chunk = _chunk("Tiny.")

        # _select_mode would return "llm" for a single chunk (1 < 500), but the
        # explicit mode is what process() honours regardless of _select_mode.
        assert extractor.mode == "nlp"
        assert extractor._select_mode([chunk]) == "llm"


# ---------------------------------------------------------------------------
# Test: deduplication by entity pair
# ---------------------------------------------------------------------------


class TestDeduplicationByEntityPair:
    """Issue #2026: same (src, tgt, type) triple across chunks yields one rel."""

    def test_different_types_not_deduplicated(self, extractor):
        entities = [_entity("FastAPI"), _entity("Redis")]
        # chunk1: no keyword -> RELATES_TO; chunk2: "import" -> USES
        chunk1 = _chunk("FastAPI and Redis are here.")
        chunk2 = _chunk("FastAPI import Redis here.")

        rels = extractor._nlp_extract([chunk1, chunk2], entities)

        types = {r.relationship_type for r in rels}
        assert len(rels) == 2
        assert "RELATES_TO" in types
        assert "USES" in types

    def test_identical_type_across_chunks_deduplicated(self, extractor):
        entities = [_entity("FastAPI"), _entity("Redis")]
        chunk1 = _chunk("FastAPI and Redis co-occur here.")
        chunk2 = _chunk("FastAPI and Redis co-occur here.")

        rels = extractor._nlp_extract([chunk1, chunk2], entities)

        # Same type (RELATES_TO) -> deduplicated to 1
        assert len(rels) == 1

    def test_three_entities_produce_three_pairs(self, extractor):
        entities = [_entity("A"), _entity("B"), _entity("C")]
        chunk = _chunk("A B C are all mentioned here.")

        rels = extractor._nlp_extract([chunk], entities)

        # combinations(3, 2) = 3 pairs
        assert len(rels) == 3

    def test_source_chunk_id_recorded(self, extractor):
        chunk = _chunk("FastAPI and Redis co-occur.")
        entities = [_entity("FastAPI"), _entity("Redis")]

        rels = extractor._nlp_extract([chunk], entities)

        assert len(rels) == 1
        assert chunk.id in rels[0].source_chunk_ids


# ---------------------------------------------------------------------------
# #11044 — multi-chunk batching (entity-conditioned via aux_of)
# ---------------------------------------------------------------------------


def _rel(src: str, tgt: str) -> dict:
    return {
        "source": src,
        "target": tgt,
        "type": "USES",
        "description": "",
        "bidirectional": False,
        "confidence": 0.9,
    }


def _llm_extractor():
    ext = RelationshipExtractor.__new__(RelationshipExtractor)
    ext.batch_size = 5
    ext.min_confidence = 0.0
    return ext


@pytest.mark.asyncio
async def test_batched_relationship_extraction_one_call(monkeypatch):
    import json
    import types
    from unittest.mock import AsyncMock

    import knowledge.pipeline.cognifiers.relationship_extractor as rex

    monkeypatch.setattr(rex.config, "cognifier_multichunk_batching", True)
    c0, c1 = _chunk("A uses B"), _chunk("C uses D")
    ents = [_entity("A"), _entity("B"), _entity("C"), _entity("D")]
    emap = {e.name.lower(): e for e in ents}

    resp = json.dumps({"0": [_rel("A", "B")], "1": [_rel("C", "D")]})
    ext = _llm_extractor()
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content=resp)))

    rels = await ext._process_batch([c0, c1], ents, emap)

    assert ext.llm.chat.call_count == 1  # ONE batched call, not one per chunk
    assert len(rels) == 2
    # the batched prompt folds each chunk's entity list in via aux_of
    _, kwargs = ext.llm.chat.call_args
    sent = ext.llm.chat.call_args[0][0][0]["content"]
    assert "Entities:" in sent and "Chunk 0:" in sent and "Chunk 1:" in sent


@pytest.mark.asyncio
async def test_flag_off_uses_per_chunk(monkeypatch):
    import json
    import types
    from unittest.mock import AsyncMock

    import knowledge.pipeline.cognifiers.relationship_extractor as rex

    monkeypatch.setattr(rex.config, "cognifier_multichunk_batching", False)
    c0, c1 = _chunk("A uses B"), _chunk("C uses D")
    ents = [_entity("A"), _entity("B")]
    emap = {e.name.lower(): e for e in ents}

    ext = _llm_extractor()
    ext.llm = types.SimpleNamespace(
        chat=AsyncMock(
            side_effect=[
                types.SimpleNamespace(content=json.dumps([_rel("A", "B")])),
                types.SimpleNamespace(content=json.dumps([])),
            ]
        )
    )
    await ext._process_batch([c0, c1], ents, emap)
    assert ext.llm.chat.call_count == 2  # legacy per-chunk path


def test_chunk_scoped_entity_map_excludes_other_chunk_entities():
    """#11070 audit: batched conversion is scoped to the chunk's own entities so a
    relationship can't resolve an entity that belongs only to another chunk."""
    ext = RelationshipExtractor.__new__(RelationshipExtractor)
    c0 = _chunk("chunk zero")
    e_in = _entity("Alpha")
    e_in.source_chunk_ids = [c0.id]
    e_other = _entity("Beta")
    e_other.source_chunk_ids = [uuid4()]  # belongs to a different chunk

    scoped = ext._chunk_scoped_entity_map([e_in, e_other], c0)
    assert "alpha" in scoped
    assert "beta" not in scoped  # other-chunk entity excluded
