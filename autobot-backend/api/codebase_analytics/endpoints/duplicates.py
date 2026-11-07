# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Duplicate code detection endpoints (Issue #528)

Provides:
- On-demand duplicate code detection using DuplicateCodeDetector
- Cached results in ChromaDB for persistence

Issue #554: Enhanced with semantic analysis support:
- Optional LLM-based semantic duplicate detection
- Redis caching for analysis results
- ChromaDB vector embeddings for code similarity
"""

import asyncio
import threading
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api.codebase_analytics.source_scope import SourceIdQuery, cached_task_result, source_scoped_prefix
from api.codebase_analytics.task_routes import add_clear_stuck_route
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, bounded, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import AnalyticsConfig
from tasks.analytics_tasks import run_duplicate_analysis
from utils.cancel_tokens import new_cancel_token, signal_cancel_token, submit_cancellable
from utils.celery_task_status import known_task_status_or_404, store_latest_task_id
from utils.io_executor import get_analytics_executor

from ..duplicate_detector import DuplicateCodeDetector, detect_duplicates_async
from .duplicate_results import (  # noqa: F401  (re-exported: the Celery task and tests import them from here)
    _build_detection_error_response,
    _convert_analysis_to_result,
    _convert_config_duplicates_to_array,
    _get_chromadb_fallback,
    _run_semantic_config_detection,
    _run_standard_config_detection,
)
from .scan_responses import (
    BACKGROUND_SCAN_TIMEOUT_SECONDS,
    ORPHAN_LEASE_SECONDS,
    ScanBusy,
    ScanHolder,
    ScanTimedOut,
    ScanUnavailable,
    response_for,
)
from .shared import UnresolvedSourceError, resolve_scan_root

logger = get_logger(__name__)

# #12779: single-flight guard for the duplicate scan.
#
# asyncio.wait_for cancels the AWAIT, but work already running in a
# ThreadPoolExecutor cannot be cancelled. So each timeout returned None to the
# caller while the worker thread kept walking the entire tree, and every
# subsequent poll queued ANOTHER full scan. Abandoned threads accumulated until
# they saturated CPU and pushed RSS 2.8 -> 7.0 GB, at which point /api/health
# stopped answering and the GUI reported "Backend API Unreachable" for a process
# that was alive the whole time.
#
# Only one scan may be in flight; concurrent callers are told it is running
# instead of starting a second walk, and a timed-out scan has its cancel token
# set so the orphaned thread stops cooperatively rather than running to
# completion for a result nobody will read.
_duplicate_scan_lock = threading.Lock()
_scan_holder: ScanHolder | None = None
_duplicate_scan_cancel: threading.Event | None = None

router = APIRouter()

_REDIS_PREFIX = "dup_task:"

# Cache for duplicate analysis (in-memory, refreshed on demand)
# Keyed by source_id (or "" for unscoped) to prevent cross-project leakage (#3685)
_duplicate_cache: dict[str, dict] = {}


async def _run_semantic_analysis(project_root: str, min_similarity: float):
    """
    Run semantic duplicate analysis using LLM embeddings.

    Args:
        project_root: Root directory to analyze
        min_similarity: Minimum similarity threshold

    Returns:
        Analysis result or None if failed
    """
    try:
        analysis = await detect_duplicates_async(
            project_root=project_root,
            min_similarity=min_similarity,
            use_semantic_analysis=True,
        )
        logger.info("Semantic duplicate analysis complete")
        return analysis
    except Exception as e:
        logger.warning("Semantic analysis failed, falling back to standard: %s", e)
        return None


def _take_scan_lock() -> threading.Lock:
    """Take the single-flight lock, or raise ``ScanBusy`` saying how long it has been held.

    #18013: a lock whose holder was told to stop but never exited is reclaimed
    once ``ORPHAN_LEASE_SECONDS`` has passed. Release is deliberately deferred to
    the executor thread's done-callback (#13602), so a thread that never exits
    would otherwise decline every later call for the life of the process. The old
    lock object is abandoned, not released: the late callback releases the
    object it captured, so it can never free a lock a newer scan owns.
    """
    global _duplicate_scan_lock, _scan_holder
    now = time.monotonic()
    lock = _duplicate_scan_lock
    if not lock.acquire(blocking=False):
        holder = _scan_holder
        leaked = (
            holder is not None and holder.orphaned_at is not None and now - holder.orphaned_at > ORPHAN_LEASE_SECONDS
        )
        if not leaked:
            raise ScanBusy(None if holder is None else now - holder.started)
        logger.error(
            "Duplicate scan lock reclaimed: the abandoned scan has not exited %.0fs after it was told to stop",
            now - holder.orphaned_at,
        )
        lock = _duplicate_scan_lock = threading.Lock()
        lock.acquire()
    _scan_holder = ScanHolder(started=now)
    return lock


def _abandon_scan(lock: threading.Lock, future, cancel_token, reason: str) -> None:
    """Tell the orphaned scan to stop; the lock stays held until its thread exits (#13602)."""
    signal_cancel_token("duplicate_detection", cancel_token, reason)
    if _scan_holder is not None:
        _scan_holder.orphaned_at = time.monotonic()
    future.add_done_callback(lambda _f: lock.release())


async def _run_standard_analysis(project_root: str, min_similarity: float, background: bool = False):
    """
    Run standard duplicate analysis in the analytics executor.

    Returns the analysis, or raises ``ScanBusy`` (a scan is already in flight)
    or ``ScanTimedOut`` (it ran and exceeded its deadline). Two conditions that
    used to share one ``None`` (#18013).

    ``background`` is the Celery task: it is bounded by
    ``BACKGROUND_SCAN_TIMEOUT_SECONDS`` instead of the request deadline, which
    the queued path exists to escape (#18067).

    Issue #14256: submission goes through ``utils.cancel_tokens.submit_cancellable``
    so ``bounded()`` can also signal the token. The single-flight lock stays
    call-site-specific: releasing it only once the orphaned thread exits is this
    endpoint's own bookkeeping.
    """
    global _duplicate_scan_cancel

    lock = _take_scan_lock()
    deadline = BACKGROUND_SCAN_TIMEOUT_SECONDS if background else AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT
    released = False
    cancel_token = new_cancel_token()
    # Issue #1233: dedicated analytics executor, so a scan cannot starve the default pool.
    future, _ = submit_cancellable(
        get_analytics_executor(),
        lambda: DuplicateCodeDetector(
            project_root=project_root,
            min_similarity=min_similarity,
            cancel_token=cancel_token,
        ).run_analysis(),
        operation="duplicate_detection",
        cancel_token=cancel_token,
    )
    _duplicate_scan_cancel = cancel_token
    try:
        analysis = await asyncio.wait_for(asyncio.shield(future), timeout=deadline)
        lock.release()
        released = True
        return analysis
    except asyncio.TimeoutError:
        _abandon_scan(lock, future, cancel_token, f"exceeded its {deadline}s deadline")
        released = True
        logger.warning("Duplicate detection timed out after %ss; holding the lock until the orphan exits", deadline)
        raise ScanTimedOut(deadline) from None
    except asyncio.CancelledError:
        # #13602: CancelledError is not TimeoutError, so without this the lock
        # was released with the token never set and the shielded orphan kept
        # burning an executor thread.
        _abandon_scan(lock, future, cancel_token, "cancelled before its own deadline")
        released = True
        logger.warning("Duplicate detection cancelled — signalled the orphaned scan to stop")
        raise
    finally:
        if not released:
            lock.release()


def _unresolved_source_response() -> JSONResponse:
    """The refusal, once. Detail is logged, never returned: CWE-209."""
    logger.warning("duplicate scan refused: source_id did not resolve")
    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": "source_id does not resolve to a code source; nothing scanned"},
    )


