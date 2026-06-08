# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ChromaDB batch storage, embeddings, and verification for codebase analytics.

Issue #2013: Decomposed from scanner.py god module.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config
from utils.file_categorization import FILE_CATEGORY_CODE

from .progress_tracker import FILE_HASH_REDIS_PREFIX
from .storage import (
    get_code_collection_async,
    get_redis_connection,
)

logger = get_logger(__name__)

# =============================================================================
# Configuration Constants (Issue #539: Configurable via environment variables)
# =============================================================================

# Batch size for ChromaDB storage operations
# Higher values = fewer batches but more memory usage
# Default: 5000 (current behavior), Range: 100-50000
try:
    _batch_size = int(config.codebase_index_batch_size)
    CHROMADB_BATCH_SIZE = max(100, min(_batch_size, 50000))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_BATCH_SIZE, using default 5000")
    CHROMADB_BATCH_SIZE = 5000

# Number of parallel batches to process concurrently
# Higher values = faster indexing but more CPU/memory usage
# Default: 1 (sequential processing), Range: 1-8
try:
    _parallel = int(config.codebase_index_parallel_batches)
    PARALLEL_BATCH_COUNT = max(1, min(_parallel, 8))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_PARALLEL_BATCHES, using default 1")
    PARALLEL_BATCH_COUNT = 1

# Issue #660: Embedding mode for ChromaDB storage
# Options: "precompute" (5-10x faster), "auto" (let ChromaDB handle), "skip" (no embeddings)
# Default: "precompute" for optimal performance
CHROMADB_EMBEDDING_MODE = config.codebase_index_embedding_mode.lower()
if CHROMADB_EMBEDDING_MODE not in ("precompute", "auto", "skip"):
    logger.warning("Invalid CODEBASE_INDEX_EMBEDDING_MODE, using 'precompute'")
    CHROMADB_EMBEDDING_MODE = "precompute"

# Batch size for embedding pre-computation (Issue #660)
# Larger batches = more efficient GPU/NPU utilization, more memory
# Default: 100, Range: 10-500
try:
    _embed_batch = int(config.codebase_index_embed_batch_size)
    EMBEDDING_BATCH_SIZE = max(10, min(_embed_batch, 500))
except ValueError:
    logger.warning("Invalid CODEBASE_INDEX_EMBED_BATCH_SIZE, using default 100")
    EMBEDDING_BATCH_SIZE = 100

# Enable incremental indexing (only re-index changed files)
# Default: False (full re-index - current behavior)
INCREMENTAL_INDEXING_ENABLED = config.codebase_index_incremental.lower() == "true"

# Redis key prefix for file hashes — imported from progress_tracker (SSOT)


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
        len(documents),
        batch_size,
        CHROMADB_EMBEDDING_MODE,
    )

    # Issue #681: Use NPU-accelerated embeddings with automatic fallback
    try:
        from api.codebase_analytics.npu_embeddings import (
            generate_codebase_embeddings_batch,
        )

        embeddings = await generate_codebase_embeddings_batch(documents, batch_size=batch_size)

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


def _convert_embeddings_to_lists(batch_embeddings: List) -> List[List[float]]:
    """
    Convert numpy arrays to lists for ChromaDB compatibility.

    Issue #620: Extracted from _generate_batch_embeddings_fallback. Issue #620.
    """
    result = []
    for emb in batch_embeddings:
        result.append(emb.tolist() if hasattr(emb, "tolist") else list(emb))
    return result


def _create_empty_embeddings(count: int) -> List[List[float]]:
    """
    Create empty embedding vectors for failed batch processing.

    Issue #620: Extracted from _generate_batch_embeddings_fallback. Issue #620.
    """
    return [[0.0] * 384 for _ in range(count)]  # MiniLM-L6-v2 dimension


