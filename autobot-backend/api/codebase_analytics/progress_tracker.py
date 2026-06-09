# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Redis task/queue and progress state management for codebase indexing.

Issue #2013: Decomposed from scanner.py god module.
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)

# Redis key prefix for file hashes (used for incremental indexing)
FILE_HASH_REDIS_PREFIX = "codebase:file_hash:"

# File hash chunk size (64KB for memory efficiency)
_FILE_HASH_CHUNK_SIZE = 65536

# Redis key prefix for task state (#1179: cross-worker visibility)
_TASK_REDIS_PREFIX = "indexing_task:"
_TASK_REDIS_TTL = TTL_24_HOURS

# Redis key for persistent index queue (#1717: survive restarts)
_QUEUE_REDIS_KEY = "codebase:index_queue"

# Note: The in-memory _index_queue lives in scanner.py (the orchestrator),
# which is the single source of truth for runtime queue state.


def _compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file for change detection.

    Issue #539: Used for incremental indexing to detect file changes.

    Args:
        file_path: Path to the file to hash

    Returns:
        SHA-256 hash string or empty string on error
    """
    try:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks for memory efficiency
            while chunk := f.read(_FILE_HASH_CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.debug("Failed to compute hash for %s: %s", file_path, e)
        return ""


async def _get_stored_file_hash(redis_client, relative_path: str) -> str | None:
    """
    Get stored file hash from Redis.

    Issue #539: Retrieves previously stored hash for incremental indexing.
    """
    if not redis_client:
        return None
    try:
        key = f"{FILE_HASH_REDIS_PREFIX}{relative_path}"
        # Issue #666: Wrap blocking Redis call in asyncio.to_thread
        stored = await asyncio.to_thread(redis_client.get, key)
        return stored.decode("utf-8") if isinstance(stored, bytes) else stored
    except Exception as e:
        logger.debug("Failed to get stored hash for %s: %s", relative_path, e)
        return None


async def _store_file_hash(redis_client, relative_path: str, file_hash: str) -> None:
    """
    Store file hash in Redis.

    Issue #539: Stores hash for future incremental indexing comparisons.
    """
    if not redis_client or not file_hash:
        return
    try:
        key = f"{FILE_HASH_REDIS_PREFIX}{relative_path}"
        # Issue #666: Wrap blocking Redis call in asyncio.to_thread
        await asyncio.to_thread(redis_client.set, key, file_hash)
    except Exception as e:
        logger.debug("Failed to store hash for %s: %s", relative_path, e)


async def _file_needs_reindex(
    file_path: Path,
    relative_path: str,
    redis_client,
    incremental_enabled: bool,
    run_in_indexing_thread,
) -> Tuple[bool, str]:
    """
    Check if a file needs to be re-indexed based on hash comparison.

    Issue #539: Core incremental indexing logic.

    Args:
        file_path: Path to the file
        relative_path: Relative path string
        redis_client: Redis client instance
        incremental_enabled: Whether incremental indexing is enabled
        run_in_indexing_thread: Callable to run sync functions in thread pool

    Returns:
        Tuple of (needs_reindex: bool, current_hash: str)
    """
    if not incremental_enabled or not redis_client:
        return True, ""

    # Issue #619: Parallelize hash computation and Redis lookup
    # Use dedicated indexing thread pool for file hash computation
    current_hash, stored_hash = await asyncio.gather(
        run_in_indexing_thread(_compute_file_hash, file_path),
        _get_stored_file_hash(redis_client, relative_path),
    )

    if not current_hash:
        return True, ""

    if stored_hash and stored_hash == current_hash:
        return False, current_hash

    return True, current_hash


async def _save_task_to_redis(task_id: str, indexing_tasks: Dict) -> None:
    """Persist task state to Redis so all uvicorn workers can read it (#1179)."""
    try:
        redis = await get_async_redis_client(database="analytics")
        if redis:
            state = indexing_tasks.get(task_id)
            if state:
                await redis.set(
                    f"{_TASK_REDIS_PREFIX}{task_id}",
                    json.dumps(state, default=str),
                    ex=_TASK_REDIS_TTL,
                )
    except Exception as e:
        logger.debug("[Task %s] Redis task state save failed (non-fatal): %s", task_id, e)


async def _load_task_from_redis(task_id: str) -> Dict | None:
    """Load task state from Redis (#1179: cross-worker visibility)."""
    try:
        redis = await get_async_redis_client(database="analytics")
        if redis:
            data = await redis.get(f"{_TASK_REDIS_PREFIX}{task_id}")
            if data:
                return json.loads(data)
    except Exception as e:
        logger.debug("[Task %s] Redis task state load failed (non-fatal): %s", task_id, e)
    return None


# =============================================================================
# Redis-backed index queue persistence (#1717)
# =============================================================================


async def _persist_queue_entry(entry: Dict) -> None:
    """Append a queue entry to Redis list (#1717)."""
    try:
        redis = await get_async_redis_client(database="analytics")
        if redis:
            await redis.rpush(_QUEUE_REDIS_KEY, json.dumps(entry, default=str))
    except Exception as e:
        logger.debug("Redis queue persist failed (non-fatal): %s", e)


async def _pop_queue_entry_redis() -> None:
    """Remove the front entry from the Redis queue (#1717)."""
    try:
        redis = await get_async_redis_client(database="analytics")
        if redis:
            await redis.lpop(_QUEUE_REDIS_KEY)
    except Exception as e:
        logger.debug("Redis queue pop failed (non-fatal): %s", e)


async def _remove_queue_entries_redis(source_id: str) -> None:
    """Remove all Redis queue entries matching *source_id* (#1717)."""
    try:
        redis = await get_async_redis_client(database="analytics")
        if not redis:
            return
        raw_items = await redis.lrange(_QUEUE_REDIS_KEY, 0, -1)
        keep = [item for item in raw_items if json.loads(item).get("source_id") != source_id]
        pipe = redis.pipeline()
        pipe.delete(_QUEUE_REDIS_KEY)
        for item in keep:
            pipe.rpush(_QUEUE_REDIS_KEY, item)
        await pipe.execute()
    except Exception as e:
        logger.debug("Redis queue remove failed (non-fatal): %s", e)


async def _load_queue_from_redis() -> List[Dict]:
    """Load all queued entries from Redis (#1717: startup recovery)."""
    try:
        redis = await get_async_redis_client(database="analytics")
        if not redis:
            return []
        raw_items = await redis.lrange(_QUEUE_REDIS_KEY, 0, -1)
        return [json.loads(item) for item in raw_items]
    except Exception as e:
        logger.debug("Redis queue load failed (non-fatal): %s", e)
        return []


async def recover_index_queue(tasks_lock: asyncio.Lock, index_queue) -> int:
    """Restore in-memory queue from Redis on startup (#1717).

    Args:
        tasks_lock: The asyncio lock protecting index_queue
        index_queue: The deque to populate with recovered entries

    Returns the number of recovered entries.
    """
    entries = await _load_queue_from_redis()
    if not entries:
        return 0
    async with tasks_lock:
        for entry in entries:
            if not any(
                e.get("source_id") == entry.get("source_id") and e.get("root_path") == entry.get("root_path")
                for e in index_queue
            ):
                index_queue.append(entry)
    logger.info("Recovered %d queued indexing jobs from Redis (#1717)", len(entries))
    return len(entries)


def _create_initial_task_state(
    chromadb_batch_size: int,
    parallel_batch_count: int,
    incremental_enabled: bool,
) -> Dict:
    """
    Create initial task state structure.

    Issue #281: extracted
    Issue #539: Added configurable batch_size and incremental indexing config

    Args:
        chromadb_batch_size: Batch size for ChromaDB storage
        parallel_batch_count: Number of parallel batches
        incremental_enabled: Whether incremental indexing is enabled
    """
    return {
        "status": "running",
        "progress": {
            "current": 0,
            "total": 0,
            "percent": 0,
            "current_file": "Initializing...",
            "operation": "Starting indexing",
        },
        "phases": {
            "current_phase": "init",
            "phases_completed": [],
            "phase_list": [
                {"id": "init", "name": "Initialization", "status": "running"},
                {"id": "scan", "name": "Scanning Files", "status": "pending"},
                {"id": "prepare", "name": "Preparing Data", "status": "pending"},
                {"id": "store", "name": "Storing to ChromaDB", "status": "pending"},
                {"id": "finalize", "name": "Finalizing", "status": "pending"},
            ],
        },
        "batches": {
            "total_batches": 0,
            "completed_batches": 0,
            "current_batch": 0,
            "batch_size": chromadb_batch_size,  # Issue #539: configurable
            "parallel_batches": parallel_batch_count,  # Issue #539: parallel processing
            "items_per_batch": [],
        },
        "stats": {
            "files_scanned": 0,
            "files_skipped": 0,  # Issue #539: incremental indexing stat
            "problems_found": 0,
            "functions_found": 0,
            "classes_found": 0,
            "items_stored": 0,
        },
        "config": {  # Issue #539: expose indexing configuration
            "batch_size": chromadb_batch_size,
            "parallel_batches": parallel_batch_count,
            "incremental_enabled": incremental_enabled,
        },
        "result": None,
        "error": None,
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _update_task_phase(task_id: str, phase_id: str, status: str, indexing_tasks: Dict) -> None:
    """
    Update phase status and track completion in task state.

    Issue #398: Extracted from do_indexing_with_progress inline helper.
    """
    phases = indexing_tasks[task_id]["phases"]
    phases["current_phase"] = phase_id
    for phase in phases["phase_list"]:
        if phase["id"] == phase_id:
            phase["status"] = status
            if status == "completed" and phase_id not in phases["phases_completed"]:
                phases["phases_completed"].append(phase_id)
            break


def _update_task_batch_info(
    task_id: str,
    current_batch: int,
    total_batches: int,
    indexing_tasks: Dict,
    items_in_batch: int = 0,
) -> None:
    """
    Update batch progress tracking for indexing task.

    Issue #398: Extracted from do_indexing_with_progress inline helper.
    """
    batches = indexing_tasks[task_id]["batches"]
    batches["current_batch"] = current_batch
    batches["total_batches"] = total_batches
    if items_in_batch > 0 and current_batch > len(batches["items_per_batch"]):
        batches["items_per_batch"].append(items_in_batch)


def _update_task_stats(task_id: str, indexing_tasks: Dict, **kwargs) -> None:
    """
    Update task statistics with provided key-value pairs.

    Issue #398: Extracted from do_indexing_with_progress inline helper.
    """
    for key, value in kwargs.items():
        if key in indexing_tasks[task_id]["stats"]:
            indexing_tasks[task_id]["stats"][key] = value


async def _invalidate_quality_cache() -> None:
    """Invalidate code_quality:latest* Redis keys after a scan changes ChromaDB.

    Issue #6669: The Code Quality Dashboard caches calculated metrics in Redis
    for 5 minutes (analytics_quality.py:130). Without invalidation, the
    dashboard serves pre-scan results until that TTL elapses. We use a
    pattern-delete so both the global ``code_quality:latest`` key and any
    per-source ``code_quality:latest:{source_root}`` variants are cleared.
    """
    try:
        redis = await get_async_redis_client(database="analytics")
        if not redis:
            return
        keys = await redis.keys("code_quality:latest*")
        if keys:
            await redis.delete(*keys)
            logger.info("Invalidated %d quality cache key(s) after scan", len(keys))
    except Exception as exc:
        logger.warning("Quality cache invalidation failed: %s", exc)


def _mark_task_completed(
    task_id: str,
    analysis_results: Dict,
    hardcodes_stored: int,
    storage_type: str,
    indexing_tasks: Dict,
) -> None:
    """
    Mark indexing task as completed with results.

    Issue #398: Extracted from do_indexing_with_progress.
    Issue #6669: Invalidate the Code Quality Dashboard's Redis cache so the
    UI surfaces fresh scan output instead of serving 5-minute-stale results.
    """
    indexing_tasks[task_id]["status"] = "completed"
    total_files = analysis_results["stats"]["total_files"]
    indexing_tasks[task_id]["result"] = {
        "status": "success",
        "message": (
            f"Indexed {total_files} files, found {hardcodes_stored} hardcodes " f"using {storage_type} storage"
        ),
        "stats": analysis_results["stats"],
        "hardcodes_count": hardcodes_stored,
        "storage_type": storage_type,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    indexing_tasks[task_id]["completed_at"] = datetime.now(tz=timezone.utc).isoformat()
    # Fire-and-forget cache invalidation; safe in any running-loop context
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_invalidate_quality_cache())
    except RuntimeError:
        # No running loop (called from a sync context); run a one-shot
        run_or_schedule(_invalidate_quality_cache())


def _mark_task_failed(task_id: str, error: Exception, indexing_tasks: Dict) -> None:
    """
    Mark indexing task as failed with error.

    Issue #398: Extracted from do_indexing_with_progress.
    """
    indexing_tasks[task_id]["status"] = "failed"
    indexing_tasks[task_id]["error"] = str(error)
    indexing_tasks[task_id]["failed_at"] = datetime.now(tz=timezone.utc).isoformat()


def _create_progress_updater(
    task_id: str,
    update_phase,
    update_batch_info,
    indexing_tasks: Dict,
    save_task_to_redis,
):
    """
    Create a progress update callback for the given task.

    Issue #398: Extracted from do_indexing_with_progress to reduce method length.

    Args:
        task_id: The task identifier
        update_phase: Callable to update task phase
        update_batch_info: Callable to update batch info
        indexing_tasks: Shared dict of indexing tasks
        save_task_to_redis: Async callable to persist task state
    """

    async def update_progress(
        operation: str,
        current: int,
        total: int,
        current_file: str,
        phase: str = None,
        batch_info: dict = None,
    ):
        percent = int((current / total * 100)) if total > 0 else 0
        indexing_tasks[task_id]["progress"] = {
            "current": current,
            "total": total,
            "percent": percent,
            "current_file": current_file,
            "operation": operation,
        }
        if phase:
            update_phase(phase, "running")
        if batch_info:
            update_batch_info(
                batch_info.get("current", 0),
                batch_info.get("total", 0),
                batch_info.get("items", 0),
            )
        logger.debug(
            "[Task %s] Progress: %s - %s/%s (%s%)",
            task_id,
            operation,
            current,
            total,
            percent,
        )
        # #1179: Persist state to Redis so other workers can read it
        await save_task_to_redis(task_id)

    return update_progress
