# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""add_document chunks (#17830) and keeps what it stored when the budget runs out (#17986)."""

import asyncio
import re
from unittest.mock import PropertyMock, patch

import pytest

import knowledge.document_ingest as ingest_module
from autobot_shared.doc_chunking import estimate_tokens
from autobot_shared.status_enums import OperationOutcome
from knowledge.document_ingest import chunk_fact_id, read_ingest_record
from knowledge.documents import DocumentsMixin
from utils.knowledge_base_timeouts import kb_timeouts

CHUNK_TOKENS = 100


class _FakeRedis:
    def __init__(self):
        self.hashes, self.facts = {}, set()

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})

    def expire(self, key, ttl):
        return True

    def delete(self, key):
        self.hashes.pop(key, None)

    def exists(self, key):
        return key in self.facts


class _FakeKB(DocumentsMixin):
    """A DocumentsMixin host whose storing a chunk costs ``delay`` seconds."""

    def __init__(self, delay=0.0):
        self.delay, self.redis_client = delay, _FakeRedis()
        self.stored, self.revectorized, self.deleted = {}, [], []

    async def _add_document_internal(self, content, metadata=None, doc_id=None):
        await asyncio.sleep(self.delay)
        self.stored[doc_id] = (content, dict(metadata or {}))
        self.redis_client.facts.add("fact:%s" % doc_id)
        return {"status": "success", "fact_id": doc_id}

    async def delete_fact(self, fact_id):
        self.stored.pop(fact_id, None)
        self.redis_client.facts.discard("fact:%s" % fact_id)
        self.deleted.append(fact_id)
        return {"status": "success"}

    async def vectorize_existing_fact(self, fact_id):
        self.revectorized.append(fact_id)
        return {"status": "success", "fact_id": fact_id}


@pytest.fixture(autouse=True)
def _small_chunks():
    with patch.object(ingest_module, "KB_CHUNK_MAX_TOKENS", CHUNK_TOKENS):
        yield


def _budget(seconds):
    return patch.object(type(kb_timeouts), "document_add", new_callable=PropertyMock, return_value=seconds)


def _transcript(sentences=400):
    """One unbroken block, no paragraph breaks -- the shape of a meeting transcript."""
    return " ".join("Speaker said point number %d about the roadmap." % i for i in range(sentences))


def _pdf_text(pages=12):
    return "\n\n".join(
        "\n\n".join("Page %d paragraph %d. " % (p, q) + "text " * 60 for q in range(3)) for p in range(pages)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [_transcript(), _pdf_text()], ids=["transcript", "pdf-text"])
async def test_long_document_is_stored_as_several_chunks_sharing_a_document_id(text):
    kb = _FakeKB()
    result = await kb.add_document(text, {"title": "t"}, doc_id="doc-1")
    assert result["status"] == "success"
    assert len(kb.stored) > 1 and result["chunks_stored"] == result["chunks_total"] == len(kb.stored)
    assert chunk_fact_id("doc-1", 0) in kb.stored and result["fact_id"] == "doc-1"
    for idx, (chunk, meta) in enumerate(kb.stored.values()):
        assert estimate_tokens(chunk) <= CHUNK_TOKENS * 1.2
        assert meta["document_id"] == "doc-1" and meta["chunk_index"] == idx and meta["chunk_count"] == len(kb.stored)


@pytest.mark.asyncio
async def test_short_document_is_stored_whole_and_unchanged():
    kb = _FakeKB()
    result = await kb.add_document("short note", {"title": "t"}, doc_id="d")
    assert result == {"status": "success", "fact_id": "d"}
    assert kb.stored["d"] == ("short note", {"title": "t"})


@pytest.mark.asyncio
async def test_budget_overrun_keeps_stored_chunks_and_reports_partial():
    kb = _FakeKB(delay=0.03)
    with _budget(0.1):
        result = await kb.add_document(_transcript(), doc_id="doc-2")
    assert result["status"] == OperationOutcome.PARTIAL.value
    assert 0 < result["chunks_stored"] < result["chunks_total"] and len(kb.stored) == result["chunks_stored"]
    record = await read_ingest_record(kb, "doc-2")
    assert record["status"] == "partial" and int(record["chunks_stored"]) == len(kb.stored)