async def _process_embedding_batch(
    chunker,
    batch_docs: List[str],
    batch_index: int,
    batch_size: int,
    total_docs: int,
) -> List[List[float]]:
    """
    Process a single batch of documents for embeddings.

    Issue #620: Extracted from _generate_batch_embeddings_fallback. Issue #620.
    """
    try:
        batch_embeddings = await chunker._compute_sentence_embeddings_async(batch_docs)
        result = _convert_embeddings_to_lists(batch_embeddings)

        if total_docs > 100 and (batch_index + batch_size) % (batch_size * 5) == 0:
            progress = min(100, int((batch_index + batch_size) / total_docs * 100))
            logger.info(
                "Fallback embedding progress: %d%% (%d/%d)",
                progress,
                batch_index + batch_size,
                total_docs,
            )

        if batch_index % (batch_size * 2) == 0:
            await asyncio.sleep(0)

        return result
    except Exception as e:
        logger.error("Fallback batch embedding failed at index %d: %s", batch_index, e)
        return _create_empty_embeddings(len(batch_docs))


async def _generate_batch_embeddings_fallback(
    documents: List[str],
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> List[List[float]]:
    """
    Generate embeddings using local semantic chunker (fallback).

    Issue #681: Original implementation preserved as fallback.
    Issue #620: Refactored with helper functions. Issue #620.

    Args:
        documents: List of document strings to embed
        batch_size: Number of documents to process per batch

    Returns:
        List of embedding vectors (384 dimensions for MiniLM-L6-v2)
    """
    from utils.semantic_chunker import get_semantic_chunker

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
        batch_result = await _process_embedding_batch(chunker, batch_docs, i, batch_size, total_docs)
        all_embeddings.extend(batch_result)

    elapsed = asyncio.get_running_loop().time() - start_time
    logger.info(
        "Generated %d fallback embeddings in %.2fs (%.1f docs/sec)",
        len(all_embeddings),
        elapsed,
        total_docs / elapsed if elapsed > 0 else 0,
    )

    return all_embeddings


def make_problem_dict(
    problem_type: str,
    severity: str,
    file_path: str,
    line: int,
    description: str,
    suggestion: str,
    file_category: str = FILE_CATEGORY_CODE,
) -> Dict:
    """Canonical factory for the problem-dict schema (#6759).

    Single source of truth for the keys read by ``_prepare_problem_document``
    and written by cross-file analysis converters.  If the schema gains a new
    field, add it here and update the reader below.
    """
    return {
        "type": problem_type,
        "severity": severity,
        "file_path": file_path,
        "file_category": file_category,
        "line": line,
        "description": description,
        "suggestion": suggestion,
    }


def _prepare_problem_document(problem: Dict, problem_idx: int, source_id: str | None = None) -> tuple:
    """
    Prepare a problem document for ChromaDB storage.

    Issue #398: Extracted from _store_problems_batch_to_chromadb.
    Issue #1710: source_id for per-project scoping.
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
    if source_id:
        metadata["source_id"] = source_id

    prefix = f"{source_id}_" if source_id else ""
    doc_id = f"{prefix}problem_{problem_idx}_{problem.get('type', 'unknown')}"
    return doc_id, problem_doc, metadata


async def _store_problems_batch_to_chromadb(
    collection,
    problems: list,
    start_idx: int,
    source_id: str | None = None,
) -> None:
    """Store multiple problems to ChromaDB in batch (#398, #1710: source_id)."""
    if not collection or not problems:
        return

    try:
        ids, documents, metadatas = [], [], []
        for i, problem in enumerate(problems):
            doc_id, problem_doc, metadata = _prepare_problem_document(problem, start_idx + i, source_id=source_id)
            ids.append(doc_id)
            documents.append(problem_doc)
            metadatas.append(metadata)

        await collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.debug("Batch stored %s problems to ChromaDB", len(problems))
    except Exception as e:
        # Issue #1712: Retry once on stale collection (mirrors #1249 pattern).
        err_msg = str(e).lower()
        if "does not exist" in err_msg or "not found" in err_msg:
            logger.warning("Problems collection stale, recreating (#1712): %s", e)
            fresh = await get_code_collection_async()
            if fresh is not None:
                try:
                    await fresh.upsert(
                        ids=ids,
                        documents=documents,
                        metadatas=metadatas,
                    )
                    logger.info("Retry stored %d problems after stale collection", len(problems))
                    return
                except Exception as retry_err:
                    logger.error("Retry also failed for problems batch: %s", retry_err)
            else:
                logger.error("Cannot retry — collection unavailable (#1712)")
        else:
            logger.error("Failed to batch store problems to ChromaDB (#1712): %s", e)


async def _clear_redis_codebase_cache(task_id: str, source_id: str | None = None) -> None:
    """
    Clear Redis cache entries for codebase data.

    Issue #398: Extracted from _initialize_chromadb_collection.
    Issue #1710: When source_id is provided, only clear keys for that source.
    """
    try:
        redis_client = await get_async_redis_client(database="analytics")
        if redis_client:
            # Scope key pattern to source_id when provided (#1710)
            if source_id:
                pattern = f"codebase:{source_id}:*"
            else:
                pattern = "codebase:*"
            keys_to_delete = []
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
                keys_to_delete.extend(keys)
                if cursor == 0:
                    break
            # Issue #1220: Preserve file hashes in incremental mode
            if INCREMENTAL_INDEXING_ENABLED:
                keys_to_delete = [
                    k
                    for k in keys_to_delete
                    if not k.decode("utf-8", errors="ignore").startswith(FILE_HASH_REDIS_PREFIX)
                ]
            if keys_to_delete:
                await redis_client.delete(*keys_to_delete)
                logger.info(
                    "[Task %s] Cleared %d Redis cache entries",
                    task_id,
                    len(keys_to_delete),
                )
        else:
            logger.info(
                "[Task %s] No Redis client, skipping cache clear",
                task_id,
            )
    except Exception as e:
        logger.error(
            "[Task %s] Error clearing Redis cache: %s",
            task_id,
            e,
            exc_info=True,
        )


async def _delete_source_documents(collection, task_id: str, source_id: str):
    """Delete all ChromaDB documents belonging to a source (#1710).

    Helper for _recreate_chromadb_collection.
    Deletes in batches to avoid SQLite C-extension limits.
    """
    try:
        # #6695: collection is an AsyncChromaDBCollection — its .get/.delete are
        # async def and must be awaited directly. Wrapping in asyncio.to_thread
        # produced an unawaited coroutine, silently masking source-doc deletion.
        existing = await collection.get(
            where={"source_id": source_id},
            include=[],
        )
        if existing and existing.get("ids"):
            ids_to_delete = existing["ids"]
            batch_size = 5000
            for i in range(0, len(ids_to_delete), batch_size):
                batch = ids_to_delete[i : i + batch_size]
                await collection.delete(ids=batch)
            logger.info(
                "[Task %s] Deleted %d documents for source %s",
                task_id,
                len(ids_to_delete),
                source_id,
            )
        else:
            logger.info(
                "[Task %s] No existing documents for source %s",
                task_id,
                source_id,
            )
    except Exception as del_exc:
        logger.warning(
            "[Task %s] Could not delete source %s docs: %s",
            task_id,
            source_id,
            del_exc,
        )


async def _drop_and_create_collection(async_client, collection_name: str, collection_meta: dict, task_id: str):
    """Drop and recreate a ChromaDB collection for global re-indexing.

    Issue #1213: Extracted from _recreate_chromadb_collection.
    """
    try:
        await async_client.delete_collection(collection_name)
        logger.info("[Task %s] Dropped ChromaDB collection '%s'", task_id, collection_name)
    except Exception:
        logger.info("[Task %s] No existing collection '%s' to drop", task_id, collection_name)
    new_collection = await async_client.get_or_create_collection(
        name=collection_name,
        metadata=collection_meta,
    )
    logger.info("[Task %s] Created fresh ChromaDB collection '%s'", task_id, collection_name)
    return new_collection


async def _recreate_chromadb_collection(task_id: str, source_id: str | None = None):
    """
    Prepare the ChromaDB collection for re-indexing.

    Issue #1213: Drops and recreates when no source_id (global).
    Issue #1710: Per-source deletion via _delete_source_documents.

    Returns:
        The AsyncChromaCollection, or None on failure.
    """
    from knowledge.backends import get_async_default_client

    chroma_path = str(Path(__file__).parent.parent.parent.parent / "data" / "chromadb")
    collection_name = "autobot_code"
    collection_meta = {"description": "Codebase analytics: functions, classes, problems, duplicates"}

    try:
        async_client = await get_async_default_client(
            db_path=chroma_path,
            allow_reset=False,
            anonymized_telemetry=False,
        )

        if source_id:
            collection = await async_client.get_or_create_collection(
                name=collection_name,
                metadata=collection_meta,
            )
            await _delete_source_documents(collection, task_id, source_id)
            return collection

        return await _drop_and_create_collection(async_client, collection_name, collection_meta, task_id)

    except Exception as e:
        logger.error(
            "[Task %s] Failed to recreate collection: %s",
            task_id,
            e,
            exc_info=True,
        )
        return None


async def _initialize_chromadb_collection(
    task_id: str,
    update_progress,
    update_phase,
    source_id: str | None = None,
):
    """Initialize ChromaDB collection and Redis cache.

    Issue #281, #398: refactored.
    Issue #1220: In incremental mode, preserves existing collection.
    Issue #1710: When source_id is provided, scopes cleanup to that source.
    """
    update_phase("init", "running")
    await update_progress(
        operation="Preparing storage",
        current=0,
        total=2,
        current_file="Clearing old cached data...",
        phase="init",
    )

    await _clear_redis_codebase_cache(task_id, source_id=source_id)

    if INCREMENTAL_INDEXING_ENABLED:
        # Keep existing collection — upsert will update changed files
        await update_progress(
            operation="Connecting to ChromaDB",
            current=1,
            total=2,
            current_file="Incremental mode — keeping existing data...",
            phase="init",
        )
        code_collection = await get_code_collection_async()
        logger.info(
            "[Task %s] Incremental mode: reusing existing collection",
            task_id,
        )
    else:
        await update_progress(
            operation="Recreating ChromaDB collection",
            current=1,
            total=2,
            current_file="Dropping and recreating collection...",
            phase="init",
        )
        code_collection = await _recreate_chromadb_collection(task_id, source_id=source_id)
        if not code_collection:
            code_collection = await get_code_collection_async()

    return code_collection


def _prepare_function_document(func: Dict, idx: int, source_id: str | None = None) -> tuple:
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
        "language": ("python" if func.get("file_path", "").endswith(".py") else "javascript"),
    }
    if source_id:
        metadata["source_id"] = source_id

    prefix = f"{source_id}_" if source_id else ""
    return f"{prefix}function_{idx}_{func['name']}", doc_text, metadata


def _prepare_class_document(cls: Dict, idx: int, source_id: str | None = None) -> tuple:
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
    if source_id:
        metadata["source_id"] = source_id

    prefix = f"{source_id}_" if source_id else ""
    return f"{prefix}class_{idx}_{cls['name']}", doc_text, metadata


def _prepare_stats_document(analysis_results: Dict, source_id: str | None = None) -> tuple:
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
    if source_id:
        metadata["source_id"] = source_id

    stats_id = f"codebase_stats_{source_id}" if source_id else "codebase_stats"
    return stats_id, stats_doc, metadata


async def _prepare_functions_batch(
    functions: List[Dict],
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    update_progress,
    total_items: int,
    source_id: str | None = None,
) -> int:
    """
    Prepare function documents for batch storage.

    Issue #398: Extracted from _prepare_batch_data to reduce method length.

    Returns:
        Number of items prepared.
    """
    items_prepared = 0
    for idx, func in enumerate(functions):
        doc_id, doc_text, metadata = _prepare_function_document(func, idx, source_id=source_id)
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
    source_id: str | None = None,
) -> int:
    """
    Prepare class documents for batch storage.

    Issue #398: Extracted from _prepare_batch_data to reduce method length.

    Returns:
        Number of items prepared (including offset).
    """
    items_prepared = items_offset
    for idx, cls in enumerate(classes):
        doc_id, doc_text, metadata = _prepare_class_document(cls, idx, source_id=source_id)
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
    source_id: str | None = None,
) -> tuple:
    """Prepare all batch data for ChromaDB storage (Issue #281, #398: refactored)."""
    update_phase("prepare", "running")

    batch_ids = []
    batch_documents = []
    batch_metadatas = []

    total_items = len(analysis_results["all_functions"]) + len(analysis_results["all_classes"]) + 1

    await update_progress(
        operation="Preparing functions",
        current=0,
        total=total_items,
        current_file="Processing functions...",
        phase="prepare",
    )

    items_prepared = await _prepare_functions_batch(
        analysis_results["all_functions"],
        batch_ids,
        batch_documents,
        batch_metadatas,
        update_progress,
        total_items,
        source_id=source_id,
    )

    await update_progress(
        operation="Storing classes",
        current=items_prepared,
        total=total_items,
        current_file="Processing classes...",
    )

    all_classes = analysis_results["all_classes"]
    await _prepare_classes_batch(
        all_classes,
        batch_ids,
        batch_documents,
        batch_metadatas,
        update_progress,
        total_items,
        items_prepared,
        source_id=source_id,
    )

    _append_stats_document(analysis_results, batch_ids, batch_documents, batch_metadatas, source_id)

    update_phase("prepare", "completed")
    return batch_ids, batch_documents, batch_metadatas


