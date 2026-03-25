# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase scanning and indexing orchestrator.

Issue #2013: Decomposed from 3352-line god module into focused sub-modules.
This file is the orchestrator — it wires the sub-modules together and
re-exports all public symbols for backward compatibility.
"""

import asyncio
import logging
import os
import sys
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from constants.path_constants import PATH
from fastapi import HTTPException
from type_defs.common import Metadata
from utils.file_categorization import (
    FILE_CATEGORY_CODE,
    SKIP_DIRS,
)
from utils.file_categorization import get_file_category as _get_file_category

from .analyzers import (
    analyze_documentation_file,
    analyze_javascript_vue_file,
    analyze_python_file,
)
from .chromadb_storage import _recreate_chromadb_collection  # noqa: F401
from .chromadb_storage import (
    CHROMADB_BATCH_SIZE,
    INCREMENTAL_INDEXING_ENABLED,
    PARALLEL_BATCH_COUNT,
    _initialize_chromadb_collection,
    _prepare_batch_data,
    _store_batches_to_chromadb,
    _store_hardcodes_to_redis,
    _store_problems_batch_to_chromadb,
    _verify_chromadb_storage,
)
from .file_analyzer import _determine_analyzer_type  # noqa: F401
from .file_analyzer import _enrich_items_with_metadata  # noqa: F401
from .file_analyzer import (
    _FILE_TYPE_MAP,
    PARALLEL_FILE_CONCURRENCY,
    PARALLEL_MODE_ENABLED,
)
from .file_analyzer import _analyze_single_file as _fa_analyze_single_file
from .file_analyzer import _process_files_parallel as _fa_process_files_parallel
from .file_counter import (
    _gather_scannable_files,
    _log_incremental_stats,
)
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
from .stats_aggregation import (
    _aggregate_all_results,
    _aggregate_file_analysis,
    _calculate_analysis_statistics,
    _create_empty_analysis_results,
)
from .storage import get_redis_connection
from .types import FileAnalysisResult

logger = logging.getLogger(__name__)

# =============================================================================
# Issue #1341: Subprocess timeout and watchdog configuration
_SUBPROCESS_HARD_TIMEOUT = 1800  # 30 minutes max for entire subprocess
_SUBPROCESS_PROGRESS_TIMEOUT = 300  # 5 min without progress = stale
_SUBPROCESS_WATCHDOG_INTERVAL = 30  # Check progress every 30 seconds

# Dedicated Indexing Thread Pool (Issue #XXX: Prevent thread starvation)
# =============================================================================
# The indexing task needs its own thread pool to avoid being starved by
# concurrent analytics requests (duplicates, hardcodes, etc.) that also use
# the default executor. With 175k+ files, the default pool can be exhausted.
_INDEXING_EXECUTOR: ThreadPoolExecutor | None = None
_INDEXING_EXECUTOR_MAX_WORKERS = 4  # Dedicated threads for indexing operations
_INDEXING_EXECUTOR_LOCK = threading.Lock()  # Issue #662: Thread-safe initialization


def _get_indexing_executor() -> ThreadPoolExecutor:
    """Get or create the dedicated indexing thread pool (thread-safe)."""
    global _INDEXING_EXECUTOR
    if _INDEXING_EXECUTOR is None:
        with _INDEXING_EXECUTOR_LOCK:
            # Double-check after acquiring lock
            if _INDEXING_EXECUTOR is None:
                _INDEXING_EXECUTOR = ThreadPoolExecutor(
                    max_workers=_INDEXING_EXECUTOR_MAX_WORKERS,
                    thread_name_prefix="indexing_worker",
                )
                logger.info(
                    "Created dedicated indexing thread pool (%d workers)",
                    _INDEXING_EXECUTOR_MAX_WORKERS,
                )
    return _INDEXING_EXECUTOR


async def _run_in_indexing_thread(func, *args):
    """Run a function in the dedicated indexing thread pool.

    If no args are provided (e.g., when using a lambda), calls func directly.
    Otherwise, calls func(*args).
    """
    loop = asyncio.get_running_loop()
    executor = _get_indexing_executor()
    if args:
        return await loop.run_in_executor(executor, func, *args)
    else:
        return await loop.run_in_executor(executor, func)


# =============================================================================
# File processing configuration (Issue #659)
# Controls progress update frequency during scanning (every N/5 files)
# Default: 50, Range: 1-100
try:
    _parallel_files = int(os.getenv("CODEBASE_SCAN_PARALLEL_FILES", "50"))
    PARALLEL_FILE_PROCESSING = max(1, min(_parallel_files, 100))
except ValueError:
    logger.warning("Invalid CODEBASE_SCAN_PARALLEL_FILES, using default 50")
    PARALLEL_FILE_PROCESSING = 50


# Issue #398: File type mapping imported from file_analyzer.py (single source of truth)


async def _get_file_analysis(
    file_path: Path, extension: str, stats: dict
) -> Optional[dict]:
    """
    Get analysis for a file based on its type.

    Issue #315, #367, #398: Refactored with mapping table for reduced complexity.
    """
    for ext_set, stat_key, analyzer_type in _FILE_TYPE_MAP:
        if extension in ext_set:
            stats[stat_key] += 1
            if analyzer_type == "python":
                return await analyze_python_file(str(file_path))
            elif analyzer_type == "js":
                # Issue #666: Wrap blocking file I/O in asyncio.to_thread
                return await asyncio.to_thread(
                    analyze_javascript_vue_file, str(file_path)
                )
            elif analyzer_type == "doc":
                # Issue #666: Wrap blocking file I/O in asyncio.to_thread
                return await asyncio.to_thread(
                    analyze_documentation_file, str(file_path)
                )
            return None

    stats["other_files"] += 1
    return None


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

_current_indexing_task_id: Optional[str] = None

# FIFO queue of pending indexing jobs (#1133)
# Each item: {"source_id": str, "root_path": str, "queued_at": str, "requested_by": str}
_index_queue: deque = deque()

# Note: Redis constants (_TASK_REDIS_PREFIX, _TASK_REDIS_TTL, _QUEUE_REDIS_KEY)
# are defined in progress_tracker.py as the single source of truth.


# =============================================================================
# Wrappers that bind module-level state to progress_tracker functions
# =============================================================================


async def _save_task_to_redis_bound(task_id: str) -> None:
    """Persist task state to Redis — bound to module-level indexing_tasks."""
    await _pt_save_task_to_redis(task_id, indexing_tasks)


async def _load_task_from_redis_bound(task_id: str) -> Optional[Dict]:
    """Load task from Redis (re-exported for convenience)."""
    return await _load_task_from_redis(task_id)


def _update_task_phase_bound(task_id: str, phase_id: str, status: str) -> None:
    """Update task phase — bound to module-level indexing_tasks."""
    _pt_update_task_phase(task_id, phase_id, status, indexing_tasks)


def _update_task_batch_info_bound(
    task_id: str, current_batch: int, total_batches: int, items_in_batch: int = 0
) -> None:
    """Update task batch info — bound to module-level indexing_tasks."""
    _pt_update_task_batch_info(
        task_id, current_batch, total_batches, indexing_tasks, items_in_batch
    )


def _update_task_stats_bound(task_id: str, **kwargs) -> None:
    """Update task stats — bound to module-level indexing_tasks."""
    _pt_update_task_stats(task_id, indexing_tasks, **kwargs)


def _mark_task_completed_bound(
    task_id: str, analysis_results: Dict, hardcodes_stored: int, storage_type: str
) -> None:
    """Mark task completed — bound to module-level indexing_tasks."""
    _pt_mark_completed(
        task_id, analysis_results, hardcodes_stored, storage_type, indexing_tasks
    )


def _mark_task_failed_bound(task_id: str, error: Exception) -> None:
    """Mark task failed — bound to module-level indexing_tasks."""
    _pt_mark_failed(task_id, error, indexing_tasks)


def _create_initial_task_state_bound() -> Dict:
    """Create initial task state with module-level config constants."""
    return _create_initial_task_state(
        CHROMADB_BATCH_SIZE, PARALLEL_BATCH_COUNT, INCREMENTAL_INDEXING_ENABLED
    )


async def _file_needs_reindex_bound(
    file_path: Path, relative_path: str, redis_client
) -> Tuple[bool, str]:
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
# Wrappers for file_analyzer functions that need injected dependencies
# =============================================================================


async def _analyze_single_file_bound(
    file_path: Path,
    root_path_obj: Path,
    redis_client=None,
) -> FileAnalysisResult:
    """Analyze single file — bound to module-level thread pool and config."""
    return await _fa_analyze_single_file(
        file_path,
        root_path_obj,
        _file_needs_reindex_bound,
        _run_in_indexing_thread,
        _store_file_hash,
        redis_client,
    )


async def _process_files_parallel_bound(
    all_files: List[Path],
    root_path_obj: Path,
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
# Core scanning functions
# =============================================================================


async def _process_single_file(
    file_path: Path,
    root_path_obj: Path,
    analysis_results: Dict,
    immediate_store_collection,
    redis_client=None,
    source_id: Optional[str] = None,
) -> Tuple[bool, bool]:
    """
    Process a single file during codebase scan.

    Issue #398: Extracted from scan_codebase to reduce method length.
    Issue #539: Added incremental indexing support.

    Returns:
        Tuple of (was_processed: bool, was_skipped_unchanged: bool)
    """
    # Use dedicated indexing thread pool for file checks
    is_file = await _run_in_indexing_thread(file_path.is_file)
    if not is_file:
        return False, False
    if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
        return False, False

    extension = file_path.suffix.lower()
    relative_path = str(file_path.relative_to(root_path_obj))
    file_category = _get_file_category(file_path)

    # Issue #539: Check if file needs reindexing (incremental mode)
    needs_reindex, current_hash = await _file_needs_reindex_bound(
        file_path, relative_path, redis_client
    )
    if not needs_reindex:
        return False, True  # Skipped - file unchanged

    analysis_results["stats"]["total_files"] += 1

    file_analysis = await _get_file_analysis(
        file_path, extension, analysis_results["stats"]
    )
    if not file_analysis:
        if current_hash and redis_client:
            await _store_file_hash(redis_client, relative_path, current_hash)
        return True, False

    _aggregate_file_analysis(
        analysis_results, file_analysis, relative_path, file_category
    )
    await _process_file_problems(
        file_analysis,
        relative_path,
        analysis_results,
        immediate_store_collection,
        file_category,
        source_id=source_id,
    )

    # Issue #539: Store file hash after successful processing
    if current_hash and redis_client:
        await _store_file_hash(redis_client, relative_path, current_hash)

    return True, False


async def _process_file_problems(
    file_analysis: Dict,
    relative_path: str,
    analysis_results: Dict,
    immediate_store_collection,
    file_category: str = FILE_CATEGORY_CODE,
    source_id: Optional[str] = None,
) -> None:
    """
    Process problems from file analysis and store to ChromaDB.

    Issue #315: extracted to reduce nesting depth in scan_codebase.
    """
    file_problems = file_analysis.get("problems", [])
    if not file_problems:
        return

    # Track starting index for batch operation
    start_idx = len(analysis_results["all_problems"])

    # Add file_path and category to each problem and collect for batch storage
    for problem in file_problems:
        problem["file_path"] = relative_path
        problem["file_category"] = file_category
        analysis_results["all_problems"].append(problem)
        # Also add to category-specific list for separate reporting
        analysis_results["problems_by_category"][file_category].append(problem)

    # Batch store all problems from this file in a single operation
    await _store_problems_batch_to_chromadb(
        immediate_store_collection,
        file_problems,
        start_idx,
        source_id=source_id,
    )


async def _iterate_files_sequential(
    all_files: list,
    root_path_obj: Path,
    analysis_results: Dict,
    immediate_store_collection,
    progress_callback,
    total_files: int,
    redis_client=None,
    source_id: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Process files sequentially (fallback when parallel mode disabled).

    Issue #620: Extracted from _iterate_and_process_files. Issue #620.
    """
    logger.info("[Issue #711] Sequential mode (parallel disabled)")
    files_processed = 0
    files_skipped = 0
    progress_interval = max(10, PARALLEL_FILE_PROCESSING // 5)

    for file_path in all_files:
        processed, skipped = await _process_single_file(
            file_path,
            root_path_obj,
            analysis_results,
            immediate_store_collection,
            redis_client,
            source_id=source_id,
        )
        if skipped:
            files_skipped += 1
        if processed:
            files_processed += 1
            if progress_callback and files_processed % progress_interval == 0:
                relative_path = str(file_path.relative_to(root_path_obj))
                await progress_callback(
                    operation="Scanning files",
                    current=files_processed,
                    total=total_files,
                    current_file=relative_path,
                )
            elif files_processed % 5 == 0:
                await asyncio.sleep(0)

    return files_processed, files_skipped


async def _iterate_and_process_files_parallel(
    all_files: list,
    root_path_obj: Path,
    immediate_store_collection,
    progress_callback,
    total_files: int,
    redis_client=None,
    source_id: Optional[str] = None,
) -> Tuple[Dict, int, int]:
    """
    Process files in parallel and return aggregated results.

    Issue #711: New parallel processing implementation.
    Issue #1710: source_id for per-project problem storage.

    Returns:
        Tuple of (analysis_results dict, files_processed, files_skipped)
    """
    import time

    start_time = time.time()

    # Process all files in parallel
    all_results = await _process_files_parallel_bound(
        all_files, root_path_obj, redis_client, progress_callback, total_files
    )

    # Single-pass aggregation (thread-safe)
    if progress_callback:
        await progress_callback(
            operation="Aggregating results",
            current=0,
            total=len(all_results),
            current_file="Aggregating analysis results...",
        )

    analysis_results = _aggregate_all_results(all_results)

    # Store all problems to ChromaDB in batch (#1710: source_id)
    if immediate_store_collection and analysis_results["all_problems"]:
        await _store_problems_batch_to_chromadb(
            immediate_store_collection,
            analysis_results["all_problems"],
            0,
            source_id=source_id,
        )

    # Calculate statistics
    files_processed = sum(1 for r in all_results if r.was_processed)
    files_skipped = sum(1 for r in all_results if r.was_skipped_unchanged)

    elapsed = time.time() - start_time
    logger.info(
        "[Parallel] Processed %d files, skipped %d, in %.2fs (%.1f files/sec)",
        files_processed,
        files_skipped,
        elapsed,
        files_processed / elapsed if elapsed > 0 else 0,
    )

    return analysis_results, files_processed, files_skipped


async def _iterate_and_process_files(
    all_files: list,
    root_path_obj: Path,
    analysis_results: Dict,
    immediate_store_collection,
    progress_callback,
    total_files: int,
    redis_client=None,
    source_id: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Iterate through files and process each one.

    Issue #398: Extracted from scan_codebase to reduce method length.
    Issue #620: Refactored with helper functions. Issue #620.
    Issue #1710: source_id for per-project problem storage.
    """
    if PARALLEL_MODE_ENABLED:
        logger.info(
            "[Issue #711] Parallel mode enabled (concurrency=%d)",
            PARALLEL_FILE_CONCURRENCY,
        )
        (
            parallel_results,
            files_processed,
            files_skipped,
        ) = await _iterate_and_process_files_parallel(
            all_files,
            root_path_obj,
            immediate_store_collection,
            progress_callback,
            total_files,
            redis_client,
            source_id=source_id,
        )
        analysis_results.update(parallel_results)
        return files_processed, files_skipped

    return await _iterate_files_sequential(
        all_files,
        root_path_obj,
        analysis_results,
        immediate_store_collection,
        progress_callback,
        total_files,
        redis_client,
        source_id=source_id,
    )


async def scan_codebase(
    root_path: Optional[str] = None,
    progress_callback: Optional[callable] = None,
    immediate_store_collection=None,
    redis_client=None,
    source_id: Optional[str] = None,
) -> Metadata:
    """
    Scan the entire codebase using MCP-like file operations.

    Issue #315, #281, #398: Uses extracted helpers for modular processing.
    Issue #539: Added redis_client param for incremental indexing support.
    Issue #620: Refactored to use helper functions.
    """
    if root_path is None:
        root_path = str(PATH.PROJECT_ROOT)

    analysis_results = _create_empty_analysis_results()

    # Issue #539: Get Redis client for incremental indexing if enabled
    if redis_client is None and INCREMENTAL_INDEXING_ENABLED:
        redis_client = await get_redis_connection()

    try:
        root_path_obj = Path(root_path)

        # Issue #620: Use helper to gather files
        total_files, all_files = await _gather_scannable_files(
            root_path_obj, progress_callback, _run_in_indexing_thread
        )

        # Process all files
        files_processed, files_skipped = await _iterate_and_process_files(
            all_files,
            root_path_obj,
            analysis_results,
            immediate_store_collection,
            progress_callback,
            total_files,
            redis_client,
            source_id=source_id,
        )

        # Issue #620: Use helper for stats logging
        _log_incremental_stats(
            files_processed, files_skipped, INCREMENTAL_INDEXING_ENABLED
        )

        # Issue #711: Statistics already calculated in parallel mode
        if not PARALLEL_MODE_ENABLED:
            _calculate_analysis_statistics(analysis_results)
        return analysis_results

    except Exception as e:
        logger.error("Error scanning codebase: %s", e)
        raise HTTPException(status_code=500, detail="Codebase scan failed")


# =============================================================================
# Progress updater factory
# =============================================================================


def _create_progress_updater(task_id: str, update_phase, update_batch_info):
    """
    Create a progress update callback for the given task.

    Issue #398: Extracted from do_indexing_with_progress to reduce method length.
    """
    from .progress_tracker import _create_progress_updater as _pt_create_updater

    return _pt_create_updater(
        task_id,
        update_phase,
        update_batch_info,
        indexing_tasks,
        _save_task_to_redis_bound,
    )


async def _init_chromadb_with_retry(
    task_id: str,
    update_progress,
    update_phase,
    source_id: Optional[str] = None,
):
    """Initialize ChromaDB collection with one retry on failure.

    Issue #398: Extracted from _run_indexing_phases.
    Issue #1249: Retry once on transient connection failure.
    Issue #1710: source_id scopes cleanup to one project.
    """
    code_collection = await _initialize_chromadb_collection(
        task_id, update_progress, update_phase, source_id=source_id
    )
    if not code_collection:
        logger.warning(
            "[Task %s] ChromaDB init failed, retrying once (#1249)",
            task_id,
        )
        await asyncio.sleep(2)
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
    source_id: Optional[str] = None,
):
    """Run codebase scan and log result counts.

    Issue #398: Extracted from _run_indexing_phases.
    Issue #1712: Log analysis result counts before batch storage.
    """
    analysis_results = await scan_codebase(
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
        "[Task %s] #1712 pre-store: %d functions, %d classes, "
        "%d problems, %d hardcodes, %d files",
        task_id,
        len(analysis_results.get("all_functions", [])),
        len(analysis_results.get("all_classes", [])),
        len(analysis_results.get("all_problems", [])),
        len(analysis_results.get("all_hardcodes", [])),
        len(analysis_results.get("files", {})),
    )
    return analysis_results


async def _run_indexing_phases(
    task_id: str,
    root_path: str,
    update_progress,
    update_phase,
    update_batch_info,
    update_stats,
    source_id: Optional[str] = None,
):
    """
    Execute the core indexing phases.

    Issue #398: Extracted from do_indexing_with_progress.
    Issue #1249: Retry ChromaDB init once on failure.
    Issue #1710: source_id scopes cleanup and metadata to one project.
    """
    code_collection = await _init_chromadb_with_retry(
        task_id, update_progress, update_phase, source_id=source_id
    )
    update_phase("init", "completed")
    update_phase("scan", "running")

    analysis_results = await _scan_and_log_analysis(
        task_id,
        root_path,
        update_progress,
        update_phase,
        update_stats,
        code_collection,
        source_id=source_id,
    )

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
            _tasks_lock,
            indexing_tasks,
        )

    hardcodes_stored = await _store_hardcodes_to_redis(
        analysis_results.get("all_hardcodes", []),
        task_id,
        source_id=source_id,
    )
    return analysis_results, hardcodes_stored


async def _handle_subprocess_crash(task_id: str, returncode: int) -> None:
    """Mark indexing task failed in Redis after subprocess crash (#1180).

    Only updates state if the subprocess did not already write a terminal
    status (completed/failed/cancelled) before crashing.
    """
    logger.error(
        "[Task %s] Indexing subprocess crashed (exit code %d)", task_id, returncode
    )
    task_data = await _load_task_from_redis(task_id) or {}
    if task_data.get("status") not in ("completed", "failed", "cancelled"):
        _mark_task_failed_bound(
            task_id,
            RuntimeError(f"Indexing subprocess crashed (exit code {returncode})"),
        )
        await _save_task_to_redis_bound(task_id)


async def _wait_with_watchdog(
    proc: asyncio.subprocess.Process,
    task_id: str,
) -> int:
    """Wait for subprocess with progress watchdog (#1341).

    Periodically checks if the subprocess is still making progress
    by reading the task state from Redis. If no progress update
    for _SUBPROCESS_PROGRESS_TIMEOUT seconds, kills the subprocess.
    """
    last_progress_hash = None
    last_progress_time = asyncio.get_running_loop().time()

    while True:
        try:
            returncode = await asyncio.wait_for(
                proc.wait(),
                timeout=_SUBPROCESS_WATCHDOG_INTERVAL,
            )
            return returncode
        except asyncio.TimeoutError:
            pass  # Process still running — check progress

        task_data = await _load_task_from_redis(task_id)
        if task_data:
            status = task_data.get("status")
            if status in ("completed", "failed", "cancelled"):
                return await proc.wait()

            progress = task_data.get("progress", {})
            progress_hash = (
                progress.get("current"),
                progress.get("total"),
                progress.get("operation"),
            )
            now = asyncio.get_running_loop().time()

            if progress_hash != last_progress_hash:
                last_progress_hash = progress_hash
                last_progress_time = now
            elif now - last_progress_time > _SUBPROCESS_PROGRESS_TIMEOUT:
                logger.error(
                    "[Task %s] Subprocess stale for %d seconds, "
                    "killing (no progress update)",
                    task_id,
                    int(now - last_progress_time),
                )
                proc.kill()
                await proc.wait()
                return -9


async def _run_indexing_subprocess(
    task_id: str, root_path: str, source_id: Optional[str] = None
) -> None:
    """Launch isolated indexing subprocess to prevent ChromaDB SIGSEGV (#1180).

    The subprocess runs do_indexing_with_progress in its own process so its
    ChromaDB PersistentClient does not conflict with the KB's concurrent
    client. If the subprocess crashes (SIGSEGV), this coroutine catches the
    non-zero exit code and marks the task failed in Redis.

    Issue #1341: Added 30-minute hard timeout and 5-minute progress watchdog.
    Issue #1710: source_id scopes indexing to one project.

    Designed as a drop-in async replacement for asyncio.create_task usage of
    do_indexing_with_progress — wrap in asyncio.create_task() as before.
    """
    worker_script = Path(__file__).parent / "indexing_worker.py"

    # Write initial state to Redis before subprocess starts so status polls
    # return "running" not "not_found" during process launch latency (#1179).
    async with _tasks_lock:
        indexing_tasks[task_id] = _create_initial_task_state_bound()
        await _save_task_to_redis_bound(task_id)

    cmd = [sys.executable, str(worker_script), task_id, root_path]
    if source_id:
        cmd.append(source_id)

    logger.info("[Task %s] Launching isolated indexing subprocess (#1180)", task_id)
    proc = await asyncio.create_subprocess_exec(*cmd)

    # Issue #1341: Wait with watchdog + hard timeout
    try:
        returncode = await asyncio.wait_for(
            _wait_with_watchdog(proc, task_id),
            timeout=_SUBPROCESS_HARD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[Task %s] Subprocess exceeded hard timeout of %d seconds",
            task_id,
            _SUBPROCESS_HARD_TIMEOUT,
        )
        proc.kill()
        await proc.wait()
        returncode = -9

    if returncode != 0:
        await _handle_subprocess_crash(task_id, returncode)
    else:
        logger.info("[Task %s] Subprocess completed successfully (rc=0)", task_id)


async def do_indexing_with_progress(
    task_id: str, root_path: str, source_id: Optional[str] = None
):
    """
    Background task: Index codebase with real-time progress updates.

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
            indexing_tasks[task_id] = _create_initial_task_state_bound()
            # #1179: Persist initial state so other workers can see task as "running"
            await _save_task_to_redis_bound(task_id)

        # Create task-specific helper closures
        def update_phase(phase_id, status):
            _update_task_phase_bound(task_id, phase_id, status)

        def update_batch_info(c, t, i=0):
            _update_task_batch_info_bound(task_id, c, t, i)

        def update_stats(**kwargs):
            _update_task_stats_bound(task_id, **kwargs)

        update_progress = _create_progress_updater(
            task_id, update_phase, update_batch_info
        )

        analysis_results, hardcodes_stored = await _run_indexing_phases(
            task_id,
            root_path,
            update_progress,
            update_phase,
            update_batch_info,
            update_stats,
            source_id=source_id,
        )

        update_phase("finalize", "running")

        # Issue #1712: Post-indexing verification — log expected vs actual
        await _verify_chromadb_storage(task_id, analysis_results)

        _mark_task_completed_bound(
            task_id, analysis_results, hardcodes_stored, "chromadb"
        )
        update_phase("finalize", "completed")
        # #1179: Persist final completed state to Redis
        await _save_task_to_redis_bound(task_id)
        logger.info("[Task %s] Indexing completed successfully", task_id)

    except Exception as e:
        logger.error("[Task %s] Indexing failed: %s", task_id, e, exc_info=True)
        _mark_task_failed_bound(task_id, e)
        # #1179: Persist failed state to Redis
        await _save_task_to_redis_bound(task_id)