def _process_and_cache_analysis(analysis, project_root: str, source_id: str | None = None) -> dict:
    """
    Convert analysis to result dict and log completion.

    Issue #620: Extracted from get_duplicate_code to reduce function length.
    Issue #3685: Keyed by source_id to prevent cross-project cache leakage.

    Args:
        analysis: Analysis result object
        project_root: Project root path
        source_id: Optional source ID for per-project cache scoping

    Returns:
        Result dict suitable for JSONResponse
    """
    result = _convert_analysis_to_result(analysis, project_root)
    _duplicate_cache[source_id or ""] = result

    logger.info(
        "Duplicate analysis complete: %d duplicates (%d high, %d medium, %d low)",
        analysis.total_duplicates,
        analysis.high_similarity_count,
        analysis.medium_similarity_count,
        analysis.low_similarity_count,
    )

    return result


async def _run_duplicate_analysis(
    project_root: str, min_similarity: float, use_semantic: bool, background: bool = False
):
    """
    Run duplicate analysis with semantic or standard detection.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Args:
        project_root: Root directory to analyze
        min_similarity: Minimum similarity threshold
        use_semantic: Whether to use semantic analysis
        background: run as the Celery task (no request deadline), see ``_run_standard_analysis``

    Returns:
        The analysis. Raises ``ScanBusy`` / ``ScanTimedOut`` when there is none (#18013).
    """
    analysis = None

    if use_semantic:
        analysis = await _run_semantic_analysis(project_root, min_similarity)

    if analysis is None:
        analysis = await _run_standard_analysis(project_root, min_similarity, background=background)

    return analysis


