# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Storage utilities for Code Pattern Analysis.

Issue #208: ChromaDB integration for code_patterns collection.
Provides vector storage for pattern embeddings and similarity search.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from knowledge.backends import get_async_default_client, get_default_client

logger = get_logger(__name__)

# Module-level project root constant
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Collection configuration
CODE_PATTERNS_COLLECTION = "code_patterns"
CODE_PATTERNS_METADATA = {
    "description": "Code pattern embeddings for similarity search and optimization",
    "hnsw:space": "cosine",
    "hnsw:construction_ef": 200,
    "hnsw:search_ef": 100,
    "hnsw:M": 32,
}


def get_pattern_collection():
    """Get ChromaDB client and code_patterns collection (sync version).

    Note: This function is synchronous and may block the event loop.
    For async contexts, use get_pattern_collection_async() instead.

    Returns:
        ChromaDB collection or None on failure
    """
    try:
        chroma_path = _PROJECT_ROOT / "data" / "chromadb"
        chroma_path.mkdir(parents=True, exist_ok=True)

        chroma_client = get_default_client(db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False)

        collection = chroma_client.get_or_create_collection(
            name=CODE_PATTERNS_COLLECTION,
            metadata=CODE_PATTERNS_METADATA,
        )

        logger.info(
            "ChromaDB %s collection ready (%d items)",
            CODE_PATTERNS_COLLECTION,
            collection.count(),
        )
        return collection

    except Exception as e:
        logger.error("ChromaDB code_patterns connection failed: %s", e)
        return None


async def get_pattern_collection_async():
    """Get ChromaDB client and code_patterns collection (async version).

    Issue #208: Non-blocking async version for FastAPI endpoints.

    Returns:
        AsyncChromaCollection wrapper or None on failure
    """
    try:
        chroma_path = _PROJECT_ROOT / "data" / "chromadb"
        chroma_path.mkdir(parents=True, exist_ok=True)

        async_client = await get_async_default_client(
            db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
        )

        async_collection = await async_client.get_or_create_collection(
            name=CODE_PATTERNS_COLLECTION,
            metadata=CODE_PATTERNS_METADATA,
        )

        count = await async_collection.count()
        logger.info(
            "ChromaDB %s collection ready (%d items)",
            CODE_PATTERNS_COLLECTION,
            count,
        )
        return async_collection

    except Exception as e:
        logger.error("ChromaDB async code_patterns connection failed: %s", e)
        return None


def generate_pattern_id(pattern_data: Dict[str, Any]) -> str:
    """Generate a unique ID for a pattern based on its content.

    Args:
        pattern_data: Pattern data dictionary

    Returns:
        SHA256 hash-based unique ID
    """
    # Create a stable hash from key pattern attributes
    hash_input = f"{pattern_data.get('pattern_type', '')}"
    hash_input += f":{pattern_data.get('file_path', '')}"
    hash_input += f":{pattern_data.get('start_line', '')}"
    hash_input += f":{pattern_data.get('code_hash', '')}"
    # Issue #12384: fold source_id into the ID so two sources with an
    # identical relative file_path/line/code_hash (e.g. both have
    # "app/main.py" with the same duplicate snippet) never collide on the
    # same ChromaDB id and silently overwrite each other's pattern.
    hash_input += f":{pattern_data.get('source_id', 'default')}"

    return hashlib.sha256(hash_input.encode()).hexdigest()[:32]


def sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize metadata for ChromaDB storage.

    ChromaDB only accepts str, int, float, bool values.

    Args:
        metadata: Raw metadata dictionary

    Returns:
        Sanitized metadata dictionary
    """
    sanitized = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        elif isinstance(value, (list, tuple)):
            # Convert lists to comma-separated strings
            if all(isinstance(v, (str, int, float)) for v in value):
                sanitized[key] = ",".join(str(v) for v in value)
        elif isinstance(value, dict):
            # Flatten simple dicts
            for k, v in value.items():
                if isinstance(v, (str, int, float, bool)):
                    sanitized[f"{key}_{k}"] = v
        else:
            # Convert other types to string
            sanitized[key] = str(value)

    return sanitized


def _build_single_pattern_data(pattern_type: str, code_content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Build pattern data dict for single pattern ID generation. Issue #620.

    Args:
        pattern_type: Type of pattern
        code_content: The code content
        metadata: Pattern metadata

    Returns:
        Pattern data dictionary for generate_pattern_id
    """
    return {
        "pattern_type": pattern_type,
        "file_path": metadata.get("file_path", ""),
        "start_line": metadata.get("start_line", 0),
        "code_hash": hashlib.sha256(code_content.encode()).hexdigest()[:16],
        "source_id": metadata.get("source_id", "default"),
    }


