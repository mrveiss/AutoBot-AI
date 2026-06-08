# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Per-file analysis orchestration for codebase analytics.

Issue #2013: Decomposed from scanner.py god module.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from utils.file_categorization import (
    ALL_CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    CSS_EXTENSIONS,
    DOC_EXTENSIONS,
    HTML_EXTENSIONS,
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    SKIP_DIRS,
    TS_EXTENSIONS,
    VUE_EXTENSIONS,
)
from utils.file_categorization import get_file_category as _get_file_category

from .analyzers import (
    analyze_documentation_file,
    analyze_javascript_vue_file,
    analyze_python_file,
)
from .types import FileAnalysisResult

logger = get_logger(__name__)

# =============================================================================
# Issue #711: Parallel file processing configuration
# =============================================================================

# Issue #711: Parallel file processing concurrency
# Controls how many files can be analyzed concurrently during scanning
# Higher values = faster scanning but more memory/CPU usage
# Default: 50, Range: 1-200
try:
    _parallel_concurrency = int(config.codebase_index_parallel_files)
    PARALLEL_FILE_CONCURRENCY = max(1, min(_parallel_concurrency, 200))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_PARALLEL_FILES, using default 50")
    PARALLEL_FILE_CONCURRENCY = 50

# Issue #711: Enable parallel file processing mode
# When True, files are processed in parallel using asyncio.gather with semaphore
# When False, falls back to sequential processing (original behavior)
# Default: True (parallel mode enabled)
PARALLEL_MODE_ENABLED = config.codebase_parallel_mode.lower() == "true"


# Issue #398: File type mapping for cleaner dispatch
_FILE_TYPE_MAP = [
    (PYTHON_EXTENSIONS, "python_files", "python"),
    (JS_EXTENSIONS, "javascript_files", "js"),
    (TS_EXTENSIONS, "typescript_files", "js"),
    (VUE_EXTENSIONS, "vue_files", "js"),
    (CSS_EXTENSIONS, "css_files", "js"),
    (HTML_EXTENSIONS, "html_files", "js"),
    (CONFIG_EXTENSIONS, "config_files", None),
    (DOC_EXTENSIONS, "doc_files", "doc"),
    (ALL_CODE_EXTENSIONS, "other_code_files", "js"),
]


def _determine_analyzer_type(extension: str) -> Tuple[str | None, str]:
    """
    Determine analyzer type and stat key from file extension.

    Issue #711: Extracted helper for _analyze_single_file.

    Args:
        extension: File extension (lowercase, e.g., ".py")

    Returns:
        Tuple of (analyzer_type, stat_key)
    """
    for ext_set, s_key, a_type in _FILE_TYPE_MAP:
        if extension in ext_set:
            return a_type, s_key
    return None, "other_files"


async def _run_file_analyzer(
    file_path: Path,
    analyzer_type: str | None,
) -> Dict | None:
    """
    Run the appropriate analyzer for a file.

    Issue #711: Extracted helper for _analyze_single_file.

    Args:
        file_path: Path to the file to analyze
        analyzer_type: Type of analyzer ("python", "js", "doc", None)

    Returns:
        Analysis dict or None if no analyzer or error
    """
    try:
        if analyzer_type == "python":
            return await analyze_python_file(str(file_path))
        elif analyzer_type == "js":
            return await asyncio.to_thread(analyze_javascript_vue_file, str(file_path))
        elif analyzer_type == "doc":
            return await asyncio.to_thread(analyze_documentation_file, str(file_path))
    except Exception as e:
        logger.debug("Error analyzing file %s: %s", file_path, e)
    return None


def _enrich_items_with_metadata(
    items: List[Dict],
    relative_path: str,
    file_category: str,
) -> List[Dict]:
    """
    Add file_path and file_category to analysis items.

    Issue #711: Extracted helper for _build_file_analysis_result.

    Args:
        items: List of item dicts (functions, classes, etc.)
        relative_path: Relative path to add
        file_category: Category to add

    Returns:
        New list with enriched items
    """
    enriched = []
    for item in items:
        item_copy = dict(item)
        item_copy["file_path"] = relative_path
        item_copy["file_category"] = file_category
        enriched.append(item_copy)
    return enriched