def _check_duplicate_cache(refresh: bool, source_id: str | None = None) -> JSONResponse | None:
    """
    Check if cached results are available and return them.

    Issue #620: Extracted from get_duplicate_code to reduce function length.
    Issue #3685: Keyed by source_id to prevent cross-project cache leakage.

    Args:
        refresh: Whether to force fresh analysis
        source_id: Optional source ID for per-project cache scoping

    Returns:
        JSONResponse with cached data, or None if cache miss/refresh requested
    """
    cached = _duplicate_cache.get(source_id or "")
    if cached and not refresh:
        logger.info(
            "Returning cached duplicate analysis (%d duplicates)",
            cached.get("total_count", 0),
        )
        return JSONResponse(cached)
    return None


async def _handle_detection_failure(error: Exception, source_id: str | None = None) -> JSONResponse:
    """
    Handle duplicate detection failure with fallback.

    Issue #620: Extracted from get_duplicate_code to reduce function length.
    Issue #1772: source_id scopes fallback to per-project data.

    Args:
        error: Exception that occurred
        source_id: Optional source ID for per-project scoping

    Returns:
        JSONResponse with fallback data or error response
    """
    logger.error("Duplicate detection failed: %s", error, exc_info=True)

    fallback = await asyncio.to_thread(_get_chromadb_fallback, str(error), source_id)
    if fallback:
        return JSONResponse(fallback)

    resp = _build_detection_error_response()
    return JSONResponse(resp)


@router.get("/duplicates")
@bounded(180.0)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_duplicate_code",
    error_code_prefix="CODEBASE",
)
async def get_duplicate_code(
    refresh: bool = Query(False, description="Force fresh analysis instead of cache"),
    min_similarity: float = Query(0.5, description="Minimum similarity threshold (0.0-1.0)"),
    use_semantic: bool = Query(False, description="Enable LLM-based semantic analysis (Issue #554)"),
    source_id: str | None = Query(None, description="#1772: source_id for per-project scoping"),
):
    """
    Get duplicate code detected in the codebase (Issue #528).

    Uses the DuplicateCodeDetector for real analysis of:
    - Exact hash matches (100% similarity)
    - Near-duplicate code blocks (token-based similarity)
    - Semantic duplicates via LLM embeddings (Issue #554, when use_semantic=True)

    Args:
        refresh: Force fresh analysis instead of using cached results
        min_similarity: Minimum similarity threshold (0.5 = 50%)
        use_semantic: Enable LLM-based semantic duplicate detection (Issue #554)

    Returns:
        JSON with duplicates, statistics, and analysis metadata
    """
    # Was a FOURTH private copy of the block `shared.resolve_source_root` was
    # extracted for (#2760, which missed this file); the copy then missed
    # #17758's fix and swallowed every failure into logger.debug, scanning
    # AutoBot's own tree under the caller's key. `strict` follows what the
    # CALLER supplied: naming nothing is not the same as naming a ghost.
    try:
        project_root = str(await resolve_scan_root(source_id, strict=bool(source_id)))
    except UnresolvedSourceError:
        return _unresolved_source_response()

    # Cache read AFTER resolution: keyed by source_id, so reading it first
    # serves a stale result for a source that no longer resolves (CodeRabbit).
    cached = _check_duplicate_cache(refresh, source_id=source_id)
    if cached:
        return cached

    try:
        # Run analysis (semantic or standard) - Issue #620: Use helper
        analysis = await _run_duplicate_analysis(project_root, min_similarity, use_semantic)

        # Convert, cache, and return results - Issue #620, #3685: Scoped by source_id
        result = _process_and_cache_analysis(analysis, project_root, source_id=source_id)
        return JSONResponse(result)

    except ScanUnavailable as exc:
        # #18013: busy and timed-out are different answers; neither is cached.
        return JSONResponse(response_for(exc))
    except Exception as e:
        # Issue #620: Use helper for error handling
        return await _handle_detection_failure(e, source_id=source_id)


