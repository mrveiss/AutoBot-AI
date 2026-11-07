# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Persist analysis problems to ChromaDB in bounded, reported chunks.

Split out of ``chromadb_storage`` for #18055.  That module is a grandfathered
large file that may not grow, and the chunking fix needed room; problem
storage is also a coherent unit on its own -- one document shape, one write
path, three call sites.

``chromadb_storage`` deliberately does NOT re-export these names: an alias
would be a second name for one implementation.  Callers import them from here.
"""

from api.codebase_analytics.source_scope import require_source_id
from autobot_shared.logging_manager import get_logger
from utils.file_categorization import FILE_CATEGORY_CODE

from .chromadb_storage import CHROMADB_BATCH_SIZE
from .storage import get_code_collection_async

logger = get_logger(__name__)


def _prepare_problem_document(problem: dict, problem_idx: int, source_id: str | None = None) -> tuple:
    """
    Prepare a problem document for ChromaDB storage.

    Issue #398: Extracted from _store_problems_batch_to_chromadb.
    Issue #1710: source_id for per-project scoping.
    Returns tuple of (id, document, metadata).
    """
    file_category = problem.get("file_category", FILE_CATEGORY_CODE)
    problem_doc = f"""
Problem: {problem.get('type', 'unknown')}
Severity: {problem.get('severity', 'medium')}
File: {problem.get('file_path', '')}
Category: {file_category}
Line: {problem.get('line', 0)}
Description: {problem.get('description', '')}
Suggestion: {problem.get('suggestion', '')}
    """.strip()

    metadata = {
        "type": "problem",
        "problem_type": problem.get("type", "unknown"),
        "severity": problem.get("severity", "medium"),
        "file_path": problem.get("file_path", ""),
        "file_category": file_category,
        "line_number": str(problem.get("line", 0)),
        "description": problem.get("description", ""),
        "suggestion": problem.get("suggestion", ""),
    }
    metadata["source_id"] = require_source_id(source_id, "codebase document id")
    prefix = f"{source_id}_"
    doc_id = f"{prefix}problem_{problem_idx}_{problem.get('type', 'unknown')}"
    return doc_id, problem_doc, metadata


def _prepare_problem_chunk(chunk: list, start_idx: int, source_id: str | None):
    """Build the (ids, documents, metadatas) triple for one chunk of problems."""
    ids, documents, metadatas = [], [], []
    for i, problem in enumerate(chunk):
        doc_id, problem_doc, metadata = _prepare_problem_document(problem, start_idx + i, source_id=source_id)
        ids.append(doc_id)
        documents.append(problem_doc)
        metadatas.append(metadata)
    return ids, documents, metadatas


async def _upsert_problem_chunk(collection, ids: list, documents: list, metadatas: list) -> bool:
    """Upsert one chunk, retrying once on a stale collection (#1712).

    Returns True when the chunk reached ChromaDB.  A chunk that fails is
    reported and skipped rather than discarding the chunks already written --
    before #18055 every problem went in a single call, so one failure lost the
    whole run.
    """
    try:
        await collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return True
    except Exception as e:
        err_msg = str(e).lower()
        if "does not exist" not in err_msg and "not found" not in err_msg:
            logger.error("Failed to batch store problems to ChromaDB (#1712): %s", e)
            return False
        # Issue #1712: Retry once on stale collection (mirrors #1249 pattern).
        logger.warning("Problems collection stale, recreating (#1712): %s", e)
        fresh = await get_code_collection_async()
        if fresh is None:
            logger.error("Cannot retry — collection unavailable (#1712)")
            return False
        try:
            await fresh.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info("Retry stored %d problems after stale collection", len(ids))
            return True
        except Exception as retry_err:
            logger.error("Retry also failed for problems batch: %s", retry_err)
            return False


async def _store_problems_batch_to_chromadb(
    collection,
    problems: list,
    start_idx: int,
    source_id: str | None = None,
    progress_callback=None,
) -> int:
    """Store problems to ChromaDB in bounded chunks (#398, #1710, #18055).

    Issue #18055: this used to build one list of every problem in the tree and
    issue a single unbounded ``upsert``.  On a large repo that one ``await``
    ran past the subprocess watchdog's window without emitting a progress
    update, so the supervisor killed the worker mid-write and the entire run
    was lost -- the scan completed, nothing was persisted, and ``last_indexed``
    stayed null.  Chunking bounds each ``await`` and reports progress per
    chunk, which is both the write-amplification fix and the liveness signal
    the watchdog needs.

    A single chunk that still exceeds the watchdog window is killed by design:
    that is the hang detector working.  ``CHROMADB_BATCH_SIZE`` is the knob.

    **Fail-closed on a bad source_id, deliberately.**  Document preparation now
    runs outside the per-chunk ``except``, so the ``ValueError`` that
    ``require_source_id`` raises for a missing or malformed id propagates and
    fails the task.  It used to be swallowed and logged as a storage failure,
    which reported "completed, 0 problems stored" for a run that wrote nothing
    scoped -- the unscoped-namespace defect #17758 exists to prevent.  The other
    writers in ``chromadb_storage`` already call ``require_source_id`` unguarded;
    this matches them.  An upsert failure is still per-chunk and non-fatal.
    """
    if not collection or not problems:
        return 0

    total = len(problems)
    stored = 0
    for offset in range(0, total, CHROMADB_BATCH_SIZE):
        chunk = problems[offset : offset + CHROMADB_BATCH_SIZE]
        ids, documents, metadatas = _prepare_problem_chunk(chunk, start_idx + offset, source_id)
        if await _upsert_problem_chunk(collection, ids, documents, metadatas):
            stored += len(chunk)
        done = offset + len(chunk)
        if progress_callback:
            await progress_callback(
                operation="Storing problems",
                current=done,
                total=total,
                current_file=f"Storing problems {done}/{total}",
            )

    logger.info(
        "Stored %d/%d problems to ChromaDB in chunks of %d (#18055)",
        stored,
        total,
        CHROMADB_BATCH_SIZE,
    )
    return stored