@pytest.mark.asyncio
async def test_partial_complete_and_failed_are_three_distinct_outcomes():
    complete = await _FakeKB().add_document(_transcript(), doc_id="a")
    with _budget(0.1):
        partial = await _FakeKB(delay=0.03).add_document(_transcript(), doc_id="b")
    with _budget(0.001):
        failed = await _FakeKB(delay=0.05).add_document(_transcript(), doc_id="c")
    assert [r["status"] for r in (complete, partial, failed)] == ["success", "partial", "timeout"]
    assert failed["chunks_stored"] == 0


@pytest.mark.asyncio
async def test_retry_resumes_after_the_last_stored_chunk_instead_of_restarting():
    kb, text = _FakeKB(delay=0.03), _transcript()
    with _budget(0.1):
        first = await kb.add_document(text, doc_id="doc-3")
    done = set(kb.stored)
    kb.delay, stores = 0.0, []
    original = kb._add_document_internal

    async def spy(content, metadata=None, doc_id=None):
        stores.append(doc_id)
        return await original(content, metadata, doc_id)

    kb._add_document_internal = spy
    with _budget(5.0):
        second = await kb.add_document(text, doc_id="doc-3")
    assert second["status"] == "success" and second["chunks_stored"] == first["chunks_total"]
    assert not done & set(stores) - {chunk_fact_id("doc-3", len(done))}, "already-stored chunks were stored again"
    assert len(kb.stored) == first["chunks_total"]


@pytest.mark.asyncio
async def test_changed_content_under_the_same_id_restarts_instead_of_resuming():
    kb = _FakeKB(delay=0.03)
    with _budget(0.1):
        await kb.add_document(_transcript(), doc_id="doc-4")
    kb.delay = 0.0
    result = await kb.add_document(_transcript(300), doc_id="doc-4")
    assert result["status"] == "success" and result["chunks_stored"] == result["chunks_total"]


@pytest.mark.asyncio
async def test_shorter_content_under_the_same_id_removes_the_orphaned_chunks():
    kb = _FakeKB()
    first = await kb.add_document(_transcript(400), doc_id="doc-5")
    assert first["chunks_total"] > 3
    second = await kb.add_document(_transcript(150), doc_id="doc-5")
    assert second["chunks_total"] < first["chunks_total"] and second["status"] == "success"
    assert set(kb.stored) == {chunk_fact_id("doc-5", i) for i in range(second["chunks_total"])}
    assert all(m["chunk_count"] == second["chunks_total"] for _c, m in kb.stored.values())


@pytest.mark.asyncio
async def test_content_shrinking_to_one_chunk_removes_every_old_chunk_and_the_record():
    kb = _FakeKB()
    await kb.add_document(_transcript(400), doc_id="doc-6")
    result = await kb.add_document("now short", doc_id="doc-6")
    assert result["status"] == "success" and set(kb.stored) == {"doc-6"}
    assert await read_ingest_record(kb, "doc-6") == {}


@pytest.mark.asyncio
async def test_a_chunk_still_over_budget_is_hard_capped():
    kb = _FakeKB()
    blob = "A" * (CHUNK_TOKENS * 4 * 5)  # one 'token' with no whitespace, five budgets long
    result = await kb.add_document("intro. " + blob + " outro.", doc_id="doc-7")
    assert result["chunks_total"] >= 5
    assert all(estimate_tokens(c) <= CHUNK_TOKENS for c, _m in kb.stored.values())
    assert "".join(c.replace(" ", "") for c, _m in kb.stored.values()).count("A") == len(blob)


def _paged_text():
    """Four 'pages' of three paragraphs, with spans in the shape _page_provenance_metadata records."""
    spans, text = [], ""
    for page in range(1, 5):
        start = len(text)
        text += "\n\n".join("Page %d para %d. " % (page, q) + "word " * 70 for q in range(3))
        spans.append({"page": page, "start": start, "end": len(text)})
        text += "\n\n"
    return text.rstrip(), spans


@pytest.mark.asyncio
async def test_each_chunk_carries_only_the_pages_it_covers_with_rebased_offsets():
    text, spans = _paged_text()
    kb = _FakeKB()
    meta = {"page_count": 4, "page_spans": spans, "pages_with_text": [1, 2, 3, 4]}
    result = await kb.add_document(text, meta, doc_id="doc-8")
    assert result["chunks_total"] > 2
    for chunk, m in kb.stored.values():
        covered = {int(x) for x in re.findall(r"Page (\d) para", chunk)}
        assert {s["page"] for s in m["page_spans"]} == covered == set(m["pages_with_text"])
        for span in m["page_spans"]:
            assert 0 <= span["start"] < span["end"] <= len(chunk)
        assert m["page_spans"][-1]["end"] == len(chunk.rstrip())
