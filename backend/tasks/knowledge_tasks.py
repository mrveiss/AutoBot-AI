# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Background Tasks for AutoBot

Celery tasks for long-running knowledge base operations with progress tracking.

Issue #424: Added periodic task for incremental man page updates.
"""

import asyncio
import logging
import subprocess
import sys

from backend.type_defs.common import Metadata

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)


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


@celery_app.task(bind=True, name="tasks.refresh_system_knowledge")
def refresh_system_knowledge(self) -> Metadata:
    """
    Refresh ALL system knowledge (man pages + AutoBot docs) in background.

    This is a long-running operation (can take up to 10 minutes) that indexes
    all system man pages and AutoBot documentation into the knowledge base.

    Args:
        self: Celery task instance (bound for progress updates)

    Returns:
        Dict with refresh results:
            - commands_indexed: Number of commands indexed
            - total_facts: Total facts in knowledge base
            - status: 'success' or 'failed'
    """
    try:
        # Update state to show we've started
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": "Starting system knowledge refresh...",
            },
        )

        logger.info(
            "Starting comprehensive system knowledge refresh (background task)..."
        )

        # Run the comprehensive indexing script
        result = subprocess.run(
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

        # Parse output using helper (Issue #315: reduced nesting)
        indexed_count, total_facts = _parse_indexing_output(result.stdout)

        logger.info(
            f"System knowledge refresh complete: {indexed_count} commands indexed, "
            f"{total_facts} total facts"
        )

        return {
            "status": "success",
            "commands_indexed": indexed_count,
            "total_facts": total_facts,
            "message": "System knowledge refreshed successfully",
        }

    except Exception as e:
        logger.exception("System knowledge refresh task failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Knowledge refresh failed: {str(e)}",
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

        from src.knowledge_base import KnowledgeBase

        # Run async reindex in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            kb = KnowledgeBase()
            loop.run_until_complete(kb.initialize())

            # Get updated stats
            stats = loop.run_until_complete(kb.get_stats())

            logger.info(
                f"Knowledge base reindex complete: {stats.get('total_vectors', 0)} vectors"
            )

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
            "error": str(e),
            "message": f"Reindex failed: {str(e)}",
        }


# =========================================================================
# Issue #424: Periodic Man Page Update Task
# =========================================================================


def _run_async_in_loop(coro):
    """Run async coroutine in a new event loop (helper for Celery tasks)."""
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


async def _scan_man_page_changes_async(machine_id: str, limit: int | None = None) -> dict:
    """
    Async implementation of man page change scanning.

    Issue #424: Core logic for incremental man page updates.

    Args:
        machine_id: Host identifier for change tracking
        limit: Optional limit on pages to process

    Returns:
        Dict with scan results and storage statistics
    """
    from src.utils.redis_client import get_redis_client
    from backend.services.fast_document_scanner import FastDocumentScanner
    from src.knowledge import get_knowledge_base

    try:
        # Get system context
        try:
            from src.utils.system_context import get_system_context
            system_context = get_system_context()
        except ImportError:
            system_context = {"machine_id": machine_id}

        # Get Redis client and scanner
        redis_client = get_redis_client(async_client=False, database="main")
        scanner = FastDocumentScanner(redis_client)

        # Scan for changes with parsing
        scan_result = scanner.scan_and_parse_changes(
            machine_id=machine_id,
            limit=limit,
            system_context=system_context,
        )

        # Get knowledge base
        kb = await get_knowledge_base()

        # Store parsed content
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
            "error": str(e),
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
        result = _run_async_in_loop(
            _scan_man_page_changes_async(machine_id, limit)
        )

        if result.get("status") == "success":
            summary = result.get("summary", {})
            logger.info(
                f"Man page scan complete: {result.get('items_stored', 0)} stored, "
                f"added={summary.get('added', 0)}, updated={summary.get('updated', 0)}"
            )
        else:
            logger.error("Man page scan failed: %s", result.get('error'))

        return result

    except Exception as e:
        logger.exception("Man page change scan task failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Scan failed: {str(e)}",
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
    from src.utils.redis_client import get_redis_client
    from backend.services.fast_document_scanner import FastDocumentScanner
    from src.knowledge import get_knowledge_base
    from src.constants.threshold_constants import TimingConstants

    # Get system context
    try:
        from src.utils.system_context import get_system_context
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
    items_added, items_failed = await _store_man_pages_to_kb(
        kb, man_pages, TimingConstants.MICRO_DELAY
    )

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
        logger.info(
            f"Starting full man page index for {machine_id} "
            f"(limit={limit}, sections={sections})..."
        )

        # Run async indexing using extracted helper (Issue #665)
        result = _run_async_in_loop(
            _execute_full_man_page_index(machine_id, limit, sections)
        )

        logger.info(
            f"Full man page index complete: {result.get('items_added', 0)} added, "
            f"{result.get('items_failed', 0)} failed"
        )

        return result

    except Exception as e:
        logger.exception("Full man page index task failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Index failed: {str(e)}",
        }


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
