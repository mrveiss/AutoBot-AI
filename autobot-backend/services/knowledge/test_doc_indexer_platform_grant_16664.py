# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot's own docs are stamped with the platform-docs grant at write (#16664).

``autobot_docs`` lives outside the facts store, so no ownership row ever covered it. Once RAG
filters every leg by visibility, an unstamped doc reads as private and drops out of every user's
results. The indexer writes the grant into each chunk instead, and the one read decision admits it.
"""

import hashlib

import pytest

from autobot_shared.scoping import Principal
from knowledge.ownership import KnowledgeOwnership
from knowledge.platform_docs import PLATFORM_DOCS_GRANT
from knowledge.search_filters import filter_for_principal, is_non_private

from .test_doc_indexer import _make_service

CHUNK = {
    "content": "How to rotate the deploy key.",
    "section": "Section",
    "subsection": None,
    "file_path": "docs/test.md",
    "doc_type": "documentation",
    "category": "general",
    "title": "Test Doc",
}


def _indexed_metadata() -> dict:
    svc = _make_service()
    assert svc._index_chunk(CHUNK, 0, 1, "docs/test.md", [], 2) is True
    return svc._collection.upsert.call_args.kwargs["metadatas"][0]


def test_the_grant_is_the_system_visibility_and_autobot_access_level():
    assert PLATFORM_DOCS_GRANT == {"visibility": "system", "access_level": "autobot"}


def test_an_indexed_doc_chunk_carries_the_grant():
    metadata = _indexed_metadata()
    assert {k: metadata[k] for k in PLATFORM_DOCS_GRANT} == PLATFORM_DOCS_GRANT
    assert metadata["source"] == "autobot_documentation"


@pytest.mark.asyncio
async def test_a_signed_in_user_may_read_a_stamped_doc_and_an_unstamped_one_reads_as_private():
    manager = KnowledgeOwnership(redis_client=object())
    user = Principal("u1", None, frozenset(), True)
    stamped = {"id": "d1", "metadata": _indexed_metadata()}
    unstamped = {"id": "d2", "metadata": {"source": "autobot_documentation", "file_path": "docs/old.md"}}

    kept = await filter_for_principal([stamped, unstamped], user, manager)

    assert kept == [stamped], "a pre-grant chunk stays hidden until the collection is re-indexed"


def test_the_non_private_scope_reads_a_stamped_doc_only():
    assert is_non_private(_indexed_metadata()) is True
    assert is_non_private({"source": "autobot_documentation"}) is False


def test_a_file_hashed_under_the_old_index_version_is_reindexed_and_a_current_one_is_skipped(tmp_path):
    """Incremental startup indexing must stamp the grant on docs that were indexed without it."""
    from services.knowledge.doc_indexer import _compute_file_hash, _filter_changed_files

    doc = tmp_path / "docs" / "a.md"
    doc.parent.mkdir()
    doc.write_text("# T\n\nbody\n", encoding="utf-8")
    old_hash = hashlib.sha256(doc.read_bytes()).hexdigest()  # what the cache held before the version existed
    files = [(str(doc), 2)]

    changed, _ = _filter_changed_files(files, {"docs/a.md": old_hash}, tmp_path)
    assert changed == files

    current = {"docs/a.md": _compute_file_hash(str(doc))}
    assert current["docs/a.md"] != old_hash
    changed, _ = _filter_changed_files(files, current, tmp_path)
    assert changed == []
