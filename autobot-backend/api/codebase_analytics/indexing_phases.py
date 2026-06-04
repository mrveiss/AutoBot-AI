# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Core indexing phase orchestration.

Issue #2364: Extracted from scanner.py to separate phase-level orchestration
from the top-level do_indexing_with_progress entry point.
from autobot_shared.logging_manager import get_logger

Public functions
----------------
- _create_progress_updater   — factory for per-task progress callbacks
- _init_chromadb_with_retry  — initialise ChromaDB with one retry
- _scan_and_log_analysis     — run scan_codebase and log result counts
- _run_indexing_phases       — execute init → scan → store → hardcodes
"""

import asyncio
from typing import Callable

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants

from .chromadb_storage import (
    _initialize_chromadb_collection,
    _prepare_batch_data,
    _store_batches_to_chromadb,
    _store_hardcodes_to_redis,
)

logger = get_logger(__name__)


def _create_progress_updater(
    task_id: str,
    update_phase: Callable,
    update_batch_info: Callable,
    indexing_tasks: dict,
    save_task_fn,
):
    """Create a progress update callback for the given task.

    Issue #398: Extracted from do_indexing_with_progress to reduce method length.

    Parameters
    ----------
    save_task_fn:
        Async callable ``(task_id)`` that persists task state to Redis.
    """
    from .progress_tracker import _create_progress_updater as _pt_create_updater

    return _pt_create_updater(
        task_id,
        update_phase,
        update_batch_info,
        indexing_tasks,
        save_task_fn,
    )


async def _init_chromadb_with_retry(
    task_id: str,
    update_progress,
    update_phase,
    source_id: str | None = None,
):
    """Initialise ChromaDB collection with one retry on failure.

    Issue #398: Extracted from _run_indexing_phases.
    Issue #1249: Retry once on transient connection failure.
    Issue #1710: source_id scopes cleanup to one project.
    """
    code_collection = await _initialize_chromadb_collection(task_id, update_progress, update_phase, source_id=source_id)
    if not code_collection:
        logger.warning("[Task %s] ChromaDB init failed, retrying once (#1249)", task_id)
        await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
        code_collection = await _initialize_chromadb_collection(
            task_id, update_progress, update_phase, source_id=source_id
        )
    if not code_collection:
        raise Exception("ChromaDB connection failed after retry")
    return code_collection


async def _scan_and_log_analysis(
    task_id: str,
    root_path: str,
    update_progress,
    update_phase,
    update_stats,
    code_collection,
    scan_codebase_fn,
    source_id: str | None = None,
):
    """Run codebase scan and log result counts.

    Issue #398: Extracted from _run_indexing_phases.
    Issue #1712: Log analysis result counts before batch storage.

    Parameters
    ----------
    scan_codebase_fn:
        Async callable with the ``scan_codebase`` signature.
    """
    analysis_results = await scan_codebase_fn(
        root_path,
        progress_callback=update_progress,
        immediate_store_collection=code_collection,
        source_id=source_id,
    )
    update_stats(
        files_scanned=analysis_results["stats"]["total_files"],
        problems_found=len(analysis_results["all_problems"]),
        functions_found=len(analysis_results["all_functions"]),
        classes_found=len(analysis_results["all_classes"]),
    )
    update_phase("scan", "completed")
    logger.info(
        "[Task %s] #1712 pre-store: %d functions, %d classes, " "%d problems, %d hardcodes, %d files",
        task_id,
        len(analysis_results.get("all_functions", [])),
        len(analysis_results.get("all_classes", [])),
        len(analysis_results.get("all_problems", [])),
        len(analysis_results.get("all_hardcodes", [])),
        len(analysis_results.get("files", {})),
    )
    return analysis_results


async def _store_analysis_batches(
    analysis_results: dict,
    code_collection,
    task_id: str,
    update_progress,
    update_phase,
    update_batch_info,
    update_stats,
    tasks_lock: asyncio.Lock,
    indexing_tasks: dict,
    source_id: str | None = None,
) -> int:
    """Prepare and store analysis batches to ChromaDB, then persist hardcodes.

    Issue #2364: Extracted from _run_indexing_phases to keep it under 65 lines.
    Returns the number of hardcoded values stored to Redis.
    """
    batch_ids, batch_documents, batch_metadatas = await _prepare_batch_data(
        analysis_results,
        task_id,
        update_progress,
        update_phase,
        source_id=source_id,
    )
    if batch_ids:
        await _store_batches_to_chromadb(
            code_collection,
            batch_ids,
            batch_documents,
            batch_metadatas,
            task_id,
            update_progress,
            update_phase,
            update_batch_info,
            update_stats,
            tasks_lock,
            indexing_tasks,
        )
    return await _store_hardcodes_to_redis(
        analysis_results.get("all_hardcodes", []),
        task_id,
        source_id=source_id,
    )


async def _run_indexing_phases(
    task_id: str,
    root_path: str,
    update_progress,
    update_phase,
    update_batch_info,
    update_stats,
    scan_codebase_fn,
    tasks_lock: asyncio.Lock,
    indexing_tasks: dict,
    source_id: str | None = None,
):
    """Execute the core indexing phases: init → scan → store → hardcodes.

    Issue #398: Extracted from do_indexing_with_progress.
    Issue #1249: Retry ChromaDB init once on failure.
    Issue #1710: source_id scopes cleanup and metadata to one project.
    scan_codebase_fn is injected to avoid circular imports.
    """
    code_collection = await _init_chromadb_with_retry(task_id, update_progress, update_phase, source_id=source_id)
    update_phase("init", "completed")
    update_phase("scan", "running")

    analysis_results = await _scan_and_log_analysis(
        task_id,
        root_path,
        update_progress,
        update_phase,
        update_stats,
        code_collection,
        scan_codebase_fn,
        source_id=source_id,
    )

    hardcodes_stored = await _store_analysis_batches(
        analysis_results,
        code_collection,
        task_id,
        update_progress,
        update_phase,
        update_batch_info,
        update_stats,
        tasks_lock,
        indexing_tasks,
        source_id=source_id,
    )
    return analysis_results, hardcodes_stored
