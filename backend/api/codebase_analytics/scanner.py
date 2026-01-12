# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase scanning and indexing functions
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException

from backend.type_defs.common import Metadata
from src.constants.path_constants import PATH
from src.utils.file_categorization import (
    # Category constants
    FILE_CATEGORY_CODE,
    FILE_CATEGORY_CONFIG,
    FILE_CATEGORY_DOCS,
    FILE_CATEGORY_LOGS,
    FILE_CATEGORY_BACKUP,
    FILE_CATEGORY_ARCHIVE,
    FILE_CATEGORY_DATA,
    FILE_CATEGORY_ASSETS,
    FILE_CATEGORY_TEST,
    # Extension sets
    PYTHON_EXTENSIONS,
    JS_EXTENSIONS,
    TS_EXTENSIONS,
    VUE_EXTENSIONS,
    CSS_EXTENSIONS,
    HTML_EXTENSIONS,
    CONFIG_EXTENSIONS,
    DOC_EXTENSIONS,
    LOG_EXTENSIONS,
    ALL_CODE_EXTENSIONS,
    # Directory sets
    SKIP_DIRS,
    BACKUP_DIRS,
    ARCHIVE_DIRS,
    LOG_DIRS,
    # Functions
    get_file_category as _get_file_category,
    should_skip_directory,
    should_count_for_metrics,
)

from .analyzers import analyze_python_file, analyze_javascript_vue_file, analyze_documentation_file
from .storage import get_code_collection_async, get_redis_connection_async
from .types import FileAnalysisResult, ParallelProcessingStats

logger = logging.getLogger(__name__)

# =============================================================================
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
                    thread_name_prefix="indexing_worker"
                )
                logger.info("Created dedicated indexing thread pool (%d workers)", _INDEXING_EXECUTOR_MAX_WORKERS)
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
# Configuration Constants (Issue #539: Configurable via environment variables)
# =============================================================================

# Batch size for ChromaDB storage operations
# Higher values = fewer batches but more memory usage
# Default: 5000 (current behavior), Range: 100-50000
try:
    _batch_size = int(os.getenv("CODEBASE_INDEX_BATCH_SIZE", "5000"))
    CHROMADB_BATCH_SIZE = max(100, min(_batch_size, 50000))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_BATCH_SIZE, using default 5000")
    CHROMADB_BATCH_SIZE = 5000

# Number of parallel batches to process concurrently
# Higher values = faster indexing but more CPU/memory usage
# Default: 1 (sequential processing), Range: 1-8
try:
    _parallel = int(os.getenv("CODEBASE_INDEX_PARALLEL_BATCHES", "1"))
    PARALLEL_BATCH_COUNT = max(1, min(_parallel, 8))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_PARALLEL_BATCHES, using default 1")
    PARALLEL_BATCH_COUNT = 1

# Enable incremental indexing (only re-index changed files)
# Default: False (full re-index - current behavior)
INCREMENTAL_INDEXING_ENABLED = os.getenv("CODEBASE_INDEX_INCREMENTAL", "false").lower() == "true"

# Issue #659: File processing configuration
# Controls progress update frequency during scanning (every N/5 files)
# Note: Full parallel processing disabled due to shared state thread-safety
# concerns in _aggregate_file_analysis. Thread pool parallelism still used
# for file I/O operations via _run_in_indexing_thread.
# Default: 50, Range: 1-100
try:
    _parallel_files = int(os.getenv("CODEBASE_SCAN_PARALLEL_FILES", "50"))
    PARALLEL_FILE_PROCESSING = max(1, min(_parallel_files, 100))
except ValueError:
    logger.warning("Invalid CODEBASE_SCAN_PARALLEL_FILES, using default 50")
    PARALLEL_FILE_PROCESSING = 50

# Issue #660: Embedding mode for ChromaDB storage
# Options: "precompute" (5-10x faster), "auto" (let ChromaDB handle), "skip" (no embeddings)
# Default: "precompute" for optimal performance
CHROMADB_EMBEDDING_MODE = os.getenv("CODEBASE_INDEX_EMBEDDING_MODE", "precompute").lower()
if CHROMADB_EMBEDDING_MODE not in ("precompute", "auto", "skip"):
    logger.warning("Invalid CODEBASE_INDEX_EMBEDDING_MODE, using 'precompute'")
    CHROMADB_EMBEDDING_MODE = "precompute"

# Batch size for embedding pre-computation (Issue #660)
# Larger batches = more efficient GPU/NPU utilization, more memory
# Default: 100, Range: 10-500
try:
    _embed_batch = int(os.getenv("CODEBASE_INDEX_EMBED_BATCH_SIZE", "100"))
    EMBEDDING_BATCH_SIZE = max(10, min(_embed_batch, 500))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_EMBED_BATCH_SIZE, using default 100")
    EMBEDDING_BATCH_SIZE = 100

# Issue #711: Parallel file processing concurrency
# Controls how many files can be analyzed concurrently during scanning
# Higher values = faster scanning but more memory/CPU usage
# Default: 50, Range: 1-200
try:
    _parallel_concurrency = int(os.getenv("CODEBASE_INDEX_PARALLEL_FILES", "50"))
    PARALLEL_FILE_CONCURRENCY = max(1, min(_parallel_concurrency, 200))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_PARALLEL_FILES, using default 50")
    PARALLEL_FILE_CONCURRENCY = 50

# Issue #711: Enable parallel file processing mode
# When True, files are processed in parallel using asyncio.gather with semaphore
# When False, falls back to sequential processing (original behavior)
# Default: True (parallel mode enabled)
PARALLEL_MODE_ENABLED = os.getenv("CODEBASE_PARALLEL_MODE", "true").lower() == "true"

# Redis key prefix for file hashes (used for incremental indexing)
FILE_HASH_REDIS_PREFIX = "codebase:file_hash:"

# File hash chunk size (64KB for memory efficiency)
_FILE_HASH_CHUNK_SIZE = 65536


# =============================================================================
# Batch Embedding Functions (Issue #660: Pre-computed Embeddings)
# Issue #681: NPU Worker Integration for Hardware-Accelerated Embeddings
# =============================================================================


