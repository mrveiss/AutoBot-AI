# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Background worker for AST code-graph indexing (#4835, #4912, #17254).

Extracted from ``api/knowledge_population.py``, which sits exactly at its
recorded size ceiling and may not grow (#14236, #5060). Wiring the indexer's
route needed one line there, and a grandfathered file has none to spare -- so
the worker moves out rather than the ceiling moving up.
"""

from __future__ import annotations

import time

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _coverage_note(unsupported: dict) -> str:
    """Name the code this run could not read (#13510).

    Without it the caller sees a skip count and no way to tell an under-covered
    graph from a complete one -- the whole point of counting these files instead
    of dropping them.
    """
    if not unsupported:
        return ""
    breakdown = ", ".join(f"{ext} x{count}" for ext, count in sorted(unsupported.items()))
    return f"; no extractor for {sum(unsupported.values())} code files ({breakdown})"


async def _report_success(task_id: str, root_dir: str, result, elapsed: float) -> None:
    """Complete the task and log the run, including what it could not read."""
    from services.knowledge.task_status_manager import TaskStatusManager

    unsupported = result.unsupported_extensions
    await TaskStatusManager.complete_task(
        task_id=task_id,
        message=(
            f"Successfully indexed {result.success} code nodes "
            f"({result.skipped} skipped, {result.failed} failed){_coverage_note(unsupported)}"
        ),
        items_processed=result.success,
        elapsed_seconds=elapsed,
    )
    logger.info(
        "[%s] Code indexing completed: root=%s success=%d failed=%d skipped=%d unsupported=%s (%.1fs)",
        task_id,
        root_dir,
        result.success,
        result.failed,
        result.skipped,
        dict(sorted(unsupported.items())) or "none",
        elapsed,
    )


async def _index_code_background(task_id: str, root_dir: str, force: bool):
    """Background task: index source files via AST-based CodeIndexer (#4912)."""
    from services.knowledge.code_indexer import CodeIndexer
    from services.knowledge.doc_indexer import get_doc_indexer_service
    from services.knowledge.task_status_manager import TaskStatusManager

    start_time = time.time()

    try:
        logger.info("[%s] Starting background code indexing (root=%s force=%s)...", task_id, root_dir, force)

        await TaskStatusManager.update_task(
            task_id=task_id,
            status="running",
            message="Initializing indexer...",
            progress_percent=5,
        )

        doc_svc = get_doc_indexer_service()
        if not await doc_svc.initialize():
            logger.error("[%s] Indexer initialization failed", task_id)
            await TaskStatusManager.fail_task(
                task_id=task_id,
                error_message="Failed to initialize ChromaDB / embed model",
            )
            return

        await TaskStatusManager.update_task(
            task_id=task_id,
            status="running",
            message="Scanning and indexing source files...",
            progress_percent=10,
        )

        # #17254: its OWN collection, not doc_svc's — rationale at the accessor.
        from api.codebase_analytics.storage import require_code_graph_collection

        code_indexer = CodeIndexer(
            collection=await require_code_graph_collection(),
            embed_model=doc_svc._embed_model,
        )

        result = await code_indexer.index_directory(root_dir, force)

        elapsed = time.time() - start_time

        # #13510: name the code this run could not read. Without it the caller sees
        await _report_success(task_id, root_dir, result, elapsed)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("[%s] Background code indexing failed: %s", task_id, e)
        await TaskStatusManager.fail_task(
            task_id=task_id,
            error_message=str(e),
        )
