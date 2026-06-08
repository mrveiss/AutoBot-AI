# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
File iteration and processing pipeline for codebase scanning.

Issue #2364: Extracted from scanner.py to isolate the file-level processing
pipeline from the higher-level orchestration logic.

Public functions
----------------
- _get_file_analysis           — dispatch file analysis by extension
- _process_file_problems       — persist problems from one file to ChromaDB
- _process_single_file         — drive analysis + storage for one file
- _iterate_files_sequential    — sequential fallback iterator
- _iterate_and_process_files_parallel — parallel batch iterator
- _iterate_and_process_files   — dispatcher: parallel vs sequential
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from utils.file_categorization import FILE_CATEGORY_CODE, SKIP_DIRS
from utils.file_categorization import get_file_category as _get_file_category

from .analyzers import (
    analyze_documentation_file,
    analyze_javascript_vue_file,
    analyze_python_file,
)
from .chromadb_storage import _store_problems_batch_to_chromadb
from .file_analyzer import (
    _FILE_TYPE_MAP,
    PARALLEL_FILE_CONCURRENCY,
    PARALLEL_MODE_ENABLED,
)
from .progress_tracker import _store_file_hash
from .stats_aggregation import _aggregate_all_results, _aggregate_file_analysis

logger = get_logger(__name__)


async def _get_file_analysis(
    file_path: Path,
    extension: str,
    stats: dict,
) -> dict | None:
    """Dispatch file analysis by extension.

    Issue #315, #367, #398: Refactored with mapping table for reduced complexity.
    """
    for ext_set, stat_key, analyzer_type in _FILE_TYPE_MAP:
        if extension in ext_set:
            stats[stat_key] += 1
            if analyzer_type == "python":
                return await analyze_python_file(str(file_path))
            elif analyzer_type == "js":
                # Issue #666: Wrap blocking file I/O in asyncio.to_thread
                return await asyncio.to_thread(analyze_javascript_vue_file, str(file_path))
            elif analyzer_type == "doc":
                # Issue #666: Wrap blocking file I/O in asyncio.to_thread
                return await asyncio.to_thread(analyze_documentation_file, str(file_path))
            return None

    stats["other_files"] += 1
    return None


async def _process_file_problems(
    file_analysis: Dict,
    relative_path: str,
    analysis_results: Dict,
    immediate_store_collection,
    file_category: str = FILE_CATEGORY_CODE,
    source_id: str | None = None,
) -> None:
    """Process problems from file analysis and store to ChromaDB.

    Issue #315: extracted to reduce nesting depth in scan_codebase.
    """
    file_problems = file_analysis.get("problems", [])
    if not file_problems:
        return

    start_idx = len(analysis_results["all_problems"])

    for problem in file_problems:
        problem["file_path"] = relative_path
        problem["file_category"] = file_category
        analysis_results["all_problems"].append(problem)
        analysis_results["problems_by_category"][file_category].append(problem)

    await _store_problems_batch_to_chromadb(
        immediate_store_collection,
        file_problems,
        start_idx,
        source_id=source_id,
    )


async def _process_single_file(
    file_path: Path,
    root_path_obj: Path,
    analysis_results: Dict,
    immediate_store_collection,
    file_needs_reindex_fn,
    run_in_thread_fn,
    redis_client=None,
    source_id: str | None = None,
) -> Tuple[bool, bool]:
    """Process one file: check, analyse, aggregate, and store.

    Issue #398: Extracted from scan_codebase. Issue #539: incremental indexing.
    Returns (was_processed, was_skipped_unchanged).
    """
    is_file = await run_in_thread_fn(file_path.is_file)
    if not is_file:
        return False, False
    if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
        return False, False

    extension = file_path.suffix.lower()
    relative_path = str(file_path.relative_to(root_path_obj))
    file_category = _get_file_category(file_path)

    needs_reindex, current_hash = await file_needs_reindex_fn(file_path, relative_path, redis_client)
    if not needs_reindex:
        return False, True

    analysis_results["stats"]["total_files"] += 1

    file_analysis = await _get_file_analysis(file_path, extension, analysis_results["stats"])
    if not file_analysis:
        if current_hash and redis_client:
            await _store_file_hash(redis_client, relative_path, current_hash)
        return True, False

    _aggregate_file_analysis(analysis_results, file_analysis, relative_path, file_category)
    await _process_file_problems(
        file_analysis,
        relative_path,
        analysis_results,
        immediate_store_collection,
        file_category,
        source_id=source_id,
    )

    if current_hash and redis_client:
        await _store_file_hash(redis_client, relative_path, current_hash)

    return True, False


