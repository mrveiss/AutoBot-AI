# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
File counting and scanning helper functions for codebase analytics.

Issue #2013: Decomposed from scanner.py god module.
"""

from pathlib import Path
from typing import Tuple

from autobot_shared.logging_manager import get_logger
from utils.file_categorization import SKIP_DIRS

logger = get_logger(__name__)


def _should_count_file(file_path: Path) -> bool:
    """Check if file should be counted for progress tracking (Issue #315)."""
    if not file_path.is_file():
        return False
    return not any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS)


def _count_scannable_files_sync(root_path_obj: Path) -> Tuple[int, list]:
    """
    Synchronous file counting - runs in thread pool.

    Returns:
        Tuple of (scannable_file_count, scannable_files_list).
        Only returns files that should be scanned (not all files).
    """
    all_files = list(root_path_obj.rglob("*"))
    # Filter to only scannable files to avoid iterating through 200K files
    scannable_files = [f for f in all_files if _should_count_file(f)]
    return len(scannable_files), scannable_files


async def _count_scannable_files(root_path_obj: Path, run_in_indexing_thread) -> Tuple[int, list]:
    """
    Count files to be scanned and return the file list for reuse.

    Issue #315: extracted for progress tracking.
    Issue #358: avoid blocking with dedicated thread pool.
    Fixed: Run entire counting (including is_file checks) in thread pool.

    Args:
        root_path_obj: Root path as Path object
        run_in_indexing_thread: Callable to run sync functions in thread pool

    Returns:
        Tuple of (scannable_file_count, all_files_list) to avoid duplicate rglob.
    """
    # Run entire counting operation in thread pool (rglob + is_file checks)
    total_files, all_files = await run_in_indexing_thread(_count_scannable_files_sync, root_path_obj)
    logger.debug(
        "Counted %d scannable files from %d total in %s",
        total_files,
        len(all_files),
        root_path_obj,
    )
    return total_files, all_files


async def _gather_scannable_files(
    root_path_obj: Path,
    progress_callback,
    run_in_indexing_thread,
) -> tuple:
    """
    Gather scannable files and initialize progress tracking.

    Issue #620: Extracted from scan_codebase to reduce function length.

    Args:
        root_path_obj: Root path as Path object
        progress_callback: Optional progress callback function
        run_in_indexing_thread: Callable to run sync functions in thread pool

    Returns:
        Tuple of (total_files, all_files list)
    """
    total_files = 0
    all_files = []

    if progress_callback:
        total_files, all_files = await _count_scannable_files(root_path_obj, run_in_indexing_thread)
        await progress_callback(
            operation="Scanning files",
            current=0,
            total=total_files,
            current_file="Initializing...",
        )
    else:
        all_files = await run_in_indexing_thread(lambda: list(root_path_obj.rglob("*")))
        logger.debug("Direct rglob returned %d files", len(all_files))

    return total_files, all_files


def _log_incremental_stats(files_processed: int, files_skipped: int, incremental_enabled: bool) -> None:
    """
    Log incremental indexing statistics.

    Issue #620: Extracted from scan_codebase to reduce function length.

    Args:
        files_processed: Number of files processed
        files_skipped: Number of files skipped (unchanged)
        incremental_enabled: Whether incremental indexing is enabled
    """
    if incremental_enabled:
        logger.info(
            "Incremental indexing: %d files processed, %d files skipped (unchanged)",
            files_processed,
            files_skipped,
        )