async def _generate_batch_embeddings(
    documents: List[str],
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> List[List[float]]:
    """
    Generate embeddings for documents in batches using NPU/GPU acceleration.

    Issue #660: Pre-computes embeddings before ChromaDB insert for 5-10x speedup.
    Issue #681: Uses NPU worker for hardware-accelerated embedding generation.
               Falls back to local semantic chunker if NPU unavailable.

    Priority order:
    1. NPU Worker (GPU.1 - RTX 4070) - fastest, uses nomic-embed-text
    2. Local semantic chunker (all-MiniLM-L6-v2) - fallback

    Args:
        documents: List of document strings to embed
        batch_size: Number of documents to process per batch (default: 100)

    Returns:
        List of embedding vectors
    """
    if not documents:
        return []

    logger.info(
        "Generating embeddings for %d documents (batch_size=%d, mode=%s)",
        len(documents), batch_size, CHROMADB_EMBEDDING_MODE
    )

    # Issue #681: Use NPU-accelerated embeddings with automatic fallback
    try:
        from backend.api.codebase_analytics.npu_embeddings import (
            generate_codebase_embeddings_batch,
        )

        embeddings = await generate_codebase_embeddings_batch(
            documents, batch_size=batch_size
        )

        if embeddings and len(embeddings) == len(documents):
            return embeddings

        logger.warning(
            "NPU embeddings returned incomplete results: %d/%d",
            len(embeddings) if embeddings else 0,
            len(documents),
        )

    except ImportError as e:
        logger.warning("NPU embeddings module not available: %s", e)
    except Exception as e:
        logger.warning("NPU embeddings failed, using fallback: %s", e)

    # Fallback to original semantic chunker implementation
    return await _generate_batch_embeddings_fallback(documents, batch_size)


async def _generate_batch_embeddings_fallback(
    documents: List[str],
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> List[List[float]]:
    """
    Generate embeddings using local semantic chunker (fallback).

    Issue #681: Original implementation preserved as fallback when
    NPU worker is unavailable or fails.

    Args:
        documents: List of document strings to embed
        batch_size: Number of documents to process per batch

    Returns:
        List of embedding vectors (384 dimensions for MiniLM-L6-v2)
    """
    from src.utils.semantic_chunker import get_semantic_chunker

    try:
        chunker = get_semantic_chunker()
        await chunker._initialize_model()
    except Exception as e:
        logger.warning("Semantic chunker unavailable: %s", e)
        return []

    all_embeddings = []
    total_docs = len(documents)

    start_time = asyncio.get_running_loop().time()

    for i in range(0, total_docs, batch_size):
        batch_docs = documents[i : i + batch_size]

        try:
            # Use async batch embedding method
            batch_embeddings = await chunker._compute_sentence_embeddings_async(
                batch_docs
            )

            # Convert numpy arrays to lists for ChromaDB
            for emb in batch_embeddings:
                all_embeddings.append(
                    emb.tolist() if hasattr(emb, "tolist") else list(emb)
                )

            # Log progress for large batches
            if total_docs > 100 and (i + batch_size) % (batch_size * 5) == 0:
                progress = min(100, int((i + batch_size) / total_docs * 100))
                logger.info(
                    "Fallback embedding progress: %d%% (%d/%d)",
                    progress,
                    i + batch_size,
                    total_docs,
                )

            # Yield to event loop periodically
            if i % (batch_size * 2) == 0:
                await asyncio.sleep(0)

        except Exception as e:
            logger.error("Fallback batch embedding failed at index %d: %s", i, e)
            # Fill with empty embeddings for failed batch
            for _ in batch_docs:
                all_embeddings.append([0.0] * 384)  # MiniLM-L6-v2 dimension

    elapsed = asyncio.get_running_loop().time() - start_time
    logger.info(
        "Generated %d fallback embeddings in %.2fs (%.1f docs/sec)",
        len(all_embeddings),
        elapsed,
        total_docs / elapsed if elapsed > 0 else 0,
    )

    return all_embeddings


# =============================================================================
# File Hashing Functions (Issue #539: Incremental Indexing Support)
# =============================================================================


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


async def _get_stored_file_hash(redis_client, relative_path: str) -> Optional[str]:
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
    file_path: Path, relative_path: str, redis_client
) -> Tuple[bool, str]:
    """
    Check if a file needs to be re-indexed based on hash comparison.

    Issue #539: Core incremental indexing logic.

    Returns:
        Tuple of (needs_reindex: bool, current_hash: str)
    """
    if not INCREMENTAL_INDEXING_ENABLED or not redis_client:
        return True, ""

    # Issue #619: Parallelize hash computation and Redis lookup
    # Use dedicated indexing thread pool for file hash computation
    current_hash, stored_hash = await asyncio.gather(
        _run_in_indexing_thread(_compute_file_hash, file_path),
        _get_stored_file_hash(redis_client, relative_path),
    )

    if not current_hash:
        return True, ""

    if stored_hash and stored_hash == current_hash:
        return False, current_hash

    return True, current_hash


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


async def _count_scannable_files(root_path_obj: Path) -> Tuple[int, list]:
    """
    Count files to be scanned and return the file list for reuse.

    Issue #315: extracted for progress tracking.
    Issue #358: avoid blocking with dedicated thread pool.
    Fixed: Run entire counting (including is_file checks) in thread pool.

    Returns:
        Tuple of (scannable_file_count, all_files_list) to avoid duplicate rglob.
    """
    logger.info("DEBUG: _count_scannable_files starting for %s", root_path_obj)
    # Run entire counting operation in thread pool (rglob + is_file checks)
    total_files, all_files = await _run_in_indexing_thread(
        _count_scannable_files_sync, root_path_obj
    )
    logger.info("DEBUG: _count_scannable_files returned %d scannable, %d total files", total_files, len(all_files))
    return total_files, all_files


# Issue #398: File type mapping for cleaner dispatch in _get_file_analysis
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


async def _get_file_analysis(file_path: Path, extension: str, stats: dict) -> Optional[dict]:
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
                return await asyncio.to_thread(analyze_javascript_vue_file, str(file_path))
            elif analyzer_type == "doc":
                # Issue #666: Wrap blocking file I/O in asyncio.to_thread
                return await asyncio.to_thread(analyze_documentation_file, str(file_path))
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


# =============================================================================
# Helper Functions (Issue #298 - Reduce Deep Nesting, Issue #281 - Long Functions)
# =============================================================================


async def _store_problem_to_chromadb(
    collection,
    problem: Dict,
    problem_idx: int,
) -> None:
    """Store a problem to ChromaDB collection."""
    if not collection:
        return

    try:
        problem_doc = f"""
Problem: {problem.get('type', 'unknown')}
Severity: {problem.get('severity', 'medium')}
File: {problem.get('file_path', '')}
Line: {problem.get('line', 0)}
Description: {problem.get('description', '')}
Suggestion: {problem.get('suggestion', '')}
        """.strip()

        metadata = {
            "type": "problem",
            "problem_type": problem.get("type", "unknown"),
            "severity": problem.get("severity", "medium"),
            "file_path": problem.get("file_path", ""),
            "line_number": str(problem.get("line", 0)),
            "description": problem.get("description", ""),
            "suggestion": problem.get("suggestion", ""),
        }

        # Use dedicated indexing thread pool for ChromaDB operations
        await _run_in_indexing_thread(
            lambda: collection.add(
                ids=[f"problem_{problem_idx}_{problem.get('type', 'unknown')}"],
                documents=[problem_doc],
                metadatas=[metadata],
            )
        )
    except Exception as e:
        logger.debug("Failed to store problem immediately: %s", e)


def _prepare_problem_document(problem: Dict, problem_idx: int) -> tuple:
    """
    Prepare a problem document for ChromaDB storage.

    Issue #398: Extracted from _store_problems_batch_to_chromadb.
    Returns tuple of (id, document, metadata).
    """
    file_category = problem.get("file_category", FILE_CATEGORY_CODE)
    problem_doc = f"""
Problem: {problem.get('type', 'unknown')}
Severity: {problem.get('severity', 'medium')}
File: {problem.get('file_path', '')}
Category: {file_category}
Line: {problem.get('line', 0)}
Description: {problem.get('description', '')}
Suggestion: {problem.get('suggestion', '')}
    """.strip()

    metadata = {
        "type": "problem",
        "problem_type": problem.get("type", "unknown"),
        "severity": problem.get("severity", "medium"),
        "file_path": problem.get("file_path", ""),
        "file_category": file_category,
        "line_number": str(problem.get("line", 0)),
        "description": problem.get("description", ""),
        "suggestion": problem.get("suggestion", ""),
    }

    doc_id = f"problem_{problem_idx}_{problem.get('type', 'unknown')}"
    return doc_id, problem_doc, metadata


async def _store_problems_batch_to_chromadb(collection, problems: list, start_idx: int) -> None:
    """Store multiple problems to ChromaDB collection in batch (Issue #398: refactored)."""
    if not collection or not problems:
        return

    try:
        ids, documents, metadatas = [], [], []
        for i, problem in enumerate(problems):
            doc_id, problem_doc, metadata = _prepare_problem_document(problem, start_idx + i)
            ids.append(doc_id)
            documents.append(problem_doc)
            metadatas.append(metadata)

        await collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.debug("Batch stored %s problems to ChromaDB", len(problems))
    except Exception as e:
        logger.debug("Failed to batch store problems: %s", e)


def _aggregate_stats_for_countable(stats: Dict, file_analysis: Dict, file_line_count: int) -> None:
    """
    Aggregate stats for countable file categories (code/config/test).

    Issue #398: Extracted from _aggregate_file_analysis to reduce method length.
    """
    stats["total_lines"] += file_line_count
    stats["total_functions"] += len(file_analysis.get("functions", []))
    stats["total_classes"] += len(file_analysis.get("classes", []))
    stats["code_lines"] += file_analysis.get("code_lines", 0)
    stats["comment_lines"] += file_analysis.get("comment_lines", 0)
    stats["docstring_lines"] += file_analysis.get("docstring_lines", 0)
    stats["blank_lines"] += file_analysis.get("blank_lines", 0)


def _aggregate_items_to_list(
    items: List[Dict], target_list: list, relative_path: str, file_category: str
) -> None:
    """
    Add file_path and file_category to items and append to target list.

    Issue #398: Extracted from _aggregate_file_analysis to reduce method length.
    """
    for item in items:
        item["file_path"] = relative_path
        item["file_category"] = file_category
        target_list.append(item)


def _aggregate_file_analysis(
    analysis_results: Dict, file_analysis: Dict, relative_path: str,
    file_category: str = FILE_CATEGORY_CODE,
) -> None:
    """
    Aggregate file analysis results into main results dict.

    Issue #398: Refactored with extracted helpers.
    """
    analysis_results["files"][relative_path] = file_analysis
    file_line_count = file_analysis.get("line_count", 0)
    stats = analysis_results["stats"]

    stats["lines_by_category"][file_category] += file_line_count
    stats["files_by_category"][file_category] += 1

    is_countable = file_category in (FILE_CATEGORY_CODE, FILE_CATEGORY_CONFIG, FILE_CATEGORY_TEST)
    if is_countable:
        _aggregate_stats_for_countable(stats, file_analysis, file_line_count)

    stats["documentation_lines"] += file_analysis.get("documentation_lines", 0)

    all_funcs = analysis_results["all_functions"]
    all_cls = analysis_results["all_classes"]
    all_hc = analysis_results["all_hardcodes"]
    _aggregate_items_to_list(file_analysis.get("functions", []), all_funcs, relative_path, file_category)
    _aggregate_items_to_list(file_analysis.get("classes", []), all_cls, relative_path, file_category)
    _aggregate_items_to_list(file_analysis.get("hardcodes", []), all_hc, relative_path, file_category)


async def _process_file_problems(
    file_analysis: Dict,
    relative_path: str,
    analysis_results: Dict,
    immediate_store_collection,
    file_category: str = FILE_CATEGORY_CODE,
) -> None:
    """
    Process problems from file analysis and store to ChromaDB.

    Issue #315: extracted to reduce nesting depth in scan_codebase.

    Args:
        file_analysis: Analysis results from a single file
        relative_path: Relative path of the file
        analysis_results: Main results dictionary to update
        immediate_store_collection: ChromaDB collection for immediate storage
        file_category: Category of the file (code, docs, logs, backup, archive)

    Note: Problems are tagged with file_category and added to problems_by_category
          for separate reporting of backup/archive issues.
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
        immediate_store_collection, file_problems, start_idx
    )


# =============================================================================
# Helper Functions for do_indexing_with_progress (Issue #281)
# =============================================================================


def _create_initial_task_state() -> Dict:
    """
    Create initial task state structure.

    Issue #281: extracted
    Issue #539: Added configurable batch_size and incremental indexing config
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
            "batch_size": CHROMADB_BATCH_SIZE,  # Issue #539: configurable
            "parallel_batches": PARALLEL_BATCH_COUNT,  # Issue #539: parallel processing
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
            "batch_size": CHROMADB_BATCH_SIZE,
            "parallel_batches": PARALLEL_BATCH_COUNT,
            "incremental_enabled": INCREMENTAL_INDEXING_ENABLED,
        },
        "result": None,
        "error": None,
        "started_at": datetime.now().isoformat(),
    }