def _append_stats_document(
    analysis_results: Dict,
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    source_id: str | None = None,
) -> None:
    """Append the codebase_stats document to the batch lists (Issue #2735)."""
    stats_id, stats_doc, stats_meta = _prepare_stats_document(analysis_results, source_id=source_id)
    batch_ids.append(stats_id)
    batch_documents.append(stats_doc)
    batch_metadatas.append(stats_meta)


async def _upsert_with_stale_retry(
    code_collection,
    ids: list,
    documents: list,
    metadatas: list,
    embeddings,
    task_id: str,
    batch_num: int,
) -> None:
    """Upsert documents to ChromaDB, recreating collection on stale reference.

    Issue #540: Uses upsert to update preserved codebase_stats entries.
    Issue #1249: Extracted from _store_single_batch for length compliance.
    """
    try:
        await code_collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    except Exception as e:
        err_msg = str(e).lower()
        if "does not exist" in err_msg or "not found" in err_msg:
            logger.warning(
                "[Task %s] Collection stale on batch %d, recreating (#1249): %s",
                task_id,
                batch_num,
                e,
            )
            new_collection = await get_code_collection_async()
            if new_collection is None:
                raise
            await new_collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        else:
            raise


def _slice_batch(
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    batch_embeddings: List[List[float]] | None,
    start_idx: int,
    batch_size: int,
) -> tuple:
    """Slice batch lists to the current window. Returns (ids, docs, metas, embeddings, end_idx).

    Issue #2735: Extracted from _store_single_batch for length compliance.
    Issue #660: Preserves optional pre-computed embeddings slice.
    """
    end_idx = min(start_idx + batch_size, len(batch_ids))
    slice_embeddings = batch_embeddings[start_idx:end_idx] if batch_embeddings is not None else None
    return (
        batch_ids[start_idx:end_idx],
        batch_documents[start_idx:end_idx],
        batch_metadatas[start_idx:end_idx],
        slice_embeddings,
        end_idx,
    )