def _build_file_analysis_result(
    file_path: Path,
    relative_path: str,
    extension: str,
    file_category: str,
    file_hash: str,
    file_analysis: Dict,
    analyzer_type: str | None,
    stat_key: str,
) -> FileAnalysisResult:
    """
    Build FileAnalysisResult from analysis dict.

    Issue #711: Extracted helper for _analyze_single_file.
    """
    return FileAnalysisResult(
        file_path=file_path,
        relative_path=relative_path,
        extension=extension,
        file_category=file_category,
        was_processed=True,
        was_skipped_unchanged=False,
        file_hash=file_hash,
        functions=_enrich_items_with_metadata(file_analysis.get("functions", []), relative_path, file_category),
        classes=_enrich_items_with_metadata(file_analysis.get("classes", []), relative_path, file_category),
        imports=file_analysis.get("imports", []),
        hardcodes=_enrich_items_with_metadata(file_analysis.get("hardcodes", []), relative_path, file_category),
        problems=_enrich_items_with_metadata(file_analysis.get("problems", []), relative_path, file_category),
        technical_debt=file_analysis.get("technical_debt", []),
        line_count=file_analysis.get("line_count", 0),
        code_lines=file_analysis.get("code_lines", 0),
        comment_lines=file_analysis.get("comment_lines", 0),
        docstring_lines=file_analysis.get("docstring_lines", 0),
        blank_lines=file_analysis.get("blank_lines", 0),
        documentation_lines=file_analysis.get("documentation_lines", 0),
        analyzer_type=analyzer_type,
        stat_key=stat_key,
    )


def _build_unchanged_file_result(
    file_path: Path,
    relative_path: str,
    extension: str,
    file_category: str,
    file_hash: str,
) -> FileAnalysisResult:
    """
    Build result for unchanged file that was skipped.

    Issue #620: Extracted from _analyze_single_file.
    """
    return FileAnalysisResult(
        file_path=file_path,
        relative_path=relative_path,
        extension=extension,
        file_category=file_category,
        was_processed=False,
        was_skipped_unchanged=True,
        file_hash=file_hash,
    )


def _build_empty_analysis_result(
    file_path: Path,
    relative_path: str,
    extension: str,
    file_category: str,
    file_hash: str,
    analyzer_type: str,
    stat_key: str,
) -> FileAnalysisResult:
    """
    Build result when file analysis returns no data.

    Issue #620: Extracted from _analyze_single_file.
    """
    return FileAnalysisResult(
        file_path=file_path,
        relative_path=relative_path,
        extension=extension,
        file_category=file_category,
        was_processed=True,
        was_skipped_unchanged=False,
        file_hash=file_hash,
        analyzer_type=analyzer_type,
        stat_key=stat_key,
    )


def _build_base_file_metadata(
    file_path: Path,
    root_path_obj: Path,
) -> Tuple[str, str, str, FileAnalysisResult]:
    """Helper for _analyze_single_file. Ref: #1088.

    Computes extension, relative_path, file_category, and a base FileAnalysisResult
    suitable for returning when the file is invalid or should be skipped.

    Returns:
        Tuple of (extension, relative_path, file_category, base_result)
    """
    extension = file_path.suffix.lower()
    relative_path = str(file_path.relative_to(root_path_obj))
    file_category = _get_file_category(file_path)
    base_result = FileAnalysisResult(
        file_path=file_path,
        relative_path=relative_path,
        extension=extension,
        file_category=file_category,
    )
    return extension, relative_path, file_category, base_result