async def _clear_redis_codebase_cache(task_id: str) -> None:
    """
    Clear Redis cache entries for codebase data.

    Issue #398: Extracted from _initialize_chromadb_collection to reduce method length.
    Issue #XXX: Fixed thread pool exhaustion by using native async Redis client.
               Previous implementation used sync client + asyncio.to_thread() which
               blocked indefinitely when the default ThreadPoolExecutor was saturated
               by concurrent analytics operations. No errors were logged because the
               code blocked BEFORE reaching any logging statements.
    """
    try:
        logger.info("[Task %s] Getting async Redis connection...", task_id)
        redis_client = await get_redis_connection_async()
        logger.info("[Task %s] Redis client: %s", task_id, type(redis_client) if redis_client else None)
        if redis_client:
            # Native async Redis scan - no thread pool dependency
            logger.info("[Task %s] Starting async scan for codebase:* keys...", task_id)
            keys_to_delete = []
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor=cursor, match="codebase:*", count=100)
                keys_to_delete.extend(keys)
                if cursor == 0:
                    break
            logger.info("[Task %s] Async scan completed, found %d keys", task_id, len(keys_to_delete))
            if keys_to_delete:
                # Native async delete
                await redis_client.delete(*keys_to_delete)
                logger.info("[Task %s] Cleared %s Redis cache entries", task_id, len(keys_to_delete))
        else:
            logger.info("[Task %s] No Redis client available, skipping cache clear", task_id)
    except Exception as e:
        logger.error("[Task %s] Error clearing Redis cache: %s", task_id, e, exc_info=True)


async def _clear_chromadb_collection(code_collection, task_id: str) -> None:
    """
    Clear existing entries from ChromaDB collection, preserving codebase_stats.

    Issue #398: Extracted from _initialize_chromadb_collection to reduce method length.
    Issue #540: Preserve codebase_stats document during clearing so stats remain
                available while indexing is in progress.
    """
    try:
        existing_data = await code_collection.get()
        existing_ids = existing_data["ids"]
        if existing_ids:
            # Issue #540: Preserve codebase_stats so stats endpoint returns data during indexing
            ids_to_delete = [id for id in existing_ids if id != "codebase_stats"]
            if ids_to_delete:
                await code_collection.delete(ids=ids_to_delete)
                logger.info(
                    "[Task %s] Cleared %s existing items from ChromaDB (preserved codebase_stats)",
                    task_id, len(ids_to_delete)
                )
    except Exception as e:
        logger.warning("[Task %s] Error clearing collection: %s", task_id, e)


async def _initialize_chromadb_collection(task_id: str, update_progress, update_phase):
    """Initialize and clear ChromaDB collection and Redis cache (Issue #281, #398: refactored)."""
    update_phase("init", "running")
    await update_progress(
        operation="Preparing storage", current=0, total=2,
        current_file="Clearing old cached data...", phase="init",
    )

    await _clear_redis_codebase_cache(task_id)

    await update_progress(
        operation="Preparing ChromaDB", current=1, total=2,
        current_file="Connecting to ChromaDB...", phase="init",
    )

    code_collection = await get_code_collection_async()
    if code_collection:
        await update_progress(
            operation="Clearing old ChromaDB data", current=1, total=2,
            current_file="Removing existing entries...", phase="init",
        )
        await _clear_chromadb_collection(code_collection, task_id)

    return code_collection


def _prepare_function_document(func: Dict, idx: int) -> tuple:
    """Prepare a function document for ChromaDB storage (Issue #281: extracted)."""
    doc_text = f"""
Function: {func['name']}
File: {func.get('file_path', 'unknown')}
Line: {func.get('line', 0)}
Parameters: {', '.join(func.get('args', []))}
Docstring: {func.get('docstring', 'No documentation')}
    """.strip()

    metadata = {
        "type": "function",
        "name": func["name"],
        "file_path": func.get("file_path", ""),
        "start_line": str(func.get("line", 0)),
        "parameters": ",".join(func.get("args", [])),
        "language": (
            "python"
            if func.get("file_path", "").endswith(".py")
            else "javascript"
        ),
    }

    return f"function_{idx}_{func['name']}", doc_text, metadata