async def _record_batch_progress(
    task_id: str,
    batch_num: int,
    total_batches: int,
    items_in_batch: int,
    end_idx: int,
    total_items: int,
    update_progress,
    update_stats,
    tasks_lock: asyncio.Lock,
    indexing_tasks: Dict,
) -> None:
    """Update progress counters and emit a progress event after storing a batch.

    Issue #2735: Extracted from _store_single_batch for length compliance.
    Issue #539: Thread-safe update for parallel batch processing.
    """
    async with tasks_lock:
        indexing_tasks[task_id]["batches"]["completed_batches"] = batch_num

    await update_progress(
        operation="Writing to ChromaDB",
        current=end_idx,
        total=total_items,
        current_file=f"Batch {batch_num}/{total_batches}",
        phase="store",
        batch_info={
            "current": batch_num,
            "total": total_batches,
            "items": items_in_batch,
        },
    )
    update_stats(items_stored=end_idx)
    logger.info(
        "[Task %s] Stored batch %d/%d: %d items (%d/%d)",
        task_id,
        batch_num,
        total_batches,
        items_in_batch,
        end_idx,
        total_items,
    )


async def _store_single_batch(
    code_collection,
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    start_idx: int,
    batch_size: int,
    batch_num: int,
    total_batches: int,
    total_items: int,
    task_id: str,
    update_progress,
    update_stats,
    tasks_lock: asyncio.Lock,
    indexing_tasks: Dict,
    batch_embeddings: List[List[float]] | None = None,
) -> int:
    """Store a single batch to ChromaDB (Issue #398, #660, #1249).

    Returns items stored. Retries once on collection errors by
    recreating the collection reference (#1249).
    """
    slice_ids, slice_docs, slice_metas, slice_embeddings, end_idx = _slice_batch(
        batch_ids,
        batch_documents,
        batch_metadatas,
        batch_embeddings,
        start_idx,
        batch_size,
    )

    # Use upsert so the preserved codebase_stats entry (#540) gets
    # updated with fresh values instead of being silently skipped by add().
    # Issue #1249: Retry once on stale collection reference.
    await _upsert_with_stale_retry(
        code_collection,
        slice_ids,
        slice_docs,
        slice_metas,
        slice_embeddings,
        task_id,
        batch_num,
    )
    items_in_batch = len(slice_ids)

    await _record_batch_progress(
        task_id,
        batch_num,
        total_batches,
        items_in_batch,
        end_idx,
        total_items,
        update_progress,
        update_stats,
        tasks_lock,
        indexing_tasks,
    )
    return items_in_batch


