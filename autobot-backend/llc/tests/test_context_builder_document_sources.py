# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/llc/tests/test_context_builder_document_sources.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLC leg of #17527: a chunk's document origin is surfaced, not only its tenant.

`_format_inherited_context` returned `{chunks, sources}` where `sources` is built
from `source_company_id` — the company a chunk was inherited from. #17527 asks for
a document's source to be identifiable, so a key named `sources` answering tenancy
is a provenance-shaped name over a different question: a caller asking where a
chunk came from got a company id and no signal it was not the answer.

The tenancy list is deliberately unchanged. Some caller relies on it, and removing
it to make room for the other meaning would trade one wrong answer for a break.
"""

from __future__ import annotations

import pytest

from llc.kb.context_builder import HeartbeatContextBuilder

TRANSCRIPT_META = {"source_type": "transcript", "source": "recording:41", "recording_id": 41}
UPLOAD_META = {"type": "file", "filename": "spec-v2.pdf", "source": "spec-v2.pdf"}


@pytest.fixture
def builder() -> HeartbeatContextBuilder:
    """The services are stored and unused by the normalisation under test.

    Constructing real ones would exercise the constructor rather than the method,
    and the method reads no instance state.
    """
    return HeartbeatContextBuilder(rag_assembler=None, goal_service=None, work_item_service=None)


def test_document_origin_is_surfaced_alongside_the_tenancy_list(builder):
    results = [
        {"id": "f1", "content": "a", "source_company_id": "co-1", "metadata": TRANSCRIPT_META},
        {"id": "f2", "content": "b", "source_company_id": "co-2", "metadata": UPLOAD_META},
    ]

    context = builder._format_inherited_context(results)

    # Unchanged: still the companies, because callers read this.
    assert sorted(context["sources"]) == ["co-1", "co-2"]
    # Added: where the documents came from.
    assert context["document_sources"] == ["recording:41", "file:spec-v2.pdf"]


def test_the_two_lists_answer_different_questions(builder):
    """One company, two documents — the count alone shows they are not the same key."""
    results = [
        {"id": "f1", "content": "a", "source_company_id": "co-1", "metadata": TRANSCRIPT_META},
        {"id": "f2", "content": "b", "source_company_id": "co-1", "metadata": UPLOAD_META},
    ]

    context = builder._format_inherited_context(results)

    assert context["sources"] == ["co-1"]
    assert len(context["document_sources"]) == 2


def test_a_chunk_with_no_recognisable_provenance_adds_no_entry(builder):
    """Rather than a placeholder, which is the defect being fixed."""
    results = [{"id": "f1", "content": "a", "source_company_id": "co-1", "metadata": {}}]

    context = builder._format_inherited_context(results)

    assert context["sources"] == ["co-1"]
    assert context["document_sources"] == []


def test_no_results_still_carries_the_key(builder):
    """A caller must not have to branch on whether the key exists."""
    context = builder._format_inherited_context([])

    assert context == {"chunks": [], "sources": [], "document_sources": []}


def test_the_chunk_still_carries_its_raw_metadata(builder):
    """The accessor is a convenience, not a replacement.

    A caller that knows a leg's dialect better than the accessor does must still be
    able to read the metadata itself.
    """
    results = [{"id": "f1", "content": "a", "source_company_id": "co-1", "metadata": TRANSCRIPT_META}]

    chunk = builder._format_inherited_context(results)["chunks"][0]

    assert chunk["metadata"]["recording_id"] == 41
    assert chunk["source_company_id"] == "co-1"