def _prepare_class_document(cls: Dict, idx: int) -> tuple:
    """Prepare a class document for ChromaDB storage (Issue #281: extracted)."""
    doc_text = f"""
Class: {cls['name']}
File: {cls.get('file_path', 'unknown')}
Line: {cls.get('line', 0)}
Methods: {', '.join(cls.get('methods', []))}
Docstring: {cls.get('docstring', 'No documentation')}
    """.strip()

    metadata = {
        "type": "class",
        "name": cls["name"],
        "file_path": cls.get("file_path", ""),
        "start_line": str(cls.get("line", 0)),
        "methods": ",".join(cls.get("methods", [])),
        "language": "python",
    }

    return f"class_{idx}_{cls['name']}", doc_text, metadata


def _prepare_stats_document(analysis_results: Dict) -> tuple:
    """Prepare stats document for ChromaDB storage (Issue #281: extracted)."""
    stats = analysis_results["stats"]

    # Get category counts for document
    lines_by_cat = stats.get("lines_by_category", {})

    stats_doc = f"""
Codebase Statistics:
Total Files: {stats['total_files']}
Total Lines: {stats['total_lines']}
Code Lines: {lines_by_cat.get('code', 0)}
Backup Lines: {lines_by_cat.get('backup', 0)}
Archive Lines: {lines_by_cat.get('archive', 0)}
Python Files: {stats['python_files']}
JavaScript Files: {stats['javascript_files']}
Vue Files: {stats['vue_files']}
Total Functions: {stats['total_functions']}
Total Classes: {stats['total_classes']}
Last Indexed: {stats['last_indexed']}
    """.strip()

    # Convert all values to strings for ChromaDB, serializing dicts as JSON
    metadata = {"type": "stats"}
    for k, v in stats.items():
        if isinstance(v, dict):
            metadata[k] = json.dumps(v)
        else:
            metadata[k] = str(v)

    return "codebase_stats", stats_doc, metadata


async def _prepare_functions_batch(
    functions: List[Dict],
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    update_progress,
    total_items: int,
) -> int:
    """
    Prepare function documents for batch storage.

    Issue #398: Extracted from _prepare_batch_data to reduce method length.

    Returns:
        Number of items prepared.
    """
    items_prepared = 0
    for idx, func in enumerate(functions):
        doc_id, doc_text, metadata = _prepare_function_document(func, idx)
        batch_ids.append(doc_id)
        batch_documents.append(doc_text)
        batch_metadatas.append(metadata)

        items_prepared += 1
        if items_prepared % 100 == 0:
            await update_progress(
                operation="Storing functions",
                current=items_prepared,
                total=total_items,
                current_file=f"Function {idx+1}/{len(functions)}",
            )
    return items_prepared


async def _prepare_classes_batch(
    classes: List[Dict],
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    update_progress,
    total_items: int,
    items_offset: int,
) -> int:
    """
    Prepare class documents for batch storage.

    Issue #398: Extracted from _prepare_batch_data to reduce method length.

    Returns:
        Number of items prepared (including offset).
    """
    items_prepared = items_offset
    for idx, cls in enumerate(classes):
        doc_id, doc_text, metadata = _prepare_class_document(cls, idx)
        batch_ids.append(doc_id)
        batch_documents.append(doc_text)
        batch_metadatas.append(metadata)

        items_prepared += 1
        if items_prepared % 50 == 0:
            await update_progress(
                operation="Storing classes",
                current=items_prepared,
                total=total_items,
                current_file=f"Class {idx+1}/{len(classes)}",
            )
    return items_prepared


async def _prepare_batch_data(
    analysis_results: Dict,
    task_id: str,
    update_progress,
    update_phase,
) -> tuple:
    """Prepare all batch data for ChromaDB storage (Issue #281, #398: refactored)."""
    update_phase("prepare", "running")

    batch_ids = []
    batch_documents = []
    batch_metadatas = []

    total_items = len(analysis_results["all_functions"]) + len(analysis_results["all_classes"]) + 1

    await update_progress(
        operation="Preparing functions", current=0, total=total_items,
        current_file="Processing functions...", phase="prepare",
    )

    items_prepared = await _prepare_functions_batch(
        analysis_results["all_functions"], batch_ids, batch_documents, batch_metadatas, update_progress, total_items
    )

    await update_progress(
        operation="Storing classes", current=items_prepared, total=total_items, current_file="Processing classes..."
    )

    all_classes = analysis_results["all_classes"]
    await _prepare_classes_batch(
        all_classes, batch_ids, batch_documents, batch_metadatas,
        update_progress, total_items, items_prepared
    )

    stats_id, stats_doc, stats_meta = _prepare_stats_document(analysis_results)
    batch_ids.append(stats_id)
    batch_documents.append(stats_doc)
    batch_metadatas.append(stats_meta)

    update_phase("prepare", "completed")
    return batch_ids, batch_documents, batch_metadatas


async def _store_single_batch(
    code_collection, batch_ids: list, batch_documents: list, batch_metadatas: list,
    start_idx: int, batch_size: int, batch_num: int, total_batches: int, total_items: int,
    task_id: str, update_progress, update_stats,
    batch_embeddings: Optional[List[List[float]]] = None,
) -> int:
    """
    Store a single batch to ChromaDB.

    Issue #398: Extracted from _store_batches_to_chromadb to reduce method length.
    Issue #660: Added optional batch_embeddings for pre-computed embeddings.

    Returns:
        Number of items stored in this batch.
    """
    end_idx = min(start_idx + batch_size, len(batch_ids))
    batch_slice_ids = batch_ids[start_idx:end_idx]
    batch_slice_docs = batch_documents[start_idx:end_idx]
    batch_slice_metas = batch_metadatas[start_idx:end_idx]

    # Issue #660: Use pre-computed embeddings if available
    batch_slice_embeddings = None
    if batch_embeddings is not None:
        batch_slice_embeddings = batch_embeddings[start_idx:end_idx]

    await code_collection.add(
        ids=batch_slice_ids,
        documents=batch_slice_docs,
        metadatas=batch_slice_metas,
        embeddings=batch_slice_embeddings,
    )
    items_in_batch = len(batch_slice_ids)

    # Issue #539: Thread-safe update for parallel batch processing
    async with _tasks_lock:
        indexing_tasks[task_id]["batches"]["completed_batches"] = batch_num

    await update_progress(
        operation="Writing to ChromaDB", current=end_idx, total=total_items,
        current_file=f"Batch {batch_num}/{total_batches}", phase="store",
        batch_info={"current": batch_num, "total": total_batches, "items": items_in_batch}
    )
    update_stats(items_stored=end_idx)

    logger.info(
        f"[Task {task_id}] Stored batch {batch_num}/{total_batches}: "
        f"{items_in_batch} items ({end_idx}/{total_items})"
    )
    return items_in_batch


async def _precompute_embeddings(
    batch_documents: list, task_id: str, update_progress, update_phase
) -> Optional[List[List[float]]]:
    """
    Pre-compute embeddings for documents before storage.

    Issue #665: Extracted from _store_batches_to_chromadb for single responsibility.
    Issue #660: Original embedding pre-computation logic.

    Returns:
        List of embeddings if successful, None otherwise.
    """
    if CHROMADB_EMBEDDING_MODE != "precompute":
        if CHROMADB_EMBEDDING_MODE == "skip":
            logger.info("[Task %s] Skipping pre-computed embeddings (mode=skip)", task_id)
        return None

    update_phase("embed", "running")
    await update_progress(
        operation="Generating embeddings", current=0, total=len(batch_documents),
        current_file="Pre-computing embeddings...", phase="embed",
    )

    try:
        batch_embeddings = await _generate_batch_embeddings(batch_documents)

        if len(batch_embeddings) != len(batch_documents):
            logger.error(
                "[Task %s] Embedding count mismatch: %d embeddings for %d documents",
                task_id, len(batch_embeddings), len(batch_documents)
            )
            batch_embeddings = None
        else:
            logger.info(
                "[Task %s] Pre-computed %d embeddings (mode=%s)",
                task_id, len(batch_embeddings), CHROMADB_EMBEDDING_MODE
            )
    except Exception as e:
        logger.warning(
            "[Task %s] Embedding pre-computation failed, falling back to auto: %s",
            task_id, e
        )
        batch_embeddings = None

    update_phase("embed", "completed")
    return batch_embeddings