async def _generate_embeddings_with_progress(
    batch_documents: list, total_docs: int, update_progress
) -> List[List[float]]:
    """Generate embeddings in super-batches, reporting progress (#1303).

    Splits the full document list into chunks of 1000 and updates
    Redis progress after each chunk so the UI shows real progress.
    """
    super_batch_size = 1000
    all_embeddings: List[List[float]] = []

    for offset in range(0, total_docs, super_batch_size):
        chunk = batch_documents[offset : offset + super_batch_size]
        chunk_embeddings = await _generate_batch_embeddings(chunk)
        all_embeddings.extend(chunk_embeddings)

        processed = offset + len(chunk)
        await update_progress(
            operation="Generating embeddings",
            current=processed,
            total=total_docs,
            current_file=(f"Embeddings: {processed}/{total_docs} " f"({processed * 100 // total_docs}%)"),
            phase="embed",
        )

    return all_embeddings


async def _precompute_embeddings(
    batch_documents: list, task_id: str, update_progress, update_phase
) -> List[List[float]] | None:
    """Pre-compute embeddings for documents before storage.

    Issue #665: Extracted from _store_batches_to_chromadb.
    Issue #660: Original embedding pre-computation logic.
    Issue #1303: Delegates to _generate_embeddings_with_progress
    so the embedding phase reports real progress instead of 0%.
    """
    if CHROMADB_EMBEDDING_MODE != "precompute":
        if CHROMADB_EMBEDDING_MODE == "skip":
            logger.info(
                "[Task %s] Skipping pre-computed embeddings (mode=skip)",
                task_id,
            )
        return None

    update_phase("embed", "running")
    total_docs = len(batch_documents)
    await update_progress(
        operation="Generating embeddings",
        current=0,
        total=total_docs,
        current_file="Pre-computing embeddings...",
        phase="embed",
    )

    try:
        batch_embeddings = await _generate_embeddings_with_progress(batch_documents, total_docs, update_progress)
        if len(batch_embeddings) != total_docs:
            logger.error(
                "[Task %s] Embedding count mismatch: %d vs %d docs",
                task_id,
                len(batch_embeddings),
                total_docs,
            )
            batch_embeddings = None
        else:
            logger.info(
                "[Task %s] Pre-computed %d embeddings (mode=%s)",
                task_id,
                len(batch_embeddings),
                CHROMADB_EMBEDDING_MODE,
            )
    except Exception as e:
        logger.warning(
            "[Task %s] Embedding pre-computation failed: %s",
            task_id,
            e,
        )
        batch_embeddings = None

    update_phase("embed", "completed")
    return batch_embeddings