async def _run_analysis_and_build_result(
    file_path: Path,
    relative_path: str,
    extension: str,
    file_category: str,
    current_hash: str,
    redis_client,
    store_file_hash,
) -> FileAnalysisResult:
    """Helper for _analyze_single_file. Ref: #1088.

    Determines the analyzer type, runs analysis, builds the FileAnalysisResult,
    and stores the file hash for incremental indexing (Issue #539).

    Args:
        file_path: Path to file
        relative_path: Relative path string
        extension: File extension
        file_category: File category string
        current_hash: Current file hash
        redis_client: Redis client for hash storage
        store_file_hash: Async callable to persist file hash

    Returns:
        FileAnalysisResult populated from analyzer output (or empty if no output)
    """
    analyzer_type, stat_key = _determine_analyzer_type(extension)
    file_analysis = await _run_file_analyzer(file_path, analyzer_type)

    if file_analysis:
        result = _build_file_analysis_result(
            file_path,
            relative_path,
            extension,
            file_category,
            current_hash,
            file_analysis,
            analyzer_type,
            stat_key,
        )
    else:
        result = _build_empty_analysis_result(
            file_path,
            relative_path,
            extension,
            file_category,
            current_hash,
            analyzer_type,
            stat_key,
        )

    if current_hash and redis_client:
        await store_file_hash(redis_client, relative_path, current_hash)

    return result


async def _analyze_single_file(
    file_path: Path,
    root_path_obj: Path,
    file_needs_reindex,
    run_in_indexing_thread,
    store_file_hash,
    redis_client=None,
) -> FileAnalysisResult:
    """
    Analyze a single file and return immutable FileAnalysisResult.

    Issue #711: This function does NOT mutate any shared state.
    Issue #620: Refactored to use extracted helper methods.

    Args:
        file_path: Path to analyze
        root_path_obj: Root path for relative path computation
        file_needs_reindex: Async callable to check if file needs re-indexing
        run_in_indexing_thread: Callable to run sync functions in thread pool
        store_file_hash: Async callable to persist file hash
        redis_client: Optional Redis client for incremental indexing
    """
    extension, relative_path, file_category, base_result = _build_base_file_metadata(file_path, root_path_obj)

    # Check if file exists and is not in skip directories
    try:
        is_file = await run_in_indexing_thread(file_path.is_file)
    except Exception as e:
        logger.debug("Error checking if path is file %s: %s", file_path, e)
        return base_result

    if not is_file or any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
        return base_result

    # Check if file needs reindexing (Issue #539)
    needs_reindex, current_hash = await file_needs_reindex(file_path, relative_path, redis_client)
    if not needs_reindex:
        return _build_unchanged_file_result(file_path, relative_path, extension, file_category, current_hash)

    return await _run_analysis_and_build_result(
        file_path,
        relative_path,
        extension,
        file_category,
        current_hash,
        redis_client,
        store_file_hash,
    )


async def _analyze_with_semaphore(
    file_path: Path,
    root_path_obj: Path,
    semaphore: asyncio.Semaphore,
    file_needs_reindex,
    run_in_indexing_thread,
    store_file_hash,
    redis_client=None,
) -> FileAnalysisResult:
    """
    Analyze a single file with semaphore-based rate limiting.

    Issue #711: Wrapper for _analyze_single_file that acquires
    semaphore before processing to limit concurrency.

    Args:
        file_path: Path to the file to analyze
        root_path_obj: Root path for relative path computation
        semaphore: Semaphore for concurrency control
        file_needs_reindex: Async callable to check if file needs re-indexing
        run_in_indexing_thread: Callable to run sync functions in thread pool
        store_file_hash: Async callable to persist file hash
        redis_client: Optional Redis client for incremental indexing

    Returns:
        FileAnalysisResult from _analyze_single_file
    """
    async with semaphore:
        return await _analyze_single_file(
            file_path,
            root_path_obj,
            file_needs_reindex,
            run_in_indexing_thread,
            store_file_hash,
            redis_client,
        )