async def _process_batches_parallel(
    code_collection, batch_ids: list, batch_documents: list, batch_metadatas: list,
    batch_indices: list, batch_size: int, parallel_count: int,
    total_batches: int, total_items: int, task_id: str,
    update_progress, update_stats, batch_embeddings: Optional[List[List[float]]],
) -> int:
    """
    Process batches with parallel execution.

    Issue #665: Extracted from _store_batches_to_chromadb for single responsibility.
    Issue #539: Original parallel batch processing logic.

    Returns:
        Total number of items stored.
    """
    items_stored = 0

    for group_start in range(0, len(batch_indices), parallel_count):
        group_end = min(group_start + parallel_count, len(batch_indices))
        parallel_tasks = []

        for idx in range(group_start, group_end):
            i = batch_indices[idx]
            batch_num = idx + 1
            task = _store_single_batch(
                code_collection, batch_ids, batch_documents, batch_metadatas,
                i, batch_size, batch_num, total_batches, total_items,
                task_id, update_progress, update_stats,
                batch_embeddings=batch_embeddings,
            )
            parallel_tasks.append(task)

        results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("[Task %s] Batch storage error: %s", task_id, result)
            else:
                items_stored += result

    return items_stored


async def _store_batches_to_chromadb(
    code_collection, batch_ids: list, batch_documents: list, batch_metadatas: list,
    task_id: str, update_progress, update_phase, update_batch_info, update_stats,
) -> int:
    """
    Store prepared data to ChromaDB in batches.

    Issue #281, #398: refactored
    Issue #539: Added configurable batch size and parallel processing
    Issue #660: Added pre-computed embeddings for 5-10x speedup
    Issue #665: Refactored to extract helper methods.

    Configuration via environment variables:
        CODEBASE_INDEX_BATCH_SIZE: Items per batch (default: 5000)
        CODEBASE_INDEX_PARALLEL_BATCHES: Concurrent batches (default: 1)
        CODEBASE_INDEX_EMBEDDING_MODE: "precompute", "auto", or "skip" (default: precompute)
    """
    # Pre-compute embeddings if configured
    batch_embeddings = await _precompute_embeddings(
        batch_documents, task_id, update_progress, update_phase
    )

    update_phase("store", "running")

    batch_size = CHROMADB_BATCH_SIZE
    parallel_count = PARALLEL_BATCH_COUNT
    total_items = len(batch_ids)
    total_batches = (total_items + batch_size - 1) // batch_size

    logger.info(
        "[Task %s] ChromaDB storage config: batch_size=%d, parallel_batches=%d, total_batches=%d, embeddings=%s",
        task_id, batch_size, parallel_count, total_batches,
        "precomputed" if batch_embeddings else "auto"
    )

    update_batch_info(0, total_batches, 0)
    await update_progress(
        operation="Writing to ChromaDB", current=0, total=total_items,
        current_file=f"Batch storage ({parallel_count} parallel)...", phase="store",
        batch_info={"current": 0, "total": total_batches, "items": 0}
    )

    batch_indices = list(range(0, total_items, batch_size))

    if parallel_count > 1:
        items_stored = await _process_batches_parallel(
            code_collection, batch_ids, batch_documents, batch_metadatas,
            batch_indices, batch_size, parallel_count,
            total_batches, total_items, task_id,
            update_progress, update_stats, batch_embeddings,
        )
    else:
        items_stored = 0
        for i in range(0, total_items, batch_size):
            batch_num = i // batch_size + 1
            items_stored += await _store_single_batch(
                code_collection, batch_ids, batch_documents, batch_metadatas,
                i, batch_size, batch_num, total_batches, total_items,
                task_id, update_progress, update_stats,
                batch_embeddings=batch_embeddings,
            )

    update_phase("store", "completed")
    logger.info("[Task %s] ✅ Stored total of %s items in ChromaDB", task_id, items_stored)
    return items_stored


async def _store_hardcodes_to_redis(
    hardcodes: List[Dict],
    task_id: str,
) -> int:
    """
    Store detected hardcoded values to Redis for retrieval by the /hardcodes endpoint.

    Hardcodes are stored grouped by type (ip, url, port, api_key, config, etc.)
    using keys like: codebase:hardcodes:ip, codebase:hardcodes:url, etc.

    Args:
        hardcodes: List of hardcode dictionaries with type, value, line, file_path
        task_id: Current indexing task ID for logging

    Returns:
        Number of hardcodes stored
    """
    if not hardcodes:
        logger.info("[Task %s] No hardcodes to store", task_id)
        return 0

    from .storage import get_redis_connection

    redis_client = await get_redis_connection()
    if not redis_client:
        logger.warning("[Task %s] Redis unavailable, skipping hardcodes storage", task_id)
        return 0

    # Group hardcodes by type
    grouped: Dict[str, List[Dict]] = {}
    for hardcode in hardcodes:
        htype = hardcode.get("type", "unknown")
        if htype not in grouped:
            grouped[htype] = []
        grouped[htype].append(hardcode)

    # Store each type group to Redis
    # Issue #666: Use asyncio.to_thread to wrap blocking Redis calls
    stored_count = 0
    for htype, items in grouped.items():
        key = f"codebase:hardcodes:{htype}"
        try:
            await asyncio.to_thread(redis_client.set, key, json.dumps(items))
            stored_count += len(items)
            logger.debug("[Task %s] Stored %s hardcodes of type '%s'", task_id, len(items), htype)
        except Exception as e:
            logger.error("[Task %s] Failed to store hardcodes type '%s': %s", task_id, htype, e)

    logger.info("[Task %s] ✅ Stored %s hardcodes to Redis (%s types)", task_id, stored_count, len(grouped))
    return stored_count


def _create_empty_analysis_results() -> Dict:
    """
    Create empty analysis results dictionary structure.

    Issue #281: Extracted from scan_codebase to reduce function length
    and improve testability.

    Returns:
        Dict with initialized structure for files, stats, functions,
        classes, hardcodes, and problems. Includes category-specific
        tracking for code, docs, logs, backup, and archive files.
    """
    return {
        "files": {},
        "stats": {
            "total_files": 0,
            # By language/type
            "python_files": 0,
            "javascript_files": 0,
            "typescript_files": 0,
            "vue_files": 0,
            "css_files": 0,
            "html_files": 0,
            "config_files": 0,
            "doc_files": 0,
            "other_code_files": 0,
            "other_files": 0,
            # Line counts
            "total_lines": 0,
            "code_lines": 0,
            "comment_lines": 0,
            "docstring_lines": 0,
            "documentation_lines": 0,
            "blank_lines": 0,
            # Declarations
            "total_functions": 0,
            "total_classes": 0,
            # Category-specific stats (code lines not counted for docs/logs)
            "lines_by_category": {
                FILE_CATEGORY_CODE: 0,
                FILE_CATEGORY_DOCS: 0,
                FILE_CATEGORY_LOGS: 0,
                FILE_CATEGORY_BACKUP: 0,
                FILE_CATEGORY_ARCHIVE: 0,
                FILE_CATEGORY_CONFIG: 0,
                FILE_CATEGORY_TEST: 0,
                FILE_CATEGORY_DATA: 0,
                FILE_CATEGORY_ASSETS: 0,
            },
            "files_by_category": {
                FILE_CATEGORY_CODE: 0,
                FILE_CATEGORY_DOCS: 0,
                FILE_CATEGORY_LOGS: 0,
                FILE_CATEGORY_BACKUP: 0,
                FILE_CATEGORY_ARCHIVE: 0,
                FILE_CATEGORY_CONFIG: 0,
                FILE_CATEGORY_TEST: 0,
                FILE_CATEGORY_DATA: 0,
                FILE_CATEGORY_ASSETS: 0,
            },
        },
        "all_functions": [],
        "all_classes": [],
        "all_hardcodes": [],
        "all_problems": [],
        # Problems by category (for separate reporting)
        "problems_by_category": {
            FILE_CATEGORY_CODE: [],
            FILE_CATEGORY_DOCS: [],
            FILE_CATEGORY_LOGS: [],
            FILE_CATEGORY_BACKUP: [],
            FILE_CATEGORY_ARCHIVE: [],
            FILE_CATEGORY_CONFIG: [],
            FILE_CATEGORY_TEST: [],
            FILE_CATEGORY_DATA: [],
            FILE_CATEGORY_ASSETS: [],
        },
    }


