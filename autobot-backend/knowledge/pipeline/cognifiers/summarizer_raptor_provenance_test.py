# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A RAPTOR node must cite the chunks it summarises (#14968).

``_summarize_groups`` passed ``source_chunk_ids=[]`` literally, so every node
above L0 was uncitable **by construction** -- not sometimes empty, never
populated. The ids were already in scope at the call site, in the ``groups``
dict the summary is built from, and were thrown away.

These assert the invariant the issue asks for -- that the ids are present and
correct, and that the tree is walkable upward -- rather than that the call was
made. A test that only checked ``_summarize_text`` received *some*
``source_chunk_ids`` argument would have passed against the literal ``[]``.

``_summarize_text`` is stubbed because it is an LLM round-trip; the stub builds
a real ``Summary`` from whatever ids it is handed, so the assertions run against
the aggregation under test rather than against the stub's own opinion.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from knowledge.pipeline.cognifiers.summarizer import HierarchicalSummarizer
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.summary import Summary

_DOC = uuid4()


def _chunk(text: str, index: int) -> ProcessedChunk:
    return ProcessedChunk(content=text, document_id=_DOC, chunk_index=index)


def _summarizer() -> HierarchicalSummarizer:
    summarizer = HierarchicalSummarizer()

    async def _fake_summarize_text(text, source_chunk_ids, document_id, level, max_words, entity_map):
        return Summary(
            content=f"summary of {len(source_chunk_ids)} chunk(s)",
            level=level,
            source_chunk_ids=list(source_chunk_ids),
            source_document_id=_DOC,
        )

    summarizer._summarize_text = _fake_summarize_text  # type: ignore[assignment]
    return summarizer


@pytest.mark.asyncio
async def test_an_l1_node_cites_exactly_the_chunks_in_its_cluster() -> None:
    chunks = [_chunk("a", 0), _chunk("b", 1), _chunk("c", 2)]
    groups = {0: [chunks[0], chunks[1]], 1: [chunks[2]]}

    summaries = await _summarizer()._summarize_groups(groups, 1, str(_DOC), {})

    assert [s.source_chunk_ids for s in summaries] == [
        [chunks[0].id, chunks[1].id],
        [chunks[2].id],
    ]


@pytest.mark.asyncio
async def test_an_l2_node_cites_the_union_of_its_children() -> None:
    """Provenance accumulates as abstraction rises; it does not reset."""
    leaf_ids = [uuid4() for _ in range(4)]
    children = [
        Summary(content="x", level="section", source_chunk_ids=leaf_ids[:2], source_document_id=_DOC),
        Summary(content="y", level="section", source_chunk_ids=leaf_ids[2:], source_document_id=_DOC),
    ]

    summaries = await _summarizer()._summarize_groups({0: children}, 2, str(_DOC), {})

    assert summaries[0].source_chunk_ids == leaf_ids


@pytest.mark.asyncio
async def test_a_chunk_shared_by_two_children_is_cited_once() -> None:
    """The union is a union -- a repeated id would inflate every level above it."""
    shared, only_a, only_b = uuid4(), uuid4(), uuid4()
    children = [
        Summary(content="x", level="section", source_chunk_ids=[shared, only_a], source_document_id=_DOC),
        Summary(content="y", level="section", source_chunk_ids=[shared, only_b], source_document_id=_DOC),
    ]

    summaries = await _summarizer()._summarize_groups({0: children}, 2, str(_DOC), {})

    assert summaries[0].source_chunk_ids == [shared, only_a, only_b]


@pytest.mark.asyncio
async def test_every_child_summary_points_at_its_parent_and_back() -> None:
    children = [
        Summary(content="x", level="section", source_chunk_ids=[uuid4()], source_document_id=_DOC),
        Summary(content="y", level="section", source_chunk_ids=[uuid4()], source_document_id=_DOC),
    ]
    assert all(c.parent_summary_id is None for c in children), "fixture must start unlinked"

    parent = (await _summarizer()._summarize_groups({0: children}, 2, str(_DOC), {}))[0]

    assert [c.parent_summary_id for c in children] == [parent.id, parent.id]
    assert parent.child_summary_ids == [children[0].id, children[1].id]


@pytest.mark.asyncio
async def test_chunks_are_not_given_parent_links() -> None:
    """L1 members are ProcessedChunks, which carry no parent field to set."""
    chunks = [_chunk("a", 0), _chunk("b", 1)]

    parent = (await _summarizer()._summarize_groups({0: chunks}, 1, str(_DOC), {}))[0]

    assert parent.child_summary_ids == []
    assert all(not hasattr(c, "parent_summary_id") for c in chunks)


def test_provenance_of_prefers_existing_ids_over_the_items_own_id() -> None:
    """The discriminator is 'does it already know its provenance', not its class.

    A Summary's own id is not a chunk id; citing it would make an L2 node point
    at a summary as though it were source material.
    """
    leaf = uuid4()
    summary = Summary(content="s", level="section", source_chunk_ids=[leaf], source_document_id=_DOC)
    chunk = _chunk("c", 0)

    assert HierarchicalSummarizer._provenance_of(summary) == [leaf]
    assert HierarchicalSummarizer._provenance_of(chunk) == [chunk.id]
    assert HierarchicalSummarizer._provenance_of(object()) == []


def test_an_empty_source_chunk_ids_is_not_treated_as_absent() -> None:
    """A Summary citing nothing must contribute nothing, not fall back to its id."""
    empty = Summary(content="s", level="section", source_chunk_ids=[], source_document_id=_DOC)

    assert HierarchicalSummarizer._provenance_of(empty) == []
