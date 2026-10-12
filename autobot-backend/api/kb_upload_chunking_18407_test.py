# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Upload, /facts and /url store through add_document, so long input is chunked (#18407)."""

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import knowledge.document_ingest as ingest_module
from api.knowledge_upload_redaction_test import _SECRET
from knowledge.documents import DocumentsMixin

LONG_TEXT = "\n\n".join("Section %d. " % i + "lorem ipsum dolor sit amet " * 40 for i in range(30))


class _KB(DocumentsMixin):
    """Every path ends in ``store_fact``, so the fact count is the same measure before and after (#18407)."""

    def __init__(self):
        self.redis_client = MagicMock(hgetall=MagicMock(return_value={}))
        self.stored = {}

    async def store_fact(self, content, metadata=None, fact_id=None):
        fact_id = fact_id or "single-fact"
        self.stored[fact_id] = (content, dict(metadata or {}))
        return {"status": "success", "fact_id": fact_id}

    async def _add_document_internal(self, content, metadata=None, doc_id=None):
        return await self.store_fact(content, metadata, doc_id)


@pytest.fixture(autouse=True)
def _small_chunks():
    with patch.object(ingest_module, "KB_CHUNK_MAX_TOKENS", 200):
        yield


def _patched(mod, kb):
    return (
        patch.object(mod, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch.object(mod, "get_auth_middleware", MagicMock()),
        patch.object(mod, "audit_record", MagicMock()),
    )


def _assert_chunked_under_one_document(kb, response_id):
    assert len(kb.stored) > 1, "a long input was stored as a single fact"
    assert {m["document_id"] for _c, m in kb.stored.values()} == {response_id}
    assert response_id in kb.stored


@pytest.mark.asyncio
async def test_a_long_upload_is_stored_as_several_chunks_under_the_returned_document_id():
    from api import knowledge as mod

    upload = SimpleNamespace(filename="notes.txt", read=AsyncMock(return_value=LONG_TEXT.encode("utf-8")))
    req = MagicMock()
    req.form = AsyncMock(return_value={"file": upload, "title": "Notes"})
    kb = _KB()
    p1, p2, p3 = _patched(mod, kb)
    with p1, p2, p3:
        response = await mod.upload_file_to_knowledge(admin_check=True, req=req)
    _assert_chunked_under_one_document(kb, response.document_id)


@pytest.mark.asyncio
async def test_pdf_chunks_name_the_right_pages_even_when_redaction_changes_the_length():
    """The secret is redacted to a shorter placeholder on page 1; spans taken before cleaning would drift."""
    from api import knowledge as mod
    from media.document.extraction import ExtractedDocument, PageText, render_plain

    secret = _SECRET
    raw = [
        PageText(
            n,
            "Page %d marker. " % n
            + ("token %s " % secret if n == 1 else "")
            + " ".join("w%d_%d" % (n, i) for i in range(400)),
        )
        for n in range(1, 7)
    ]
    extracted = ExtractedDocument(format="pdf", text="", pages=tuple(raw), page_count=6)
    upload = SimpleNamespace(filename="doc.pdf", read=AsyncMock(return_value=b"x"))
    req = MagicMock()
    req.form = AsyncMock(return_value={"file": upload, "title": "Doc"})
    kb = _KB()
    p1, p2, p3 = _patched(mod, kb)
    extraction = AsyncMock(return_value=(render_plain(raw)[0], extracted))
    with (
        p1,
        p2,
        p3,
        patch.object(mod, "extract_within_deadline", extraction),
        patch.object(mod, "_has_usable_content", return_value=True),
    ):
        response = await mod.upload_file_to_knowledge(admin_check=True, req=req)
    _assert_chunked_under_one_document(kb, response.document_id)
    assert all(secret not in chunk for chunk, _m in kb.stored.values()), "a secret reached the KB"
    marker = re.compile(r"Page (\d) marker")
    for chunk, meta in kb.stored.values():
        spans = meta["page_spans"]
        for span in spans:
            text = chunk[span["start"] : span["end"]]
            assert 0 <= span["start"] < span["end"] <= len(chunk)
            assert not (
                marker.search(text) and int(marker.search(text).group(1)) != span["page"]
            ), "span names the wrong page"
            assert {int(n) for n in re.findall(r"w(\d)_\d+", text)} <= {span["page"]}
        assert {s["page"] for s in spans} == {int(n) for n in re.findall(r"(?:Page |\bw)(\d)(?: marker|_\d+)", chunk)}


@pytest.mark.asyncio
async def test_add_fact_and_url_content_are_chunked_through_the_same_helper():
    from api import knowledge as mod

    for metadata in ({"source": "s"}, {"type": "url", "source": "https://example.invalid"}):
        kb = _KB()
        doc_id = await mod._store_fact_in_kb(kb, LONG_TEXT, dict(metadata))
        _assert_chunked_under_one_document(kb, doc_id)