def _calculate_analysis_statistics(analysis_results: Dict) -> None:
    """
    Calculate derived statistics for analysis results.

    Issue #281: Extracted from scan_codebase to reduce function length.
    Modifies analysis_results in place.

    Calculates:
        - average_file_size: Average lines per file
        - comment_ratio: Percentage of comment lines
        - docstring_ratio: Percentage of docstring lines
        - documentation_ratio: Combined comment + docstring percentage
        - last_indexed: Timestamp of indexing
    """
    stats = analysis_results["stats"]

    # Calculate average file size
    if stats["total_files"] > 0:
        stats["average_file_size"] = stats["total_lines"] / stats["total_files"]
    else:
        stats["average_file_size"] = 0

    # Calculate documentation ratios (Issue #368)
    total_lines = stats["total_lines"]
    if total_lines > 0:
        comment_lines = stats["comment_lines"]
        docstring_lines = stats["docstring_lines"]
        stats["comment_ratio"] = f"{(comment_lines / total_lines * 100):.1f}%"
        stats["docstring_ratio"] = f"{(docstring_lines / total_lines * 100):.1f}%"
        # Combined documentation ratio (comments + docstrings)
        doc_total = comment_lines + docstring_lines
        stats["documentation_ratio"] = f"{(doc_total / total_lines * 100):.1f}%"
    else:
        stats["comment_ratio"] = "0.0%"
        stats["docstring_ratio"] = "0.0%"
        stats["documentation_ratio"] = "0.0%"

    stats["last_indexed"] = datetime.now().isoformat()


# =============================================================================
# End of Helper Functions
# =============================================================================


# =============================================================================
# Issue #711: Parallel File Processing Functions
# =============================================================================


def _determine_analyzer_type(extension: str) -> Tuple[Optional[str], str]:
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
    analyzer_type: Optional[str],
) -> Optional[Dict]:
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
            return await asyncio.to_thread(
                analyze_javascript_vue_file, str(file_path)
            )
        elif analyzer_type == "doc":
            return await asyncio.to_thread(
                analyze_documentation_file, str(file_path)
            )
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
    analyzer_type: Optional[str],
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
        functions=_enrich_items_with_metadata(
            file_analysis.get("functions", []), relative_path, file_category
        ),
        classes=_enrich_items_with_metadata(
            file_analysis.get("classes", []), relative_path, file_category
        ),
        imports=file_analysis.get("imports", []),
        hardcodes=_enrich_items_with_metadata(
            file_analysis.get("hardcodes", []), relative_path, file_category
        ),
        problems=_enrich_items_with_metadata(
            file_analysis.get("problems", []), relative_path, file_category
        ),
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


async def _analyze_single_file(
    file_path: Path,
    root_path_obj: Path,
    redis_client=None,
) -> FileAnalysisResult:
    """
    Analyze a single file and return immutable FileAnalysisResult.

    Issue #711: This function does NOT mutate any shared state.
    All results are returned in a FileAnalysisResult dataclass,
    enabling safe parallel processing with asyncio.gather().
    """
    extension = file_path.suffix.lower()
    relative_path = str(file_path.relative_to(root_path_obj))
    file_category = _get_file_category(file_path)

    # Base result for invalid/skipped files
    base_result = FileAnalysisResult(
        file_path=file_path,
        relative_path=relative_path,
        extension=extension,
        file_category=file_category,
    )

    # Check if file exists and is not in skip directories
    try:
        is_file = await _run_in_indexing_thread(file_path.is_file)
    except Exception as e:
        logger.debug("Error checking if path is file %s: %s", file_path, e)
        return base_result

    if not is_file or any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
        return base_result

    # Check if file needs reindexing (Issue #539)
    needs_reindex, current_hash = await _file_needs_reindex(
        file_path, relative_path, redis_client
    )
    if not needs_reindex:
        return FileAnalysisResult(
            file_path=file_path, relative_path=relative_path, extension=extension,
            file_category=file_category, was_processed=False,
            was_skipped_unchanged=True, file_hash=current_hash,
        )

    # Determine analyzer and run analysis
    analyzer_type, stat_key = _determine_analyzer_type(extension)
    file_analysis = await _run_file_analyzer(file_path, analyzer_type)

    # Build result
    if file_analysis:
        result = _build_file_analysis_result(
            file_path, relative_path, extension, file_category,
            current_hash, file_analysis, analyzer_type, stat_key
        )
    else:
        result = FileAnalysisResult(
            file_path=file_path, relative_path=relative_path, extension=extension,
            file_category=file_category, was_processed=True,
            was_skipped_unchanged=False, file_hash=current_hash,
            analyzer_type=analyzer_type, stat_key=stat_key,
        )

    # Store file hash for incremental indexing (Issue #539)
    if current_hash and redis_client:
        await _store_file_hash(redis_client, relative_path, current_hash)

    return result