async def _process_batches_parallel(
    code_collection,
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    batch_indices: list,
    batch_size: int,
    parallel_count: int,
    total_batches: int,
    total_items: int,
    task_id: str,
    update_progress,
    update_stats,
    batch_embeddings: List[List[float]] | None,
    tasks_lock: asyncio.Lock,
    indexing_tasks: Dict,
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
                code_collection,
                batch_ids,
                batch_documents,
                batch_metadatas,
                i,
                batch_size,
                batch_num,
                total_batches,
                total_items,
                task_id,
                update_progress,
                update_stats,
                tasks_lock,
                indexing_tasks,
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


async def _process_batches_sequential(
    code_collection,
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    batch_size: int,
    total_batches: int,
    total_items: int,
    task_id: str,
    update_progress,
    update_stats,
    batch_embeddings: List[List[float]] | None,
    tasks_lock: asyncio.Lock,
    indexing_tasks: Dict,
) -> int:
    """
    Process batches sequentially (one at a time).

    Issue #620: Extracted from _store_batches_to_chromadb to reduce function length.

    Returns:
        Total number of items stored. Issue #620.
    """
    items_stored = 0
    for i in range(0, total_items, batch_size):
        batch_num = i // batch_size + 1
        items_stored += await _store_single_batch(
            code_collection,
            batch_ids,
            batch_documents,
            batch_metadatas,
            i,
            batch_size,
            batch_num,
            total_batches,
            total_items,
            task_id,
            update_progress,
            update_stats,
            tasks_lock,
            indexing_tasks,
            batch_embeddings=batch_embeddings,
        )
    return items_stored


def _log_chromadb_storage_config(
    task_id: str,
    total_batches: int,
    batch_embeddings: List[List[float]] | None,
) -> None:
    """
    Log ChromaDB storage configuration details.

    Issue #620: Extracted from _store_batches_to_chromadb. Issue #620.
    """
    logger.info(
        "[Task %s] ChromaDB storage config: batch_size=%d, parallel_batches=%d, " "total_batches=%d, embeddings=%s",
        task_id,
        CHROMADB_BATCH_SIZE,
        PARALLEL_BATCH_COUNT,
        total_batches,
        "precomputed" if batch_embeddings else "auto",
    )


async def _update_chromadb_progress(
    update_progress,
    total_items: int,
    total_batches: int,
) -> None:
    """
    Send initial progress update for ChromaDB batch storage.

    Issue #620: Extracted from _store_batches_to_chromadb. Issue #620.
    """
    await update_progress(
        operation="Writing to ChromaDB",
        current=0,
        total=total_items,
        current_file=f"Batch storage ({PARALLEL_BATCH_COUNT} parallel)...",
        phase="store",
        batch_info={"current": 0, "total": total_batches, "items": 0},
    )


async def _execute_batch_storage(
    code_collection,
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    total_batches: int,
    total_items: int,
    task_id: str,
    update_progress,
    update_stats,
    batch_embeddings: List[List[float]] | None,
    tasks_lock: asyncio.Lock,
    indexing_tasks: Dict,
) -> int:
    """
    Execute batch storage using parallel or sequential processing.

    Issue #620: Extracted from _store_batches_to_chromadb. Issue #620.
    """
    batch_indices = list(range(0, total_items, CHROMADB_BATCH_SIZE))

    if PARALLEL_BATCH_COUNT > 1:
        return await _process_batches_parallel(
            code_collection,
            batch_ids,
            batch_documents,
            batch_metadatas,
            batch_indices,
            CHROMADB_BATCH_SIZE,
            PARALLEL_BATCH_COUNT,
            total_batches,
            total_items,
            task_id,
            update_progress,
            update_stats,
            batch_embeddings,
            tasks_lock,
            indexing_tasks,
        )

    return await _process_batches_sequential(
        code_collection,
        batch_ids,
        batch_documents,
        batch_metadatas,
        CHROMADB_BATCH_SIZE,
        total_batches,
        total_items,
        task_id,
        update_progress,
        update_stats,
        batch_embeddings,
        tasks_lock,
        indexing_tasks,
    )


async def _store_batches_to_chromadb(
    code_collection,
    batch_ids: list,
    batch_documents: list,
    batch_metadatas: list,
    task_id: str,
    update_progress,
    update_phase,
    update_batch_info,
    update_stats,
    tasks_lock: asyncio.Lock,
    indexing_tasks: Dict,
) -> int:
    """
    Store prepared data to ChromaDB in batches.

    Issue #281, #398: refactored
    Issue #539: Added configurable batch size and parallel processing
    Issue #660: Added pre-computed embeddings for 5-10x speedup
    Issue #620, #665: Refactored to extract helper methods.

    Configuration via environment variables:
        CODEBASE_INDEX_BATCH_SIZE: Items per batch (default: 5000)
        CODEBASE_INDEX_PARALLEL_BATCHES: Concurrent batches (default: 1)
        CODEBASE_INDEX_EMBEDDING_MODE: "precompute", "auto", or "skip" (default: precompute)
    """
    batch_embeddings = await _precompute_embeddings(batch_documents, task_id, update_progress, update_phase)
    update_phase("store", "running")

    total_items = len(batch_ids)
    total_batches = (total_items + CHROMADB_BATCH_SIZE - 1) // CHROMADB_BATCH_SIZE

    _log_chromadb_storage_config(task_id, total_batches, batch_embeddings)
    update_batch_info(0, total_batches, 0)
    await _update_chromadb_progress(update_progress, total_items, total_batches)

    items_stored = await _execute_batch_storage(
        code_collection,
        batch_ids,
        batch_documents,
        batch_metadatas,
        total_batches,
        total_items,
        task_id,
        update_progress,
        update_stats,
        batch_embeddings,
        tasks_lock,
        indexing_tasks,
    )

    update_phase("store", "completed")
    logger.info("[Task %s] Stored total of %s items in ChromaDB", task_id, items_stored)
    return items_stored


async def _store_hardcodes_to_redis(
    hardcodes: List[Dict],
    task_id: str,
    source_id: str | None = None,
) -> int:
    """
    Store detected hardcoded values to Redis for retrieval by the /hardcodes endpoint.

    Hardcodes are stored grouped by type (ip, url, port, api_key, config, etc.)
    using keys like: codebase:{source_id}:hardcodes:ip, etc.
    Falls back to codebase:hardcodes:ip when no source_id (#1710).

    Args:
        hardcodes: List of hardcode dictionaries with type, value, line, file_path
        task_id: Current indexing task ID for logging
        source_id: Optional source ID for per-project scoping

    Returns:
        Number of hardcodes stored
    """
    if not hardcodes:
        logger.info("[Task %s] No hardcodes to store", task_id)
        return 0

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

    # Store each type group to Redis (#1710: source-scoped keys)
    stored_count = 0
    key_prefix = f"codebase:{source_id}" if source_id else "codebase"
    for htype, items in grouped.items():
        key = f"{key_prefix}:hardcodes:{htype}"
        try:
            await asyncio.to_thread(redis_client.set, key, json.dumps(items))
            stored_count += len(items)
            logger.debug("[Task %s] Stored %s hardcodes of type '%s'", task_id, len(items), htype)
        except Exception as e:
            logger.error("[Task %s] Failed to store hardcodes type '%s': %s", task_id, htype, e)

    logger.info(
        "[Task %s] Stored %s hardcodes to Redis (%s types)",
        task_id,
        stored_count,
        len(grouped),
    )
    return stored_count


async def _verify_chromadb_storage(task_id: str, analysis_results: Dict) -> None:
    """Verify ChromaDB actually contains the indexed data (#1712).

    Queries ChromaDB after indexing to compare expected vs actual
    item counts. Logs WARNING if data appears to be missing.
    """
    try:
        collection = await get_code_collection_async()
        if not collection:
            logger.warning(
                "[Task %s] #1712 verify: ChromaDB collection unavailable",
                task_id,
            )
            return

        total_count = await collection.count()
        expected_funcs = len(analysis_results.get("all_functions", []))
        expected_classes = len(analysis_results.get("all_classes", []))
        expected_problems = len(analysis_results.get("all_problems", []))
        expected_total = expected_funcs + expected_classes + 1  # +1 stats

        logger.info(
            "[Task %s] #1712 verify: ChromaDB has %d items "
            "(expected ~%d: %d funcs + %d classes + 1 stats + "
            "%d problems stored during scan)",
            task_id,
            total_count,
            expected_total,
            expected_funcs,
            expected_classes,
            expected_problems,
        )

        if total_count < expected_total // 2 and expected_total > 10:
            logger.warning(
                "[Task %s] #1712 DATA LOSS DETECTED: ChromaDB has %d "
                "items but expected ~%d. Check batch storage logs.",
                task_id,
                total_count,
                expected_total,
            )
    except Exception as e:
        logger.warning("[Task %s] #1712 verify failed: %s", task_id, e)
