# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chunked, budgeted, resumable document ingest for ``add_document`` (#17830, #17986).

A document is split by ``autobot_shared.doc_chunking`` into chunks that are stored
as ordinary facts sharing a ``document_id``. Chunk 0 keeps the document id as its
fact id (so existing callers' ``fact_id`` stays addressable); later chunks use
``<doc_id>:chunk:<n>``. A per-document record in Redis carries the ingest status:

(``autobot_shared.status_enums.OperationOutcome``; also the result's ``status``)

* ``success``  -- every chunk stored
* ``partial``  -- the time budget ran out after at least one chunk was stored
* ``timeout``  -- the budget ran out with nothing stored

A retry with the same ``doc_id`` and the same content resumes after the last
stored chunk instead of restarting.
"""

import asyncio
import time
from typing import Any, Dict, List

from autobot_shared.content_digest import content_digest
from autobot_shared.doc_chunking import chunk_plain_text
from autobot_shared.env_utils import env_int, env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import OperationOutcome
from knowledge.chunk_provenance import chunk_page_metadata, locate_chunks

logger = get_logger(__name__)

INGEST_RECORD_PREFIX = "kb:ingest:"
# Token budget per stored chunk (~4 chars/token) and how long a per-document ingest record is kept for resume.
KB_CHUNK_MAX_TOKENS = env_int_clamped("AUTOBOT_KB_CHUNK_MAX_TOKENS", 800, 50, 100000)
KB_INGEST_RECORD_TTL_SECONDS = env_int("AUTOBOT_KB_INGEST_RECORD_TTL_SECONDS", 30 * 24 * 3600)


def chunk_fact_id(doc_id: str, index: int) -> str:
    """Deterministic fact id of chunk *index*; chunk 0 is the document id itself."""
    return doc_id if index == 0 else "%s:chunk:%d" % (doc_id, index)


def _chunk_metadata(metadata: Dict[str, Any], doc_id: str, index: int, total: int, offsets) -> Dict[str, Any]:
    chunk_meta = chunk_page_metadata(metadata, offsets)
    chunk_meta.update({"document_id": doc_id, "chunk_index": index, "chunk_count": total})
    return chunk_meta


def _record_key(doc_id: str) -> str:
    return INGEST_RECORD_PREFIX + doc_id


async def read_ingest_record(kb, doc_id: str) -> Dict[str, str]:
    """Return the ingest record for *doc_id* (empty dict if none)."""
    raw = await asyncio.to_thread(kb.redis_client.hgetall, _record_key(doc_id))
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in (raw or {}).items()
    }


async def _write_record(
    kb, doc_id: str, status: OperationOutcome, stored: int, total: int, extra: Dict[str, Any]
) -> None:
    key = _record_key(doc_id)
    mapping = {"status": status.value, "chunks_stored": stored, "chunks_total": total, "updated_at": int(time.time())}
    mapping.update(extra)
    await asyncio.to_thread(kb.redis_client.hset, key, mapping=mapping)
    await asyncio.to_thread(kb.redis_client.expire, key, KB_INGEST_RECORD_TTL_SECONDS)


async def _drop_orphans(kb, doc_id: str, new_total: int, record: Dict[str, str]) -> None:
    """Delete this document's own chunks past the new count when shorter content replaces longer.

    These are derived chunks of the same document id being replaced, not user data: left behind they
    would keep serving text the document no longer contains.
    """
    for index in range(max(new_total, 1), int(record.get("chunks_total", 0))):
        await kb.delete_fact(chunk_fact_id(doc_id, index))
    if new_total == 1 and record:
        await asyncio.to_thread(kb.redis_client.delete, _record_key(doc_id))


async def _store_chunk(kb, text: str, metadata: Dict[str, Any], fact_id: str, interrupted: bool) -> Dict[str, Any]:
    """Store one chunk. The chunk a prior attempt was interrupted on may already be half-written
    (durable row, vector missing) -- that one is re-vectorized rather than deduplicated away."""
    if interrupted and await asyncio.to_thread(kb.redis_client.exists, "fact:%s" % fact_id):
        return await kb.vectorize_existing_fact(fact_id)
    return await kb._add_document_internal(text, metadata, fact_id)


def _outcome(status: OperationOutcome, doc_id: str, stored: int, total: int, first_id: str | None) -> Dict[str, Any]:
    """Build the caller-facing result; ``status`` is the OperationOutcome value."""
    return {
        "status": status.value,
        "fact_id": (first_id or doc_id) if stored else None,
        "document_id": doc_id,
        "chunks_stored": stored,
        "chunks_total": total,
    }


async def _ingest_single(kb, text: str, metadata: Dict[str, Any], doc_id: str, budget: float) -> Dict[str, Any]:
    """A document within one chunk: stored as before, all-or-nothing."""
    record = await read_ingest_record(kb, doc_id) if getattr(kb, "redis_client", None) is not None else {}
    if record:
        await _drop_orphans(kb, doc_id, 1, record)
    try:
        return await asyncio.wait_for(kb._add_document_internal(text, metadata, doc_id), timeout=budget)
    except asyncio.TimeoutError:
        logger.warning("Document addition timed out")
        return {"status": "timeout", "message": "Document addition timed out"}


async def _plan(kb, doc_id: str, digest: str, total: int) -> tuple[int, bool, str | None]:
    """(chunks already stored, resuming?, chunk-0 fact id); drops orphans of a longer earlier version."""
    record = await read_ingest_record(kb, doc_id)
    await _drop_orphans(kb, doc_id, total, record)
    if record.get("content_digest") != digest:
        return 0, False, None
    return int(record.get("chunks_stored", 0)), True, record.get("first_fact_id")


async def ingest_document(kb, content: str, metadata: Dict[str, Any], doc_id: str, budget: float) -> Dict[str, Any]:
    """Chunk *content* and store it within *budget* seconds, keeping what was stored on timeout."""
    chunks: List[str] = chunk_plain_text(content, KB_CHUNK_MAX_TOKENS)
    total = len(chunks)
    if total == 1:
        return await _ingest_single(kb, content, metadata, doc_id, budget)
    digest = content_digest(content)
    stored, resumed, first_id = await _plan(kb, doc_id, digest, total)
    offsets = locate_chunks(content, chunks) if "page_spans" in metadata else [None] * total
    deadline = time.monotonic() + budget
    status = OperationOutcome.SUCCESS
    for index in range(stored, total):
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError
            chunk_meta = _chunk_metadata(metadata, doc_id, index, total, offsets[index])
            interrupted = resumed and index == stored
            res = await asyncio.wait_for(
                _store_chunk(kb, chunks[index], chunk_meta, chunk_fact_id(doc_id, index), interrupted),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            logger.warning("Document %s ingest budget exhausted at chunk %d/%d", doc_id, index, total)
            status = OperationOutcome.PARTIAL if stored else OperationOutcome.TIMEOUT
            break
        if res.get("status") not in ("success", "duplicate"):
            if not stored:
                return res
            status = OperationOutcome.PARTIAL
            break
        first_id = first_id or res.get("fact_id")
        stored = index + 1
        await _write_record(kb, doc_id, OperationOutcome.PARTIAL, stored, total, _extra(digest, first_id))
    await _write_record(kb, doc_id, status, stored, total, _extra(digest, first_id))
    return _outcome(status, doc_id, stored, total, first_id)


def _extra(digest: str, first_id: str | None) -> Dict[str, Any]:
    return {"content_digest": digest, "first_fact_id": first_id or ""}