@router.get("/config-duplicates")
@bounded(180.0)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_config_duplicates",
    error_code_prefix="CODEBASE",
)
async def detect_config_duplicates_endpoint(
    use_semantic: bool = Query(False, description="Enable LLM-based semantic analysis (Issue #554)"),
    source_id: str | None = Query(None, description="#3685: source_id for per-project scoping"),
):
    """
    Detect configuration value duplicates across codebase (Issue #341).

    Issue #554: Enhanced with optional semantic analysis.
    Issue #620: Refactored to use helper functions.
    Issue #3685: source_id scopes analysis to the correct project clone.

    Args:
        use_semantic: Enable semantic duplicate detection via LLM embeddings
        source_id: Optional source ID to scope analysis to the correct project

    Returns:
        JSONResponse with duplicate detection results
    """
    # #17982: the second copy of the same block. Same reasoning as the scan
    # above -- a named source that does not resolve is an error, not a cue to
    # substitute AutoBot's own tree.
    try:
        project_root = await resolve_scan_root(source_id, strict=bool(source_id))
    except UnresolvedSourceError:
        return _unresolved_source_response()

    # Issue #620: Use helpers for detection
    result = None
    if use_semantic:
        result = await _run_semantic_config_detection(project_root)

    if result is None:
        result = await _run_standard_config_detection(project_root)

    if result.get("files_scanned", 0) == 0:
        # #18067: "scanned nothing" is not "found nothing". This answered a
        # clean 200 "No configuration duplicates found!" in 0.7s for a tree it
        # had not read a single file of.
        logger.warning("config-duplicates scanned 0 files under %s", project_root)
        return JSONResponse(
            status_code=422,
            content={"status": "error", "message": "no Python files were scanned; nothing to report"},
        )

    # Issue #620: Use helper for array conversion
    duplicates_array = _convert_config_duplicates_to_array(result["duplicates"])

    return JSONResponse(
        {
            "status": "success",
            "duplicates_found": result["duplicates_found"],
            "duplicates": duplicates_array,
            "report": result["report"],
            "files_scanned": result["files_scanned"],
            "files_failed": result.get("files_failed", 0),
            "scope": result.get("scope", ""),
        }
    )


# ------------------------------------------------------------------
# Background task endpoints (#1304)
# ------------------------------------------------------------------


@router.get("/duplicates/cached")
@bounded(180.0)
async def get_cached_duplicate_result(source_id: SourceIdQuery):
    """Return the latest completed duplicate analysis result (#1540)."""
    return await cached_task_result(_REDIS_PREFIX, source_id)


@router.post("/duplicates/analyze")
@bounded(180.0)
async def start_duplicate_analysis(source_id: SourceIdQuery):
    """Enqueue duplicate analysis as a Celery task (GH#6505)."""
    result = run_duplicate_analysis.delay(source_id)
    await store_latest_task_id(source_scoped_prefix(_REDIS_PREFIX, source_id), result.id)
    return {"task_id": result.id, "status": "pending"}


@router.get("/duplicates/status/{task_id}", dependencies=[Depends(get_current_user)])
@bounded(180.0)
async def get_duplicate_status(task_id: str):
    """Get duplicate analysis task status."""
    return known_task_status_or_404(task_id)


add_clear_stuck_route(router, "/duplicates/tasks/clear-stuck", name="clear_stuck_dup_tasks", bounded_s=180.0)