def _create_error_result(file_path: Path, root_path_obj: Path) -> FileAnalysisResult:
    """
    Create FileAnalysisResult for a failed file processing.

    Issue #665: Extracted from _process_files_parallel to reduce function length.

    Args:
        file_path: Path to the file that failed
        root_path_obj: Root path for relative path computation

    Returns:
        FileAnalysisResult with was_processed=False
    """
    return FileAnalysisResult(
        file_path=file_path,
        relative_path=str(file_path.relative_to(root_path_obj)),
        extension=file_path.suffix.lower(),
        file_category=_get_file_category(file_path),
        was_processed=False,
        was_skipped_unchanged=False,
    )


async def _process_batch_results(
    batch_results: List,
    batch_files: List[Path],
    root_path_obj: Path,
    results: List[FileAnalysisResult],
) -> None:
    """
    Process batch results, handling exceptions and collecting results.

    Issue #665: Extracted from _process_files_parallel to reduce function length.

    Args:
        batch_results: Results from asyncio.gather (may include exceptions)
        batch_files: List of files in this batch
        root_path_obj: Root path for relative path computation
        results: List to append results to
    """
    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            file_path = batch_files[i]
            logger.debug("Error processing %s: %s", file_path, result)
            results.append(_create_error_result(file_path, root_path_obj))
        else:
            results.append(result)


async def _run_parallel_batch(
    batch_files: List[Path],
    root_path_obj: Path,
    semaphore: asyncio.Semaphore,
    redis_client,
    results: List,
    batch_idx: int,
    files_completed: int,
    progress_callback,
    total_files: int,
    total: int,
    file_needs_reindex,
    run_in_indexing_thread,
    store_file_hash,
) -> int:
    """Helper for _process_files_parallel. Ref: #1088."""
    tasks = [
        _analyze_with_semaphore(
            f,
            root_path_obj,
            semaphore,
            file_needs_reindex,
            run_in_indexing_thread,
            store_file_hash,
            redis_client,
        )
        for f in batch_files
    ]
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
    await _process_batch_results(batch_results, batch_files, root_path_obj, results)
    files_completed += len(batch_files)
    if progress_callback:
        await progress_callback(
            operation="Scanning files (parallel)",
            current=files_completed,
            total=total_files or total,
            current_file=f"Batch {batch_idx + 1} complete",
        )
    return files_completed


async def _process_files_parallel(
    all_files: List[Path],
    root_path_obj: Path,
    file_needs_reindex,
    run_in_indexing_thread,
    store_file_hash,
    redis_client=None,
    progress_callback=None,
    total_files: int = 0,
) -> List[FileAnalysisResult]:
    """Process files in parallel using asyncio.gather with semaphore rate limiting.

    Issue #665: Refactored to use extracted helper methods.

    Args:
        all_files: List of file paths to process
        root_path_obj: Root path for relative path computation
        file_needs_reindex: Async callable to check if file needs re-indexing
        run_in_indexing_thread: Callable to run sync functions in thread pool
        store_file_hash: Async callable to persist file hash
        redis_client: Optional Redis client for incremental indexing
        progress_callback: Optional progress reporting callback
        total_files: Total file count for progress reporting
    """
    if not all_files:
        return []

    semaphore = asyncio.Semaphore(PARALLEL_FILE_CONCURRENCY)
    results: List[FileAnalysisResult] = []
    batch_size = max(100, PARALLEL_FILE_CONCURRENCY * 2)
    total = len(all_files)
    logger.info(
        "[Parallel] Processing %d files with concurrency=%d, batch_size=%d",
        total,
        PARALLEL_FILE_CONCURRENCY,
        batch_size,
    )

    files_completed = 0
    for batch_idx, batch_start in enumerate(range(0, total, batch_size)):
        batch_files = all_files[batch_start : min(batch_start + batch_size, total)]
        files_completed = await _run_parallel_batch(
            batch_files,
            root_path_obj,
            semaphore,
            redis_client,
            results,
            batch_idx,
            files_completed,
            progress_callback,
            total_files,
            total,
            file_needs_reindex,
            run_in_indexing_thread,
            store_file_hash,
        )
        await asyncio.sleep(0)

    logger.info("[Parallel] Completed processing %d files", len(results))
    return results