async def _analyze_with_semaphore(
    file_path: Path,
    root_path_obj: Path,
    semaphore: asyncio.Semaphore,
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
        redis_client: Optional Redis client for incremental indexing

    Returns:
        FileAnalysisResult from _analyze_single_file
    """
    async with semaphore:
        return await _analyze_single_file(file_path, root_path_obj, redis_client)


async def _process_files_parallel(
    all_files: List[Path],
    root_path_obj: Path,
    redis_client=None,
    progress_callback=None,
    total_files: int = 0,
) -> List[FileAnalysisResult]:
    """
    Process files in parallel using asyncio.gather with semaphore rate limiting.

    Issue #711: Core parallel processing function that replaces sequential
    file iteration. Returns list of FileAnalysisResult objects for
    thread-safe aggregation.

    Args:
        all_files: List of file paths to process
        root_path_obj: Root path for relative path computation
        redis_client: Optional Redis client for incremental indexing
        progress_callback: Optional callback for progress updates
        total_files: Total file count for progress calculation

    Returns:
        List of FileAnalysisResult objects (one per file)
    """
    if not all_files:
        return []

    semaphore = asyncio.Semaphore(PARALLEL_FILE_CONCURRENCY)
    results: List[FileAnalysisResult] = []

    # Process in batches for progress tracking
    batch_size = max(100, PARALLEL_FILE_CONCURRENCY * 2)
    total = len(all_files)

    logger.info(
        "[Parallel] Processing %d files with concurrency=%d, batch_size=%d",
        total, PARALLEL_FILE_CONCURRENCY, batch_size
    )

    files_completed = 0

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_files = all_files[batch_start:batch_end]

        # Create tasks for this batch
        tasks = [
            _analyze_with_semaphore(f, root_path_obj, semaphore, redis_client)
            for f in batch_files
        ]

        # Process batch in parallel
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results, handle exceptions
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                # Create error result for failed file
                file_path = batch_files[i]
                logger.debug("Error processing %s: %s", file_path, result)
                results.append(FileAnalysisResult(
                    file_path=file_path,
                    relative_path=str(file_path.relative_to(root_path_obj)),
                    extension=file_path.suffix.lower(),
                    file_category=_get_file_category(file_path),
                    was_processed=False,
                    was_skipped_unchanged=False,
                ))
            else:
                results.append(result)

        files_completed += len(batch_files)

        # Progress update
        if progress_callback:
            percent = int((files_completed / total) * 100)
            await progress_callback(
                operation="Scanning files (parallel)",
                current=files_completed,
                total=total_files or total,
                current_file=f"Batch {batch_start // batch_size + 1} complete",
            )

        # Yield to event loop between batches
        await asyncio.sleep(0)

    logger.info("[Parallel] Completed processing %d files", len(results))
    return results


def _aggregate_from_file_result(
    analysis_results: Dict,
    result: FileAnalysisResult,
) -> None:
    """
    Aggregate a single FileAnalysisResult into the main results dict.

    Issue #711: Helper for single-pass aggregation from immutable results.
    This is called sequentially after parallel processing completes.

    Args:
        analysis_results: Main results dictionary to update
        result: Single FileAnalysisResult to aggregate
    """
    if not result.was_processed:
        return

    relative_path = result.relative_path
    file_category = result.file_category
    stats = analysis_results["stats"]

    # Store file analysis dict
    analysis_results["files"][relative_path] = result.to_dict()

    # Update file type stats
    if result.stat_key:
        stats[result.stat_key] = stats.get(result.stat_key, 0) + 1
    else:
        stats["other_files"] = stats.get("other_files", 0) + 1

    stats["total_files"] += 1

    # Update category stats
    stats["lines_by_category"][file_category] += result.line_count
    stats["files_by_category"][file_category] += 1

    # Update line counts for countable categories
    is_countable = file_category in (
        FILE_CATEGORY_CODE, FILE_CATEGORY_CONFIG, FILE_CATEGORY_TEST
    )
    if is_countable:
        stats["total_lines"] += result.line_count
        stats["total_functions"] += len(result.functions)
        stats["total_classes"] += len(result.classes)
        stats["code_lines"] += result.code_lines
        stats["comment_lines"] += result.comment_lines
        stats["docstring_lines"] += result.docstring_lines
        stats["blank_lines"] += result.blank_lines

    stats["documentation_lines"] += result.documentation_lines

    # Aggregate lists
    analysis_results["all_functions"].extend(result.functions)
    analysis_results["all_classes"].extend(result.classes)
    analysis_results["all_hardcodes"].extend(result.hardcodes)
    analysis_results["all_problems"].extend(result.problems)
    analysis_results["problems_by_category"][file_category].extend(result.problems)


def _aggregate_all_results(
    all_results: List[FileAnalysisResult],
) -> Dict:
    """
    Aggregate all FileAnalysisResult objects into a single results dictionary.

    Issue #711: Thread-safe single-pass aggregation after parallel processing.
    This runs AFTER all parallel processing is complete, operating on
    immutable input data, so there are no thread-safety concerns.

    Args:
        all_results: List of FileAnalysisResult from parallel processing

    Returns:
        Complete analysis_results dictionary matching existing format
    """
    analysis_results = _create_empty_analysis_results()

    for result in all_results:
        _aggregate_from_file_result(analysis_results, result)

    _calculate_analysis_statistics(analysis_results)
    return analysis_results


async def _iterate_and_process_files_parallel(
    all_files: list,
    root_path_obj: Path,
    immediate_store_collection,
    progress_callback,
    total_files: int,
    redis_client=None,
) -> Tuple[Dict, int, int]:
    """
    Process files in parallel and return aggregated results.

    Issue #711: New parallel processing implementation that returns
    aggregated results instead of mutating shared state.

    Args:
        all_files: List of file paths to process
        root_path_obj: Root path for relative path computation
        immediate_store_collection: ChromaDB collection for problem storage
        progress_callback: Callback for progress updates
        total_files: Total file count for progress
        redis_client: Optional Redis client for incremental indexing

    Returns:
        Tuple of (analysis_results dict, files_processed, files_skipped)
    """
    import time
    start_time = time.time()

    # Process all files in parallel
    all_results = await _process_files_parallel(
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

    # Store all problems to ChromaDB in batch
    if immediate_store_collection and analysis_results["all_problems"]:
        await _store_problems_batch_to_chromadb(
            immediate_store_collection,
            analysis_results["all_problems"],
            0
        )

    # Calculate statistics
    files_processed = sum(1 for r in all_results if r.was_processed)
    files_skipped = sum(1 for r in all_results if r.was_skipped_unchanged)

    elapsed = time.time() - start_time
    logger.info(
        "[Parallel] Processed %d files, skipped %d, in %.2fs (%.1f files/sec)",
        files_processed, files_skipped, elapsed,
        files_processed / elapsed if elapsed > 0 else 0
    )

    return analysis_results, files_processed, files_skipped


# =============================================================================
# End of Issue #711 Parallel Processing Functions
# =============================================================================


async def _process_single_file(
    file_path: Path,
    root_path_obj: Path,
    analysis_results: Dict,
    immediate_store_collection,
    redis_client=None,
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
    needs_reindex, current_hash = await _file_needs_reindex(
        file_path, relative_path, redis_client
    )
    if not needs_reindex:
        return False, True  # Skipped - file unchanged

    analysis_results["stats"]["total_files"] += 1

    file_analysis = await _get_file_analysis(file_path, extension, analysis_results["stats"])
    if not file_analysis:
        if current_hash and redis_client:
            await _store_file_hash(redis_client, relative_path, current_hash)
        return True, False

    _aggregate_file_analysis(analysis_results, file_analysis, relative_path, file_category)
    await _process_file_problems(
        file_analysis, relative_path, analysis_results, immediate_store_collection, file_category
    )

    # Issue #539: Store file hash after successful processing
    if current_hash and redis_client:
        await _store_file_hash(redis_client, relative_path, current_hash)

    return True, False


async def _iterate_and_process_files(
    all_files: list, root_path_obj: Path, analysis_results: Dict,
    immediate_store_collection, progress_callback, total_files: int,
    redis_client=None,
) -> Tuple[int, int]:
    """
    Iterate through files and process each one.

    Issue #398: Extracted from scan_codebase to reduce method length.
    Issue #539: Added incremental indexing - returns (processed, skipped) counts.
    Issue #659: Added batch parallel processing for 3-5x speedup.
    Issue #711: Added parallel mode with PARALLEL_MODE_ENABLED flag.
                When enabled, uses asyncio.gather() with semaphore for
                true parallel processing with thread-safe aggregation.
    """
    # Issue #711: Use parallel processing when enabled
    if PARALLEL_MODE_ENABLED:
        logger.info(
            "[Issue #711] Parallel mode enabled (concurrency=%d)",
            PARALLEL_FILE_CONCURRENCY
        )
        parallel_results, files_processed, files_skipped = await _iterate_and_process_files_parallel(
            all_files, root_path_obj, immediate_store_collection,
            progress_callback, total_files, redis_client
        )
        # Update analysis_results with parallel results
        analysis_results.update(parallel_results)
        return files_processed, files_skipped

    # Sequential processing fallback (original implementation)
    logger.info("[Issue #711] Sequential mode (parallel disabled)")
    files_processed = 0
    files_skipped = 0

    # Issue #659: Sequential processing with thread pool for file I/O
    progress_interval = max(10, PARALLEL_FILE_PROCESSING // 5)

    for file_path in all_files:
        processed, skipped = await _process_single_file(
            file_path, root_path_obj, analysis_results, immediate_store_collection,
            redis_client
        )
        if skipped:
            files_skipped += 1
        if processed:
            files_processed += 1
            if progress_callback and files_processed % progress_interval == 0:
                relative_path = str(file_path.relative_to(root_path_obj))
                await progress_callback(
                    operation="Scanning files", current=files_processed,
                    total=total_files, current_file=relative_path
                )
            elif files_processed % 5 == 0:
                await asyncio.sleep(0)

    return files_processed, files_skipped


async def scan_codebase(
    root_path: Optional[str] = None,
    progress_callback: Optional[callable] = None,
    immediate_store_collection=None,
    redis_client=None,
) -> Metadata:
    """
    Scan the entire codebase using MCP-like file operations.

    Issue #315, #281, #398: Uses extracted helpers for modular processing.
    Issue #539: Added redis_client param for incremental indexing support.
    """
    if root_path is None:
        root_path = str(PATH.PROJECT_ROOT)

    analysis_results = _create_empty_analysis_results()

    # Issue #539: Get Redis client for incremental indexing if enabled
    if redis_client is None and INCREMENTAL_INDEXING_ENABLED:
        redis_client = await get_redis_connection()

    try:
        root_path_obj = Path(root_path)
        total_files = 0
        all_files = []
        logger.info("DEBUG: scan_codebase starting for %s", root_path)
        if progress_callback:
            logger.info("DEBUG: about to call _count_scannable_files")
            # Get both count and file list to avoid duplicate rglob
            total_files, all_files = await _count_scannable_files(root_path_obj)
            logger.info("DEBUG: Got %d scannable files from %d total files", total_files, len(all_files))
            logger.info("DEBUG: About to call progress_callback for scan init")
            await progress_callback(
                operation="Scanning files", current=0,
                total=total_files, current_file="Initializing..."
            )
            logger.info("DEBUG: progress_callback returned, about to iterate")
        else:
            # No progress callback - still need file list but skip counting
            logger.info("DEBUG: No progress callback, doing direct rglob")
            all_files = await _run_in_indexing_thread(lambda: list(root_path_obj.rglob("*")))
            logger.info("DEBUG: Direct rglob returned %d files", len(all_files))

        # all_files is now already populated - no second rglob needed
        logger.info("DEBUG: Starting _iterate_and_process_files with %d files", len(all_files))
        files_processed, files_skipped = await _iterate_and_process_files(
            all_files, root_path_obj, analysis_results,
            immediate_store_collection, progress_callback, total_files,
            redis_client
        )

        # Issue #539: Log incremental indexing stats
        if INCREMENTAL_INDEXING_ENABLED:
            logger.info(
                "Incremental indexing: %d files processed, %d files skipped (unchanged)",
                files_processed, files_skipped
            )

        # Issue #711: Statistics already calculated in parallel mode
        # Only calculate for sequential mode (parallel mode does it in _aggregate_all_results)
        if not PARALLEL_MODE_ENABLED:
            _calculate_analysis_statistics(analysis_results)
        return analysis_results

    except Exception as e:
        logger.error("Error scanning codebase: %s", e)
        raise HTTPException(status_code=500, detail=f"Codebase scan failed: {str(e)}")


def _update_task_phase(task_id: str, phase_id: str, status: str) -> None:
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
    task_id: str, current_batch: int, total_batches: int, items_in_batch: int = 0
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


def _update_task_stats(task_id: str, **kwargs) -> None:
    """
    Update task statistics with provided key-value pairs.

    Issue #398: Extracted from do_indexing_with_progress inline helper.
    """
    for key, value in kwargs.items():
        if key in indexing_tasks[task_id]["stats"]:
            indexing_tasks[task_id]["stats"][key] = value


def _mark_task_completed(
    task_id: str, analysis_results: Dict, hardcodes_stored: int, storage_type: str
) -> None:
    """
    Mark indexing task as completed with results.

    Issue #398: Extracted from do_indexing_with_progress.
    """
    indexing_tasks[task_id]["status"] = "completed"
    total_files = analysis_results["stats"]["total_files"]
    indexing_tasks[task_id]["result"] = {
        "status": "success",
        "message": f"Indexed {total_files} files, found {hardcodes_stored} hardcodes using {storage_type} storage",
        "stats": analysis_results["stats"],
        "hardcodes_count": hardcodes_stored,
        "storage_type": storage_type,
        "timestamp": datetime.now().isoformat(),
    }
    indexing_tasks[task_id]["completed_at"] = datetime.now().isoformat()


def _mark_task_failed(task_id: str, error: Exception) -> None:
    """
    Mark indexing task as failed with error.

    Issue #398: Extracted from do_indexing_with_progress.
    """
    indexing_tasks[task_id]["status"] = "failed"
    indexing_tasks[task_id]["error"] = str(error)
    indexing_tasks[task_id]["failed_at"] = datetime.now().isoformat()


def _create_progress_updater(task_id: str, update_phase, update_batch_info):
    """
    Create a progress update callback for the given task.

    Issue #398: Extracted from do_indexing_with_progress to reduce method length.
    """
    async def update_progress(
        operation: str, current: int, total: int, current_file: str,
        phase: str = None, batch_info: dict = None
    ):
        percent = int((current / total * 100)) if total > 0 else 0
        indexing_tasks[task_id]["progress"] = {
            "current": current, "total": total, "percent": percent,
            "current_file": current_file, "operation": operation,
        }
        if phase:
            update_phase(phase, "running")
        if batch_info:
            update_batch_info(batch_info.get("current", 0), batch_info.get("total", 0), batch_info.get("items", 0))
        logger.debug("[Task %s] Progress: %s - %s/%s (%s%)", task_id, operation, current, total, percent)
    return update_progress


async def _run_indexing_phases(
    task_id: str, root_path: str, update_progress,
    update_phase, update_batch_info, update_stats
):
    """
    Execute the core indexing phases.

    Issue #398: Extracted from do_indexing_with_progress to reduce method length.
    """
    code_collection = await _initialize_chromadb_collection(
        task_id, update_progress, update_phase
    )
    if not code_collection:
        raise Exception("ChromaDB connection failed")

    update_phase("init", "completed")
    update_phase("scan", "running")

    analysis_results = await scan_codebase(
        root_path, progress_callback=update_progress,
        immediate_store_collection=code_collection
    )

    update_stats(
        files_scanned=analysis_results["stats"]["total_files"],
        problems_found=len(analysis_results["all_problems"]),
        functions_found=len(analysis_results["all_functions"]),
        classes_found=len(analysis_results["all_classes"]),
    )
    update_phase("scan", "completed")

    batch_ids, batch_documents, batch_metadatas = await _prepare_batch_data(
        analysis_results, task_id, update_progress, update_phase
    )
    if batch_ids:
        await _store_batches_to_chromadb(
            code_collection, batch_ids, batch_documents, batch_metadatas,
            task_id, update_progress, update_phase, update_batch_info, update_stats,
        )

    hardcodes_stored = await _store_hardcodes_to_redis(analysis_results.get("all_hardcodes", []), task_id)
    return analysis_results, hardcodes_stored


async def do_indexing_with_progress(task_id: str, root_path: str):
    """
    Background task: Index codebase with real-time progress updates.

    Issue #281, #398: Refactored with extracted helpers for reduced complexity.
    """
    try:
        logger.info("[Task %s] Starting background codebase indexing for: %s", task_id, root_path)

        async with _tasks_lock:
            indexing_tasks[task_id] = _create_initial_task_state()

        # Create task-specific helper closures
        def update_phase(phase_id, status):
            _update_task_phase(task_id, phase_id, status)

        def update_batch_info(c, t, i=0):
            _update_task_batch_info(task_id, c, t, i)

        def update_stats(**kwargs):
            _update_task_stats(task_id, **kwargs)

        update_progress = _create_progress_updater(task_id, update_phase, update_batch_info)

        analysis_results, hardcodes_stored = await _run_indexing_phases(
            task_id, root_path, update_progress, update_phase, update_batch_info, update_stats
        )

        update_phase("finalize", "running")
        _mark_task_completed(task_id, analysis_results, hardcodes_stored, "chromadb")
        update_phase("finalize", "completed")
        logger.info("[Task %s] ✅ Indexing completed successfully", task_id)

    except Exception as e:
        logger.error("[Task %s] ❌ Indexing failed: %s", task_id, e, exc_info=True)
        _mark_task_failed(task_id, e)
