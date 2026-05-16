# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase scanning and indexing orchestrator.

Issue #2013: Decomposed from 3352-line god module into focused sub-modules.
Issue #2364: Further decomposed — executor, file pipeline, subprocess runner,
             and indexing phases each live in their own module.

This file is the orchestrator — it wires the sub-modules together and
re-exports all public symbols for backward compatibility.

Sub-module responsibilities
---------------------------
- indexing_executor    — dedicated thread pool + async runner
- file_pipeline        — per-file analysis dispatch + iteration
- indexing_phases      — ChromaDB init / scan / batch-store phases
- subprocess_runner    — isolated subprocess launch + watchdog
- progress_tracker     — Redis-backed task state and queue persistence
- file_analyzer        — parallel file-analysis worker
- chromadb_storage     — ChromaDB and Redis storage helpers
- stats_aggregation    — result aggregation utilities
- file_counter         — file discovery and stats logging
"""

import asyncio
import threading
from collections import deque
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import HTTPException

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.path_constants import PATH
from type_defs.common import Metadata

from .chromadb_storage import _recreate_chromadb_collection  # noqa: F401
from .chromadb_storage import (
    CHROMADB_BATCH_SIZE,
    INCREMENTAL_INDEXING_ENABLED,
    PARALLEL_BATCH_COUNT,
    _verify_chromadb_storage,
)
from .file_analyzer import _determine_analyzer_type  # noqa: F401
from .file_analyzer import _enrich_items_with_metadata  # noqa: F401
from .file_analyzer import (  # noqa: F401
    PARALLEL_FILE_CONCURRENCY,
    PARALLEL_MODE_ENABLED,
)
from .file_analyzer import _analyze_single_file as _fa_analyze_single_file
from .file_analyzer import _process_files_parallel as _fa_process_files_parallel
from .file_counter import (
    _gather_scannable_files,
    _log_incremental_stats,
)
from .file_pipeline import _iterate_and_process_files
from .indexing_executor import _get_indexing_executor  # noqa: F401
from .indexing_executor import _run_in_indexing_thread
from .indexing_phases import _create_progress_updater as _ip_create_progress_updater
from .indexing_phases import _run_indexing_phases as _ip_run_indexing_phases
from .progress_tracker import _persist_queue_entry  # noqa: F401
from .progress_tracker import _pop_queue_entry_redis  # noqa: F401
from .progress_tracker import _remove_queue_entries_redis  # noqa: F401
from .progress_tracker import (
    _create_initial_task_state,
    _file_needs_reindex,
    _load_task_from_redis,
)
from .progress_tracker import _mark_task_completed as _pt_mark_completed
from .progress_tracker import _mark_task_failed as _pt_mark_failed
from .progress_tracker import _save_task_to_redis as _pt_save_task_to_redis
from .progress_tracker import (
    _store_file_hash,
)
from .progress_tracker import _update_task_batch_info as _pt_update_task_batch_info
from .progress_tracker import _update_task_phase as _pt_update_task_phase
from .progress_tracker import _update_task_stats as _pt_update_task_stats
from .stats_aggregation import _aggregate_from_file_result  # noqa: F401
from .stats_aggregation import (  # noqa: F401
    _aggregate_all_results,
    _calculate_analysis_statistics,
    _create_empty_analysis_results,
)
from .storage import get_redis_connection
from .subprocess_runner import _run_indexing_subprocess as _sr_run_indexing_subprocess
from .types import FileAnalysisResult

logger = get_logger(__name__)

# =============================================================================
# File processing configuration (Issue #659)
# Controls progress update frequency during scanning (every N/5 files)
# Default: 50, Range: 1-100
# =============================================================================
try:
    _parallel_files = int(config.codebase_scan_parallel_files)
    PARALLEL_FILE_PROCESSING = max(1, min(_parallel_files, 100))
except ValueError:
    logger.warning("Invalid CODEBASE_SCAN_PARALLEL_FILES, using default 50")
    PARALLEL_FILE_PROCESSING = 50

# =============================================================================
# Global mutable state
# =============================================================================

# In-memory storage fallback
_in_memory_storage = {}

# Global storage for indexing task progress
indexing_tasks: Dict[str, Metadata] = {}

# Store active task references
_active_tasks: Dict[str, asyncio.Task] = {}

# Global lock to prevent concurrent indexing
_indexing_lock = asyncio.Lock()

# Lock for protecting indexing_tasks and _active_tasks
_tasks_lock = asyncio.Lock()

# Threading lock for synchronous callbacks
_tasks_sync_lock = threading.Lock()

_current_indexing_task_id: str | None = None

# FIFO queue of pending indexing jobs (#1133)
# Each item: {"source_id": str, "root_path": str, "queued_at": str, "requested_by": str}
_index_queue: deque = deque()

# Note: Redis constants (_TASK_REDIS_PREFIX, _TASK_REDIS_TTL, _QUEUE_REDIS_KEY)
# are defined in progress_tracker.py as the single source of truth.


# =============================================================================
# Bound wrappers — bind module-level state to progress_tracker functions
# =============================================================================


async def _save_task_to_redis_bound(task_id: str) -> None:
    """Persist task state to Redis — bound to module-level indexing_tasks."""
    await _pt_save_task_to_redis(task_id, indexing_tasks)


async def _load_task_from_redis_bound(task_id: str) -> Dict | None:
    """Load task from Redis (re-exported for convenience)."""
    return await _load_task_from_redis(task_id)


def _update_task_phase_bound(task_id: str, phase_id: str, status: str) -> None:
    """Update task phase — bound to module-level indexing_tasks."""
    _pt_update_task_phase(task_id, phase_id, status, indexing_tasks)


def _update_task_batch_info_bound(
    task_id: str, current_batch: int, total_batches: int, items_in_batch: int = 0
) -> None:
    """Update task batch info — bound to module-level indexing_tasks."""
    _pt_update_task_batch_info(task_id, current_batch, total_batches, indexing_tasks, items_in_batch)


def _update_task_stats_bound(task_id: str, **kwargs) -> None:
    """Update task stats — bound to module-level indexing_tasks."""
    _pt_update_task_stats(task_id, indexing_tasks, **kwargs)


def _mark_task_completed_bound(task_id: str, analysis_results: Dict, hardcodes_stored: int, storage_type: str) -> None:
    """Mark task completed — bound to module-level indexing_tasks."""
    _pt_mark_completed(task_id, analysis_results, hardcodes_stored, storage_type, indexing_tasks)


def _mark_task_failed_bound(task_id: str, error: Exception) -> None:
    """Mark task failed — bound to module-level indexing_tasks."""
    _pt_mark_failed(task_id, error, indexing_tasks)


def _create_initial_task_state_bound() -> Dict:
    """Create initial task state with module-level config constants."""
    return _create_initial_task_state(CHROMADB_BATCH_SIZE, PARALLEL_BATCH_COUNT, INCREMENTAL_INDEXING_ENABLED)


async def _file_needs_reindex_bound(file_path, relative_path: str, redis_client) -> Tuple[bool, str]:
    """Check if file needs reindex — bound to module-level config and thread pool."""
    return await _file_needs_reindex(
        file_path,
        relative_path,
        redis_client,
        INCREMENTAL_INDEXING_ENABLED,
        _run_in_indexing_thread,
    )


async def recover_index_queue() -> int:
    """Restore in-memory queue from Redis on startup (#1717).

    Returns the number of recovered entries.
    """
    from .progress_tracker import recover_index_queue as _pt_recover

    return await _pt_recover(_tasks_lock, _index_queue)


# =============================================================================
# Bound wrappers for file_analyzer — inject thread pool and hash helpers
# =============================================================================


async def _analyze_single_file_bound(
    file_path,
    root_path_obj,
    redis_client=None,
) -> FileAnalysisResult:
    """Analyse single file — bound to module-level thread pool and config."""
    return await _fa_analyze_single_file(
        file_path,
        root_path_obj,
        _file_needs_reindex_bound,
        _run_in_indexing_thread,
        _store_file_hash,
        redis_client,
    )


async def _process_files_parallel_bound(
    all_files: List,
    root_path_obj,
    redis_client=None,
    progress_callback=None,
    total_files: int = 0,
) -> List[FileAnalysisResult]:
    """Process files in parallel — bound to module-level dependencies."""
    return await _fa_process_files_parallel(
        all_files,
        root_path_obj,
        _file_needs_reindex_bound,
        _run_in_indexing_thread,
        _store_file_hash,
        redis_client,
        progress_callback,
        total_files,
    )


# Re-bind the public API names to bound versions with original signatures.
# Tests and external callers import these from scanner and expect the
# original 3-argument signatures (no injected dependencies).
_process_files_parallel = _process_files_parallel_bound
_analyze_single_file = _analyze_single_file_bound


# =============================================================================
# Core scanning
# =============================================================================


async def scan_codebase(
    root_path: str | None = None,
    progress_callback: callable | None = None,
    immediate_store_collection=None,
    redis_client=None,
    source_id: str | None = None,
) -> Metadata:
    """Scan the entire codebase using MCP-like file operations.

    Issue #315, #281, #398: Uses extracted helpers for modular processing.
    Issue #539: Added redis_client param for incremental indexing support.
    Issue #620: Refactored to use helper functions.
    """
    if root_path is None:
        root_path = str(PATH.PROJECT_ROOT)

    analysis_results = _create_empty_analysis_results()

    if redis_client is None and INCREMENTAL_INDEXING_ENABLED:
        redis_client = await get_redis_connection()

    try:
        root_path_obj = Path(root_path)

        total_files, all_files = await _gather_scannable_files(
            root_path_obj, progress_callback, _run_in_indexing_thread
        )

        files_processed, files_skipped = await _iterate_and_process_files(
            all_files,
            root_path_obj,
            analysis_results,
            immediate_store_collection,
            progress_callback,
            total_files,
            _file_needs_reindex_bound,
            _run_in_indexing_thread,
            _process_files_parallel_bound,
            PARALLEL_FILE_PROCESSING,
            redis_client,
            source_id=source_id,
        )

        _log_incremental_stats(files_processed, files_skipped, INCREMENTAL_INDEXING_ENABLED)

        if not PARALLEL_MODE_ENABLED:
            _calculate_analysis_statistics(analysis_results)
        return analysis_results

    except Exception as e:
        logger.error("Error scanning codebase: %s", e)
        raise HTTPException(status_code=500, detail="Codebase scan failed")


# =============================================================================
# Progress updater factory (bound to module state)
# =============================================================================


def _create_progress_updater(task_id: str, update_phase, update_batch_info):
    """Create a progress update callback for the given task.

    Issue #398: Extracted from do_indexing_with_progress to reduce method length.
    """
    return _ip_create_progress_updater(
        task_id,
        update_phase,
        update_batch_info,
        indexing_tasks,
        _save_task_to_redis_bound,
    )


# =============================================================================
# Subprocess entry point (bound to module state)
# =============================================================================


async def _run_indexing_subprocess(task_id: str, root_path: str, source_id: str | None = None) -> None:
    """Launch isolated indexing subprocess to prevent ChromaDB SIGSEGV (#1180).

    Delegates to subprocess_runner._run_indexing_subprocess with module-level
    state injected.  Issue #1341, #1710.
    """
    await _sr_run_indexing_subprocess(
        task_id,
        root_path,
        indexing_tasks,
        _tasks_lock,
        _create_initial_task_state_bound,
        _save_task_to_redis_bound,
        _mark_task_failed_bound,
        source_id=source_id,
    )


# =============================================================================
# Main background task
# =============================================================================


async def do_indexing_with_progress(task_id: str, root_path: str, source_id: str | None = None):
    """Background task: Index codebase with real-time progress updates.

    Issue #281, #398: Refactored with extracted helpers for reduced complexity.
    Issue #1710: source_id scopes all storage to one project.
    """
    try:
        logger.info(
            "[Task %s] Starting background codebase indexing for: %s",
            task_id,
            root_path,
        )

        async with _tasks_lock:
            state = _create_initial_task_state_bound()
            # Issue #3685: Store source_id so stats endpoint can filter by project
            state["source_id"] = source_id
            indexing_tasks[task_id] = state
            await _save_task_to_redis_bound(task_id)

        def update_phase(phase_id, status):
            _update_task_phase_bound(task_id, phase_id, status)

        def update_batch_info(c, t, i=0):
            _update_task_batch_info_bound(task_id, c, t, i)

        def update_stats(**kwargs):
            _update_task_stats_bound(task_id, **kwargs)

        update_progress = _create_progress_updater(task_id, update_phase, update_batch_info)

        analysis_results, hardcodes_stored = await _ip_run_indexing_phases(
            task_id,
            root_path,
            update_progress,
            update_phase,
            update_batch_info,
            update_stats,
            scan_codebase,
            _tasks_lock,
            indexing_tasks,
            source_id=source_id,
        )

        update_phase("finalize", "running")

        await _verify_chromadb_storage(task_id, analysis_results)

        # #6747: Run cross-file rules (LSP + consolidation) over the scanned
        # root and persist findings to ChromaDB so they surface in
        # /codebase/problems alongside the per-file results.  Imported lazily
        # so a missing dep doesn't break the existing per-file pipeline.
        try:
            from api.codebase_analytics.cross_file_analysis import (
                run_cross_file_analysis,
            )

            await run_cross_file_analysis(root_path, source_id=source_id)
        except Exception as exc:
            logger.warning("[Task %s] Cross-file analysis skipped: %s", task_id, exc)

        _mark_task_completed_bound(task_id, analysis_results, hardcodes_stored, "chromadb")
        update_phase("finalize", "completed")
        await _save_task_to_redis_bound(task_id)
        logger.info("[Task %s] Indexing completed successfully", task_id)

    except Exception as e:
        logger.error("[Task %s] Indexing failed: %s", task_id, e, exc_info=True)
        _mark_task_failed_bound(task_id, e)
        await _save_task_to_redis_bound(task_id)