def _build_single_pattern_metadata(pattern_type: str, code_content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Build and sanitize metadata for single pattern storage. Issue #620.

    Args:
        pattern_type: Type of pattern
        code_content: The code content
        metadata: Raw pattern metadata

    Returns:
        Sanitized metadata dictionary
    """
    full_metadata = {
        "pattern_type": pattern_type,
        "code_length": len(code_content),
        **metadata,
    }
    return sanitize_metadata(full_metadata)


async def store_pattern(
    pattern_type: str,
    code_content: str,
    embedding: List[float],
    metadata: Dict[str, Any],
    collection=None,
) -> str | None:
    """Store a code pattern in ChromaDB.

    Args:
        pattern_type: Type of pattern (duplicate, regex_opportunity, etc.)
        code_content: The code content being stored
        embedding: Pre-computed embedding vector
        metadata: Additional metadata for the pattern
        collection: Optional pre-fetched collection

    Returns:
        Pattern ID if successful, None otherwise
    """
    try:
        if collection is None:
            collection = await get_pattern_collection_async()
            if collection is None:
                logger.error("Could not get pattern collection")
                return None

        pattern_data = _build_single_pattern_data(pattern_type, code_content, metadata)
        pattern_id = generate_pattern_id(pattern_data)
        sanitized_metadata = _build_single_pattern_metadata(pattern_type, code_content, metadata)

        await collection.add(
            ids=[pattern_id],
            embeddings=[embedding],
            documents=[code_content[:10000]],
            metadatas=[sanitized_metadata],
        )

        logger.debug("Stored pattern %s: %s", pattern_id, pattern_type)
        return pattern_id

    except Exception as e:
        logger.error("Failed to store pattern: %s", e)
        return None


def _prepare_pattern_data(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare pattern data dictionary for ID generation. Issue #620.

    Args:
        pattern: Raw pattern dictionary with pattern_type, code_content, metadata

    Returns:
        Pattern data dictionary suitable for generate_pattern_id
    """
    return {
        "pattern_type": pattern["pattern_type"],
        "file_path": pattern.get("metadata", {}).get("file_path", ""),
        "start_line": pattern.get("metadata", {}).get("start_line", 0),
        "code_hash": hashlib.sha256(pattern["code_content"].encode()).hexdigest()[:16],
        "source_id": pattern.get("metadata", {}).get("source_id", "default"),
    }


def _prepare_pattern_metadata(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare and sanitize metadata for a pattern. Issue #620.

    Args:
        pattern: Raw pattern dictionary with pattern_type, code_content, metadata

    Returns:
        Sanitized metadata dictionary ready for ChromaDB storage
    """
    full_metadata = {
        "pattern_type": pattern["pattern_type"],
        "code_length": len(pattern["code_content"]),
        **pattern.get("metadata", {}),
    }
    return sanitize_metadata(full_metadata)


async def store_patterns_batch(
    patterns: List[Dict[str, Any]],
    collection=None,
) -> int:
    """Store multiple patterns in a single batch operation.

    Args:
        patterns: List of pattern dictionaries with keys:
            - pattern_type: str
            - code_content: str
            - embedding: List[float]
            - metadata: Dict[str, Any]
        collection: Optional pre-fetched collection

    Returns:
        Number of patterns successfully stored
    """
    if not patterns:
        return 0

    try:
        if collection is None:
            collection = await get_pattern_collection_async()
            if collection is None:
                logger.error("Could not get pattern collection")
                return 0

        ids, embeddings, documents, metadatas = [], [], [], []

        for pattern in patterns:
            ids.append(generate_pattern_id(_prepare_pattern_data(pattern)))
            embeddings.append(pattern["embedding"])
            documents.append(pattern["code_content"][:10000])
            metadatas.append(_prepare_pattern_metadata(pattern))

        await collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

        logger.info("Stored %d patterns in batch", len(patterns))
        return len(patterns)

    except Exception as e:
        logger.error("Failed to store patterns batch: %s", e)
        return 0


def _process_search_results(results: Dict[str, Any], min_similarity: float) -> List[Dict[str, Any]]:
    """Process ChromaDB query results into pattern list. Issue #620.

    Args:
        results: Raw ChromaDB query results
        min_similarity: Minimum similarity threshold (0.0 to 1.0)

    Returns:
        List of similar patterns with similarity scores
    """
    similar_patterns = []
    if not results or not results.get("ids") or not results["ids"][0]:
        return similar_patterns

    for i, pattern_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i] if results.get("distances") else 0
        similarity = 1.0 - distance  # Cosine distance to similarity

        if similarity >= min_similarity:
            similar_patterns.append(
                {
                    "id": pattern_id,
                    "similarity": similarity,
                    "document": (results["documents"][0][i] if results.get("documents") else ""),
                    "metadata": (results["metadatas"][0][i] if results.get("metadatas") else {}),
                }
            )

    return similar_patterns


def build_source_scoped_where(
    source_id: str | None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a ChromaDB ``where`` filter scoped to a source, with optional
    extra equality conditions folded in via ``$and``.

    Issue #12384: The ``source_id`` condition is ALWAYS included -- callers
    must never query the shared ``code_patterns`` collection without it, or a
    request for one source could surface another source's (or AutoBot's own)
    stored patterns. Uses the ``source_id or "default"`` sentinel so it
    matches exactly what ``CodePatternAnalyzer`` writes at storage time.

    Note: ChromaDB equality on an ABSENT field matches nothing, so patterns
    stored before this fix (no ``source_id`` key at all) become invisible to
    every query until their source is reindexed. This is intentional
    fail-closed behavior, not a bug -- see #12356/#12374.

    Args:
        source_id: Code source to scope the query to.
        extra: Optional additional equality conditions to AND together.

    Returns:
        ChromaDB-compatible where filter dict.
    """
    conditions = [{"source_id": source_id or "default"}]
    if extra:
        conditions.extend({k: v} for k, v in extra.items())
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


async def search_similar_patterns(
    query_embedding: List[float],
    pattern_type: str | None = None,
    n_results: int = 10,
    min_similarity: float = 0.7,
    collection=None,
    source_id: str | None = None,
) -> List[Dict[str, Any]]:
    """Search for similar patterns using vector similarity.

    Issue #12384: Always scopes the query to ``source_id`` (default sentinel
    when None) so one project can never read another's stored patterns.

    Args:
        query_embedding: Embedding vector to search for
        pattern_type: Optional filter by pattern type
        n_results: Maximum number of results to return
        min_similarity: Minimum similarity threshold (0.0 to 1.0)
        collection: Optional pre-fetched collection
        source_id: Code source this query is scoped to (Issue #12384).

    Returns:
        List of similar patterns with similarity scores
    """
    try:
        if collection is None:
            collection = await get_pattern_collection_async()
            if collection is None:
                logger.error("Could not get pattern collection")
                return []

        where_filter = build_source_scoped_where(
            source_id,
            {"pattern_type": pattern_type} if pattern_type else None,
        )

        results = await collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        return _process_search_results(results, min_similarity)

    except Exception as e:
        logger.error("Failed to search similar patterns: %s", e)
        return []


async def delete_pattern(pattern_id: str, collection=None) -> bool:
    """Delete a pattern from the collection.

    Args:
        pattern_id: ID of the pattern to delete
        collection: Optional pre-fetched collection

    Returns:
        True if successful, False otherwise
    """
    try:
        if collection is None:
            collection = await get_pattern_collection_async()
            if collection is None:
                return False

        await collection.delete(ids=[pattern_id])
        logger.debug("Deleted pattern: %s", pattern_id)
        return True

    except Exception as e:
        logger.error("Failed to delete pattern %s: %s", pattern_id, e)
        return False


async def get_pattern_stats(collection=None, source_id: str | None = None) -> Dict[str, Any]:
    """Get statistics about stored patterns.

    Issue #12384: Scopes the sample/count to ``source_id`` so aggregate stats
    (pattern-type distribution) for one source never include another
    source's stored patterns.

    Args:
        collection: Optional pre-fetched collection
        source_id: Code source to scope the stats to (Issue #12384).

    Returns:
        Dictionary with pattern statistics
    """
    try:
        if collection is None:
            collection = await get_pattern_collection_async()
            if collection is None:
                return {"error": "Collection not available"}

        where_filter = build_source_scoped_where(source_id)
        # #1361: bound the fetch (no scoped count() exists in the ChromaDB API)
        # to stay under the SQLite backend's ~999 SQL-variable limit -- mirrors
        # the sampling already done by get_pattern_stats() pre-#12384.
        sample = await collection.get(
            limit=1000,
            where=where_filter,
            include=["metadatas"],
        )
        metadatas = sample.get("metadatas") or []
        count = len(metadatas)

        if count > 0:
            type_counts: Dict[str, int] = {}
            for meta in metadatas:
                ptype = meta.get("pattern_type", "unknown")
                type_counts[ptype] = type_counts.get(ptype, 0) + 1

            return {
                "total_patterns": count,
                "pattern_type_distribution": type_counts,
                "collection_name": CODE_PATTERNS_COLLECTION,
            }

        return {
            "total_patterns": 0,
            "pattern_type_distribution": {},
            "collection_name": CODE_PATTERNS_COLLECTION,
        }

    except Exception as e:
        logger.error("Failed to get pattern stats: %s", e)
        return {"error": "Failed to retrieve pattern stats"}


async def clear_patterns(collection=None) -> bool:
    """Clear all patterns from the collection.

    WARNING: This is destructive and cannot be undone.

    Args:
        collection: Optional pre-fetched collection

    Returns:
        True if successful, False otherwise
    """
    try:
        if collection is None:
            collection = await get_pattern_collection_async()
            if collection is None:
                return False

        # Get all IDs and delete them
        count = await collection.count()
        if count > 0:
            results = await collection.get(limit=count, include=[])
            if results.get("ids"):
                await collection.delete(ids=results["ids"])

        logger.info("Cleared %d patterns from collection", count)
        return True

    except Exception as e:
        logger.error("Failed to clear patterns: %s", e)
        return False
