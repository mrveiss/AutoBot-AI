# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Background Tasks for AutoBot

Celery tasks for long-running knowledge base operations with progress tracking.

Issue #424: Added periodic task for incremental man page updates.
"""

import asyncio
import fnmatch
import os
import subprocess  # nosec B404 - used for internal script execution only
import sys
import time
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app
from type_defs.common import Metadata

logger = get_logger(__name__)


# Issue #5083: exclude patterns for cleanup_generated_files. Matches filenames
# (via fnmatch) or any parent directory name. Prevents accidental deletion of
# persistent artefacts (ChromaDB sqlite journals, Redis AOF/RDB, WAL files)
# that may land in cache/temp dirs through operator mistake or future refactor.
_CLEANUP_EXCLUDE_PATTERNS = (
    "*.sqlite",
    "*.sqlite3",
    "*.sqlite-journal",
    "*.sqlite-wal",
    "*.sqlite-shm",
    "*.wal",
    "*.aof",
    "*.rdb",
    "*chroma*",  # chromadb artefact names (chromadb/, chroma.sqlite, etc.)
    "*redis*",  # redis data dirs/files (redis-data/, dump.rdb rename, etc.)
)


def _is_excluded(path: Path) -> bool:
    """Return True if path or any parent dir matches an exclude pattern.

    Issue #5083: guard cleanup_generated_files from deleting persistent
    artefacts (ChromaDB sqlite journals, Redis AOF fragments, WAL files).
    """
    for pattern in _CLEANUP_EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(path.name, pattern):
            return True
        # Check parent directory names too (for *chroma* catching chromadb/)
        for parent in path.parents:
            if fnmatch.fnmatch(parent.name, pattern):
                return True
    return False


def _parse_indexing_output(output: str) -> tuple:
    """Parse indexing script output for statistics (Issue #315: extracted helper).

    Args:
        output: Raw stdout from indexing script

    Returns:
        Tuple of (indexed_count, total_facts)
    """
    indexed_count = 0
    total_facts = 0
    for line in output.split("\n"):
        if "Successfully indexed:" in line:
            indexed_count = int(line.split(":")[1].strip())
        elif "Total facts in KB:" in line:
            total_facts = int(line.split(":")[1].strip())
    return indexed_count, total_facts


def _run_indexing_subprocess() -> dict:
    """Helper for refresh_system_knowledge. Ref: #1088.

    Runs the index_all_man_pages.py script as a subprocess and returns a result
    dict.  On non-zero exit returns a 'failed' dict; on success returns a
    'success' dict with commands_indexed and total_facts.
    """
    result = subprocess.run(  # nosec B603 - uses sys.executable with fixed internal script path
        [sys.executable, "scripts/utilities/index_all_man_pages.py"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error_msg = result.stderr[:500] if result.stderr else "Unknown error"
        logger.error("System knowledge refresh failed: %s", error_msg)
        return {
            "status": "failed",
            "error": error_msg,
            "message": "Knowledge refresh failed",
        }
    indexed_count, total_facts = _parse_indexing_output(result.stdout)
    logger.info(f"System knowledge refresh complete: {indexed_count} commands indexed, " f"{total_facts} total facts")
    return {
        "status": "success",
        "commands_indexed": indexed_count,
        "total_facts": total_facts,
        "message": "System knowledge refreshed successfully",
    }


@celery_app.task(bind=True, name="tasks.refresh_system_knowledge")
def refresh_system_knowledge(self) -> Metadata:
    """
    Refresh ALL system knowledge (man pages + AutoBot docs) in background.

    This is a long-running operation (can take up to 10 minutes) that indexes
    all system man pages and AutoBot documentation into the knowledge base.
    Issue #1088: Subprocess execution extracted to _run_indexing_subprocess.

    Args:
        self: Celery task instance (bound for progress updates)

    Returns:
        Dict with refresh results:
            - commands_indexed: Number of commands indexed
            - total_facts: Total facts in knowledge base
            - status: 'success' or 'failed'
    """
    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": "Starting system knowledge refresh...",
            },
        )
        logger.info("Starting comprehensive system knowledge refresh (background task)...")
        return _run_indexing_subprocess()

    except Exception as e:
        logger.exception("System knowledge refresh task failed: %s", e)
        return {
            "status": "failed",
            "error": "Knowledge refresh failed",
            "message": "Knowledge refresh failed",
        }


@celery_app.task(bind=True, name="tasks.reindex_knowledge_base")
def reindex_knowledge_base(self) -> Metadata:
    """
    Reindex the entire knowledge base (rebuild vector indexes).

    This operation can take several minutes for large knowledge bases.

    Args:
        self: Celery task instance (bound for progress updates)

    Returns:
        Dict with reindex results
    """
    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": "Starting knowledge base reindexing...",
            },
        )

        logger.info("Starting knowledge base reindex (background task)...")

        # Import here to avoid circular dependencies
        import asyncio

        from knowledge_base import KnowledgeBase

        # Run async reindex in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            kb = KnowledgeBase()
            loop.run_until_complete(kb.initialize())

            # Get updated stats
            stats = loop.run_until_complete(kb.get_stats())

            logger.info(f"Knowledge base reindex complete: {stats.get('total_vectors', 0)} vectors")

            return {
                "status": "success",
                "total_vectors": stats.get("total_vectors", 0),
                "total_facts": stats.get("total_facts", 0),
                "message": "Knowledge base reindexed successfully",
            }
        finally:
            loop.close()

    except Exception as e:
        logger.exception("Knowledge base reindex task failed: %s", e)
        return {
            "status": "failed",
            "error": "Knowledge base reindex failed",
            "message": "Reindex failed",
        }


# =========================================================================
# Issue #424: Periodic Man Page Update Task
# =========================================================================


def _run_async_in_loop(coro):
    """Run async coroutine in a new event loop (helper for Celery tasks).

    Resets stale async Redis pools before entering the loop so each task
    invocation gets fresh pool connections bound to its own event loop.
    Without this, pools created in a previous loop survive in the singleton
    but their internal connections reference a closed loop, causing
    get_async_redis_client() to catch the error and return None (#10936).
    """
    from autobot_shared.redis_client import reset_async_redis_pools

    reset_async_redis_pools()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _store_man_pages_to_kb(kb, man_pages: list, delay: float) -> tuple[int, int]:
    """Store man pages to knowledge base with delay between items (Issue #398: extracted).

    Args:
        kb: Knowledge base instance
        man_pages: List of man page dicts with 'content' and 'metadata'
        delay: Delay between storing each item (seconds)

    Returns:
        Tuple of (items_added, items_failed)
    """
    items_added = 0
    items_failed = 0

    for man_page in man_pages:
        try:
            content = man_page.get("content", "")
            metadata = man_page.get("metadata", {})

            if not content:
                items_failed += 1
                continue

            result = await kb.store_fact(content=content, metadata=metadata)

            if result and result.get("status") == "success":
                items_added += 1
            else:
                items_failed += 1

        except Exception as e:
            logger.error("Error storing man page: %s", e)
            items_failed += 1

        await asyncio.sleep(delay)

    return items_added, items_failed


async def _store_scan_results_to_kb(kb, scan_result: dict) -> tuple:
    """Helper for _scan_man_page_changes_async. Ref: #1088.

    Iterates over parsed_content in scan_result and stores each item to the
    knowledge base.  Returns (items_added, items_failed).
    """
    items_added = 0
    items_failed = 0
    for parsed in scan_result.get("parsed_content", []):
        try:
            result = await kb.store_fact(
                content=parsed.get("content", ""),
                metadata=parsed.get("metadata", {}),
            )
            if result and result.get("status") == "success":
                items_added += 1
            else:
                items_failed += 1
        except Exception as e:
            logger.error("Error storing parsed man page: %s", e)
            items_failed += 1
    return items_added, items_failed


async def _scan_man_page_changes_async(machine_id: str, limit: int | None = None) -> dict:
    """
    Async implementation of man page change scanning.

    Issue #424: Core logic for incremental man page updates.
    Issue #1088: Store loop extracted to _store_scan_results_to_kb.

    Args:
        machine_id: Host identifier for change tracking
        limit: Optional limit on pages to process

    Returns:
        Dict with scan results and storage statistics
    """
    from autobot_shared.redis_client import get_redis_client
    from knowledge import get_knowledge_base
    from services.fast_document_scanner import FastDocumentScanner

    try:
        try:
            from utils.system_context import get_system_context

            system_context = get_system_context()
        except ImportError:
            system_context = {"machine_id": machine_id}

        redis_client = get_redis_client(async_client=False, database="main")
        scanner = FastDocumentScanner(redis_client)

        scan_result = scanner.scan_and_parse_changes(
            machine_id=machine_id,
            limit=limit,
            system_context=system_context,
        )

        kb = await get_knowledge_base()
        items_added, items_failed = await _store_scan_results_to_kb(kb, scan_result)

        return {
            "status": "success",
            "machine_id": machine_id,
            "scan_duration_seconds": scan_result.get("scan_duration_seconds", 0),
            "summary": scan_result.get("summary", {}),
            "items_stored": items_added,
            "items_failed": items_failed,
            "parsed_count": scan_result.get("parsed_count", 0),
        }

    except Exception as e:
        logger.error("Man page change scan failed: %s", e)
        return {
            "status": "failed",
            "error": "Man page scan failed",
            "items_stored": 0,
        }


@celery_app.task(bind=True, name="tasks.scan_man_page_changes")
def scan_man_page_changes(self, limit: int | None = None) -> Metadata:
    """
    Scan for changed man pages and update knowledge base.

    Issue #424: Celery task for incremental man page updates.

    This task detects man pages that have been added, updated, or removed
    since the last scan using metadata-based change detection (fast).

    Args:
        self: Celery task instance (bound for progress updates)
        limit: Optional limit on number of changes to process

    Returns:
        Dict with scan results:
            - status: 'success' or 'failed'
            - items_stored: Number of man pages stored
            - summary: Change summary (added/updated/removed counts)
    """
    import socket

    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": "Scanning for man page changes...",
            },
        )

        machine_id = socket.gethostname()
        logger.info("Starting man page change scan for %s...", machine_id)

        # Run async scan in event loop
        result = _run_async_in_loop(_scan_man_page_changes_async(machine_id, limit))

        if result.get("status") == "success":
            summary = result.get("summary", {})
            logger.info(
                f"Man page scan complete: {result.get('items_stored', 0)} stored, "
                f"added={summary.get('added', 0)}, updated={summary.get('updated', 0)}"
            )
        else:
            logger.error("Man page scan failed: %s", result.get("error"))

        return result

    except Exception as e:
        logger.exception("Man page change scan task failed: %s", e)
        return {
            "status": "failed",
            "error": "Man page scan task failed",
            "message": "Scan failed",
        }


async def _execute_full_man_page_index(
    machine_id: str,
    limit: int | None,
    sections: list[str] | None,
) -> dict:
    """Execute full man page indexing asynchronously.

    Issue #665: Extracted from full_man_page_index to reduce function length.

    Args:
        machine_id: Host identifier
        limit: Optional limit on pages to process
        sections: Optional filter to specific sections

    Returns:
        Dict with indexing results
    """
    from autobot_shared.redis_client import get_redis_client
    from constants.threshold_constants import TimingConstants
    from knowledge import get_knowledge_base
    from services.fast_document_scanner import FastDocumentScanner

    # Get system context
    try:
        from utils.system_context import get_system_context

        system_context = get_system_context()
    except ImportError:
        system_context = {"machine_id": machine_id}

    # Get scanner and KB
    redis_client = get_redis_client(async_client=False, database="main")
    scanner = FastDocumentScanner(redis_client)
    kb = await get_knowledge_base()

    # Get all man pages
    man_pages = scanner.get_all_man_pages_for_indexing(
        limit=limit,
        sections=sections,
        system_context=system_context,
    )

    # Store using extracted helper (Issue #398)
    items_added, items_failed = await _store_man_pages_to_kb(kb, man_pages, TimingConstants.MICRO_DELAY)

    return {
        "status": "success",
        "items_added": items_added,
        "items_failed": items_failed,
        "total_scanned": len(man_pages),
        "machine_id": machine_id,
    }


@celery_app.task(bind=True, name="tasks.full_man_page_index")
def full_man_page_index(
    self,
    limit: int | None = None,
    sections: list[str] | None = None,
) -> Metadata:
    """
    Perform a full index of all system man pages.

    Issue #424: Celery task for complete man page indexing.
    Issue #665: Refactored to use extracted async helper.

    This is a longer-running operation that indexes all man pages (or a subset).
    Use for initial population or periodic full refresh.

    Args:
        self: Celery task instance
        limit: Optional limit on pages to process
        sections: Optional filter to specific sections (e.g., ["1", "8"])

    Returns:
        Dict with indexing results
    """
    import socket

    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": "Starting full man page index...",
            },
        )

        machine_id = socket.gethostname()
        logger.info(f"Starting full man page index for {machine_id} " f"(limit={limit}, sections={sections})...")

        # Run async indexing using extracted helper (Issue #665)
        result = _run_async_in_loop(_execute_full_man_page_index(machine_id, limit, sections))

        logger.info(
            f"Full man page index complete: {result.get('items_added', 0)} added, "
            f"{result.get('items_failed', 0)} failed"
        )

        return result

    except Exception as e:
        logger.exception("Full man page index task failed: %s", e)
        return {
            "status": "failed",
            "error": "Full man page index failed",
            "message": "Index failed",
        }


# =========================================================================
# Issue #4455: Knowledge cleanup tasks (orphan documents + generated files)
# =========================================================================


def _collect_orphan_doc_ids(collection) -> tuple[list[str], list[str], int]:
    """Scan ChromaDB collection and return IDs whose file paths no longer exist.

    Args:
        collection: ChromaDB collection object.

    Returns:
        Tuple of (orphan_ids, orphan_paths, scanned_count).
    """
    from utils.chromadb_client import get_all_paginated

    page = get_all_paginated(collection, include=["metadatas"])
    ids = page.get("ids") or []
    metadatas = page.get("metadatas") or []
    scanned = len(ids)

    orphan_ids: list[str] = []
    orphan_paths: list[str] = []

    for doc_id, meta in zip(ids, metadatas):
        if not meta:
            continue
        # Accept either "file_path" (DocIndexerService) or legacy "path" keys
        path = meta.get("file_path") or meta.get("path")
        if not path:
            continue
        try:
            if not os.path.exists(path):
                orphan_ids.append(doc_id)
                orphan_paths.append(path)
        except (OSError, ValueError) as e:
            logger.warning("Path check failed for %s: %s", path, e)

    return orphan_ids, orphan_paths, scanned


async def _cleanup_orphan_documents_async(dry_run: bool) -> dict:
    """Async core for cleanup_orphan_documents Celery task."""
    from services.knowledge.doc_indexer import get_doc_indexer_service

    service = get_doc_indexer_service()
    if not getattr(service, "_initialized", False):
        await service.initialize()

    collection = getattr(service, "_collection", None)
    if collection is None:
        logger.warning("DocIndexerService collection unavailable; skipping orphan cleanup")
        return {
            "status": "skipped",
            "reason": "collection_unavailable",
            "scanned": 0,
            "removed": 0,
            "dry_run": dry_run,
            "sample_removed_paths": [],
        }

    orphan_ids, orphan_paths, scanned = _collect_orphan_doc_ids(collection)

    if dry_run:
        for path in orphan_paths:
            logger.info("[dry_run] Would remove orphan document: %s", path)
        return {
            "status": "success",
            "scanned": scanned,
            "removed": 0,
            "dry_run": True,
            "sample_removed_paths": orphan_paths[:10],
        }

    removed = 0
    batch_size = 500
    for i in range(0, len(orphan_ids), batch_size):
        batch = orphan_ids[i : i + batch_size]
        try:
            collection.delete(ids=batch)
            removed += len(batch)
        except Exception as e:
            logger.error("Failed to delete orphan batch (size=%d): %s", len(batch), e)

    logger.info(
        "cleanup_orphan_documents: scanned=%d removed=%d",
        scanned,
        removed,
    )
    return {
        "status": "success",
        "scanned": scanned,
        "removed": removed,
        "dry_run": False,
        "sample_removed_paths": orphan_paths[:10],
    }


@celery_app.task(bind=True, name="tasks.cleanup_orphan_documents")
def cleanup_orphan_documents(self, dry_run: bool = False) -> Metadata:
    """
    Remove ChromaDB document entries whose source file no longer exists.

    Issue #4455: Scheduled nightly cleanup of dangling vectors left behind by
    deleted or moved source files. Metadata field ``file_path`` (or legacy
    ``path``) is used to resolve the on-disk location.

    Args:
        self: Celery task instance.
        dry_run: If True, log orphan entries without deleting them.

    Returns:
        Dict with cleanup statistics:
            - status: 'success' | 'skipped' | 'failed'
            - scanned: Number of documents inspected
            - removed: Number of documents deleted
            - dry_run: Whether this was a preview run
            - sample_removed_paths: Up to 10 sample orphan paths
    """
    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": "Scanning ChromaDB for orphan documents...",
            },
        )
        logger.info("Starting orphan document cleanup (dry_run=%s)...", dry_run)
        return _run_async_in_loop(_cleanup_orphan_documents_async(dry_run))
    except Exception as e:
        logger.exception("cleanup_orphan_documents failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
            "scanned": 0,
            "removed": 0,
            "dry_run": dry_run,
            "sample_removed_paths": [],
        }


def _resolve_cache_directories() -> list:
    """Return list of cache/temp directory Paths that cleanup_generated_files manages.

    Covered directories and the modules that write to them:
    - ``DATA_DIR/cache`` — ``utils/graceful_degradation.py`` writes
      ``data/cache/claude_responses/*.json`` via ``GracefulDegradationManager``;
      rglob covers all subdirectories recursively.
    - ``TEMP_DIR`` — miscellaneous temporary scratch space.

    Directories intentionally excluded:
    - ``DATA_DIR/embeddings_cache`` — no write sites found in the codebase.
    - ``DATA_DIR/chunks_temp`` — no write sites found in the codebase.
    - ``DATA_DIR/exports`` — only ``KnowledgeDocuments.export_all_data()`` could
      write here, but that method has no call sites and is therefore dead code.

    Only directories that actually exist are returned; the task silently skips
    missing paths to avoid errors in fresh installs.
    """
    from pathlib import Path

    from constants.path_constants import PATH

    candidates = [
        PATH.DATA_DIR / "cache",
        PATH.TEMP_DIR,
    ]
    return [p for p in candidates if isinstance(p, Path) and p.exists()]


def _cleanup_files_older_than(
    directories: list,
    cutoff_ts: float,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Walk directories, delete files older than cutoff_ts (mtime).

    Args:
        directories: List of Path objects to walk.
        cutoff_ts: Unix timestamp; files with mtime < cutoff_ts are stale.
        dry_run: If True, log what would be deleted without removing.

    Returns:
        Tuple of (scanned_count, removed_count, bytes_freed).
    """
    scanned = 0
    removed = 0
    bytes_freed = 0

    for directory in directories:
        if not directory.exists():
            continue
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            scanned += 1
            # Issue #5083: skip persistent artefacts (sqlite/WAL/AOF/RDB,
            # chromadb/, redis-data/) regardless of age.
            if _is_excluded(file_path):
                logger.debug("Skipping excluded file: %s", file_path)
                continue
            try:
                stat = file_path.stat()
            except OSError as e:
                logger.warning("Stat failed for %s: %s", file_path, e)
                continue
            if stat.st_mtime >= cutoff_ts:
                continue
            if dry_run:
                logger.info(
                    "[dry_run] Would remove stale cache file: %s (%d bytes)",
                    file_path,
                    stat.st_size,
                )
                continue
            try:
                file_path.unlink()
                removed += 1
                bytes_freed += stat.st_size
            except OSError as e:
                logger.warning("Failed to delete %s: %s", file_path, e)

    return scanned, removed, bytes_freed


@celery_app.task(bind=True, name="tasks.cleanup_generated_files")
def cleanup_generated_files(
    self,
    dry_run: bool = False,
    ttl_days: int | None = None,
) -> Metadata:
    """
    Delete stale generated cache/temp files older than the configured TTL.

    Issue #4455: Scheduled nightly cleanup of cached embeddings, chunk
    intermediates, export artefacts, and other generated files that accumulate
    indefinitely under ``PATH.DATA_DIR`` and ``PATH.TEMP_DIR``.

    Args:
        self: Celery task instance.
        dry_run: If True, log removal candidates without deleting them.
        ttl_days: Override for ``KNOWLEDGE_CACHE_TTL_DAYS`` from ssot_config.

    Returns:
        Dict with cleanup statistics:
            - status: 'success' | 'failed'
            - scanned: Number of files inspected
            - removed: Number of files deleted
            - bytes_freed: Total bytes reclaimed
            - dry_run: Whether this was a preview run
            - ttl_days: Effective TTL applied
    """
    from autobot_shared.ssot_config import config as ssot_config

    effective_ttl = ttl_days if ttl_days is not None else ssot_config.knowledge_cache_ttl_days
    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": f"Scanning generated files older than {effective_ttl} days...",
            },
        )
        logger.info(
            "Starting generated-file cleanup (dry_run=%s, ttl_days=%d)...",
            dry_run,
            effective_ttl,
        )

        directories = _resolve_cache_directories()
        cutoff_ts = time.time() - (effective_ttl * 86400)

        scanned, removed, bytes_freed = _cleanup_files_older_than(
            directories,
            cutoff_ts,
            dry_run,
        )

        logger.info(
            "cleanup_generated_files: scanned=%d removed=%d bytes_freed=%d",
            scanned,
            removed,
            bytes_freed,
        )
        return {
            "status": "success",
            "scanned": scanned,
            "removed": removed,
            "bytes_freed": bytes_freed,
            "dry_run": dry_run,
            "ttl_days": effective_ttl,
        }
    except Exception as e:
        logger.exception("cleanup_generated_files failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
            "scanned": 0,
            "removed": 0,
            "bytes_freed": 0,
            "dry_run": dry_run,
            "ttl_days": effective_ttl,
        }


# =========================================================================
# Issue #5081: Prune done entries from the sync queue DONE zset
# =========================================================================


@celery_app.task(bind=True, name="tasks.prune_sync_queue_done")
def prune_sync_queue_done(self) -> dict:
    """Remove expired entries from the doc_sync:queue:done zset.

    Issue #5081: The DONE zset grew unbounded because prune_done() was only
    callable via admin API.  This task is scheduled via Celery Beat so
    pruning runs automatically on a configurable cron.

    Returns:
        Dict with pruning statistics:
            - status: 'success' | 'failed'
            - pruned: Number of entries removed
    """
    from services.knowledge.sync_queue import get_document_sync_queue

    try:
        self.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 1, "status": "Pruning sync queue done entries..."},
        )
        logger.info("Starting sync queue done-entry pruning...")
        queue = get_document_sync_queue()
        pruned = _run_async_in_loop(queue.prune_done())
        logger.info("prune_sync_queue_done: pruned=%d", pruned)
        return {"status": "success", "pruned": pruned}
    except Exception as e:
        logger.exception("prune_sync_queue_done failed: %s", e)
        return {"status": "failed", "error": str(e), "pruned": 0}


# =========================================================================
# Periodic Task Beat Schedule (add to celery_app.conf.beat_schedule)
# =========================================================================
#
# To enable periodic man page scanning, add to backend/celery_app.py:
#
# celery_app.conf.beat_schedule = {
#     'scan-man-pages-hourly': {
#         'task': 'tasks.scan_man_page_changes',
#         'schedule': crontab(minute=0),  # Every hour
#         'args': (100,),  # Limit to 100 changes per run
#     },
#     'full-man-page-index-weekly': {
#         'task': 'tasks.full_man_page_index',
#         'schedule': crontab(day_of_week='sunday', hour=3, minute=0),
#         'kwargs': {'sections': ['1', '8']},  # User commands and admin
#     },
# }
# =========================================================================