async def _iterate_files_sequential(
    all_files: List[Path],
    root_path_obj: Path,
    analysis_results: Dict,
    immediate_store_collection,
    progress_callback,
    total_files: int,
    file_needs_reindex_fn,
    run_in_thread_fn,
    parallel_file_processing: int,
    redis_client=None,
    source_id: str | None = None,
) -> Tuple[int, int]:
    """Process files sequentially (fallback when parallel mode disabled).

    Issue #620: Extracted from _iterate_and_process_files.

    Parameters
    ----------
    file_needs_reindex_fn / run_in_thread_fn:
        Injected callables — see ``_process_single_file`` for signatures.
    parallel_file_processing:
        Progress-update interval denominator (from PARALLEL_FILE_PROCESSING).
    """
    logger.info("[Issue #711] Sequential mode (parallel disabled)")
    files_processed = 0
    files_skipped = 0
    progress_interval = max(10, parallel_file_processing // 5)

    for file_path in all_files:
        processed, skipped = await _process_single_file(
            file_path,
            root_path_obj,
            analysis_results,
            immediate_store_collection,
            file_needs_reindex_fn,
            run_in_thread_fn,
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
    all_files: List[Path],
    root_path_obj: Path,
    immediate_store_collection,
    progress_callback,
    total_files: int,
    process_files_parallel_fn,
    redis_client=None,
    source_id: str | None = None,
) -> Tuple[Dict, int, int]:
    """Process files in parallel and return aggregated results.

    Issue #711: New parallel processing implementation.
    Issue #1710: source_id for per-project problem storage.

    Parameters
    ----------
    process_files_parallel_fn:
        Async callable with the same signature as
        ``file_analyzer._process_files_parallel`` but bound to injected
        thread-pool/hash helpers.

    Returns
    -------
    (analysis_results, files_processed, files_skipped)
    """
    import time

    start_time = time.time()

    all_results = await process_files_parallel_fn(
        all_files, root_path_obj, redis_client, progress_callback, total_files
    )

    if progress_callback:
        await progress_callback(
            operation="Aggregating results",
            current=0,
            total=len(all_results),
            current_file="Aggregating analysis results...",
        )

    analysis_results = _aggregate_all_results(all_results)

    if immediate_store_collection and analysis_results["all_problems"]:
        await _store_problems_batch_to_chromadb(
            immediate_store_collection,
            analysis_results["all_problems"],
            0,
            source_id=source_id,
        )

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
    all_files: List[Path],
    root_path_obj: Path,
    analysis_results: Dict,
    immediate_store_collection,
    progress_callback,
    total_files: int,
    file_needs_reindex_fn,
    run_in_thread_fn,
    process_files_parallel_fn,
    parallel_file_processing: int,
    redis_client=None,
    source_id: str | None = None,
) -> Tuple[int, int]:
    """Dispatch file iteration to parallel or sequential mode.

    Issue #398: Extracted from scan_codebase to reduce method length.
    Issue #620: Refactored with helper functions.
    Issue #1710: source_id for per-project problem storage.
    """
    if PARALLEL_MODE_ENABLED:
        logger.info(
            "[Issue #711] Parallel mode enabled (concurrency=%d)",
            PARALLEL_FILE_CONCURRENCY,
        )
        parallel_results, files_processed, files_skipped = await _iterate_and_process_files_parallel(
            all_files,
            root_path_obj,
            immediate_store_collection,
            progress_callback,
            total_files,
            process_files_parallel_fn,
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
        file_needs_reindex_fn,
        run_in_thread_fn,
        parallel_file_processing,
        redis_client,
        source_id=source_id,
    )
