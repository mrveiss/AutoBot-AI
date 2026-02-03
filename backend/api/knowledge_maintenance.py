# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base Maintenance API endpoints for bulk operations and cleanup.

This module contains maintenance and bulk operation endpoints extracted from knowledge.py
as part of Issue #185 - splitting oversized files.

Includes:
- Deduplication (simple and advanced)
- Bulk operations (delete, update category)
- Orphaned fact management
- Export/Import functionality
- Knowledge base cleanup
- Host change scanning
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path as PathLib

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

# Import Pydantic models from dedicated module
from backend.api.knowledge_models import (
    BackupRequest,
    BulkCategoryUpdateRequest,
    BulkDeleteRequest,
    CleanupRequest,
    DeduplicationRequest,
    DeleteBackupRequest,
    ExportRequest,
    ImportRequest,
    RestoreRequest,
    ScanHostChangesRequest,
    UpdateFactRequest,
)
from backend.knowledge_factory import get_or_create_knowledge_base
from src.auth_middleware import check_admin_permission
from src.constants.threshold_constants import QueryDefaults
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge_maintenance"])


def _process_fact_metadata(metadata_str, fact_key, created_at) -> dict | None:
    """Process fact metadata and extract grouping info (Issue #315: extracted).

    Returns:
        Dict with fact info if valid, None if invalid
    """
    # Decode key if it's bytes
    if isinstance(fact_key, bytes):
        fact_key = fact_key.decode("utf-8")

    if not metadata_str:
        return None

    try:
        metadata = json.loads(metadata_str)
        return {
            "fact_id": metadata.get("fact_id", fact_key.split(":")[1]),
            "fact_key": fact_key,
            "created_at": created_at or "1970-01-01T00:00:00",
            "category": metadata.get("category", "unknown"),
            "title": metadata.get("title", "unknown"),
        }
    except json.JSONDecodeError:
        logger.warning("Failed to parse metadata for %s", fact_key)
        return None


def _group_fact_by_category_title(fact_info: dict, fact_groups: dict) -> None:
    """Add fact to appropriate group by category:title (Issue #315: extracted)."""
    group_key = f"{fact_info['category']}:{fact_info['title']}"
    if group_key not in fact_groups:
        fact_groups[group_key] = []
    fact_groups[group_key].append(fact_info)


# ===== DEDUPLICATION ENDPOINTS =====


async def _scan_all_facts(kb) -> tuple[dict, int]:
    """Scan all facts and group by category+title (Issue #398: extracted).

    Returns:
        Tuple of (fact_groups dict, total_facts count)
    """
    fact_groups = {}
    cursor = 0
    total_facts = 0

    while True:

        def _scan_and_fetch():
            cur, scanned_keys = kb.redis_client.scan(cursor, match="fact:*", count=100)
            if not scanned_keys:
                return cur, [], []
            pipe = kb.redis_client.pipeline()
            for key in scanned_keys:
                pipe.hget(key, "metadata")
                pipe.hget(key, "created_at")
            pipe_results = pipe.execute()
            return cur, scanned_keys, pipe_results

        cursor, keys, results = await asyncio.to_thread(_scan_and_fetch)

        if keys:
            for i in range(0, len(results), 2):
                fact_info = _process_fact_metadata(
                    results[i], keys[i // 2], results[i + 1]
                )
                if fact_info:
                    _group_fact_by_category_title(fact_info, fact_groups)
                    total_facts += 1

        if cursor == 0:
            break

    return fact_groups, total_facts


def _find_duplicates_in_groups(fact_groups: dict) -> tuple[list, list]:
    """Find duplicates in fact groups, keep oldest (Issue #398: extracted).

    Returns:
        Tuple of (duplicates_found list, facts_to_delete list)
    """
    duplicates_found = []
    facts_to_delete = []

    for group_key, facts in fact_groups.items():
        if len(facts) <= 1:
            continue

        facts.sort(key=lambda x: x["created_at"])
        kept_fact = facts[0]
        duplicate_facts = facts[1:]

        duplicates_found.append(
            {
                "category": kept_fact["category"],
                "title": kept_fact["title"],
                "total_copies": len(facts),
                "kept_fact_id": kept_fact["fact_id"],
                "kept_created_at": kept_fact["created_at"],
                "removed_count": len(duplicate_facts),
                "removed_fact_ids": [f["fact_id"] for f in duplicate_facts],
            }
        )

        facts_to_delete.extend([f["fact_key"] for f in duplicate_facts])

    return duplicates_found, facts_to_delete


async def _delete_facts_in_batches(
    kb, facts_to_delete: list, batch_size: int = 100
) -> int:
    """Delete facts in batches (Issue #398: extracted).

    Returns:
        Number of facts deleted
    """
    deleted_count = 0
    for i in range(0, len(facts_to_delete), batch_size):
        batch = facts_to_delete[i : i + batch_size]
        await asyncio.to_thread(kb.redis_client.delete, *batch)
        deleted_count += len(batch)
    return deleted_count


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="deduplicate_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/deduplicate")
async def deduplicate_facts(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    dry_run: bool = True,
):
    """
    Remove duplicate facts based on category + title (Issue #398: refactored).
    Keeps the oldest fact and removes newer duplicates.

    Issue #744: Requires admin authentication.

    Args:
        dry_run: If True, only report duplicates without deleting (default: True)

    Returns:
        Report of duplicates found and removed
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    logger.info("Starting deduplication scan (dry_run=%s)...", dry_run)

    # Scan and group facts
    fact_groups, total_facts = await _scan_all_facts(kb)
    logger.info(
        f"Scanned {total_facts} facts, found {len(fact_groups)} unique combinations"
    )

    # Find duplicates
    duplicates_found, facts_to_delete = _find_duplicates_in_groups(fact_groups)

    # Delete duplicates if not dry run
    deleted_count = 0
    if not dry_run and facts_to_delete:
        logger.info("Deleting %s duplicate facts...", len(facts_to_delete))
        deleted_count = await _delete_facts_in_batches(kb, facts_to_delete)
        logger.info("Deleted %s duplicate facts", deleted_count)

    return {
        "status": "success",
        "dry_run": dry_run,
        "total_facts_scanned": total_facts,
        "unique_combinations": len(fact_groups),
        "duplicate_groups_found": len(duplicates_found),
        "total_duplicates": len(facts_to_delete),
        "deleted_count": deleted_count,
        "duplicates": duplicates_found[:50],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_duplicates",
    error_code_prefix="KB",
)
@router.post("/deduplicate/advanced")
async def find_duplicates(
    admin_check: bool = Depends(check_admin_permission),
    request: DeduplicationRequest = None,
    req: Request = None,
):
    """
    Find duplicate or near-duplicate facts in the knowledge base.

    Issue #79: Bulk Operations - Deduplication
    Issue #744: Requires admin authentication.

    Request body:
    - similarity_threshold: Threshold for near-duplicates (0.5-1.0, default: 0.95)
    - dry_run: Only report duplicates (default: True)
    - keep_strategy: "newest", "oldest", or "longest" (default: "newest")
    - category: Limit to specific category (optional)
    - max_comparisons: Maximum comparisons to prevent timeout (default: 10000)

    Returns:
    - success: Boolean status
    - total_facts_scanned: Number of facts scanned
    - exact_duplicates: Count of exact duplicates
    - near_duplicates: Count of near-duplicates
    - total_duplicates: Total duplicate pairs found
    - duplicates: List of duplicate pairs with similarity scores
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Deduplication request: threshold={request.similarity_threshold}, "
        f"use_embeddings={request.use_embeddings}, "
        f"dry_run={request.dry_run}, category={request.category}"
    )

    result = await kb.find_duplicates(
        similarity_threshold=request.similarity_threshold,
        use_embeddings=request.use_embeddings,
        category=request.category,
        max_results=request.max_results,
    )

    return result


# ===== DATA QUALITY METRICS (Issue #418) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_data_quality_metrics",
    error_code_prefix="KB",
)
@router.get("/quality")
async def get_data_quality_metrics(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """
    Get comprehensive data quality metrics for the knowledge base.

    Issue #418: Data quality metrics and health dashboard.
    Issue #744: Requires admin authentication.

    Returns comprehensive quality analysis including:
    - Overall quality score (0-100)
    - Dimension scores:
      - Completeness: How complete is the metadata
      - Consistency: How consistent is the data format
      - Freshness: How recent is the data
      - Uniqueness: How unique is the data (duplicates)
      - Validity: Is the data valid and well-formed
    - Issues: Specific problems found with severity levels
    - Recommendations: Suggested actions to improve quality

    Returns:
    - status: success or error
    - overall_score: Weighted quality score (0-100)
    - dimensions: Per-dimension scores and details
    - summary: Quick overview of issues
    - issues: List of specific problems found
    - recommendations: Actions to improve quality
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info("Data quality metrics requested")

    result = await kb.get_data_quality_metrics()

    return result


def _determine_health_status(stats: dict, quality: dict) -> str:
    """
    Determine overall health status from stats and quality metrics. Issue #620.

    Args:
        stats: Knowledge base statistics dict
        quality: Data quality metrics dict

    Returns:
        Health status string: "healthy", "warning", "degraded", or "error"
    """
    if stats.get("status") == "error":
        return "error"

    overall_score = quality.get("overall_score", 100)
    if overall_score < 50:
        return "degraded"
    if overall_score < 70:
        return "warning"
    return "healthy"


def _build_stats_summary(stats: dict) -> dict:
    """
    Build stats summary dict from raw stats. Issue #620.

    Args:
        stats: Raw knowledge base statistics

    Returns:
        Formatted stats summary dict
    """
    return {
        "total_facts": stats.get("total_facts", 0),
        "total_vectors": stats.get("total_vectors", 0),
        "db_size": stats.get("db_size", 0),
        "categories": len(stats.get("categories", [])),
        "embedding_cache": stats.get("embedding_cache", {}),
    }


def _build_quality_summary(quality: dict) -> dict:
    """
    Build quality summary dict from raw quality metrics. Issue #620.

    Args:
        quality: Raw data quality metrics

    Returns:
        Formatted quality summary dict
    """
    return {
        "overall_score": quality.get("overall_score", 0),
        "dimensions": {
            dim: data.get("score", 0)
            for dim, data in quality.get("dimensions", {}).items()
        },
        "critical_issues": quality.get("summary", {}).get("critical_issues", 0),
        "warnings": quality.get("summary", {}).get("warnings", 0),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_health_dashboard",
    error_code_prefix="KB",
)
@router.get("/health/dashboard")
async def get_health_dashboard(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """
    Get a combined health dashboard with stats and quality metrics.

    Issue #418: Health dashboard endpoint.
    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.

    Returns:
    - status: Overall system status
    - stats: Knowledge base statistics
    - quality: Data quality metrics summary
    - last_updated: Dashboard generation timestamp
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info("Health dashboard requested")

    stats, quality = await asyncio.gather(kb.get_stats(), kb.get_data_quality_metrics())

    return {
        "status": _determine_health_status(stats, quality),
        "last_updated": datetime.now().isoformat(),
        "stats": _build_stats_summary(stats),
        "quality": _build_quality_summary(quality),
        "top_recommendations": quality.get("recommendations", [])[:3],
    }


# ===== HOST CHANGE SCANNING =====


def _create_vectorization_result() -> dict:
    """Create initial vectorization result structure (Issue #281: extracted)."""
    return {
        "attempted": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }


def _add_vectorization_detail(
    results: dict, doc_id: str, command: str, status: str, **kwargs
) -> None:
    """
    Add a detail entry to vectorization results. Issue #620.

    Args:
        results: Results dict to update
        doc_id: Document ID
        command: Command name
        status: Status string (skipped, failed, success, error)
        **kwargs: Additional fields (reason, fact_id)
    """
    detail = {"doc_id": doc_id, "command": command, "status": status}
    detail.update(kwargs)
    results["details"].append(detail)


def _build_document_metadata(
    doc_change: dict, machine_id: str, content_size: int
) -> dict:
    """
    Build metadata dict for knowledge base document. Issue #620.

    Args:
        doc_change: Document change info
        machine_id: Machine identifier
        content_size: Size of content

    Returns:
        Metadata dictionary
    """
    return {
        "category": "system/manpages",
        "title": f"man {doc_change.get('command')}",
        "command": doc_change.get("command"),
        "machine_id": machine_id,
        "file_path": doc_change.get("file_path"),
        "document_id": doc_change.get("document_id"),
        "change_type": doc_change.get("change_type"),
        "content_size": content_size,
    }


async def _vectorize_single_document(
    kb, scanner, doc_change: dict, machine_id: str, results: dict
) -> None:
    """
    Vectorize a single document and update results.

    Issue #281: Originally extracted from larger function.
    Issue #620: Further refactored with helper methods.
    """
    results["attempted"] += 1

    command = doc_change.get("command")
    file_path = doc_change.get("file_path")
    doc_id = doc_change.get("document_id")

    # Validate required fields
    if not file_path or not command:
        results["skipped"] += 1
        _add_vectorization_detail(
            results, doc_id, command, "skipped", reason="Missing file_path or command"
        )
        return

    try:
        # Read and validate content
        content = scanner.read_man_page_content(file_path, command)

        if not content or len(content.strip()) < 10:
            results["failed"] += 1
            _add_vectorization_detail(
                results, doc_id, command, "failed", reason="Empty or too short content"
            )
            return

        # Issue #620: Extracted metadata building
        metadata = _build_document_metadata(doc_change, machine_id, len(content))

        # Add to knowledge base
        kb_result = await kb.add_document(
            content=content, metadata=metadata, doc_id=doc_id
        )

        if kb_result.get("status") == "success":
            results["successful"] += 1
            _add_vectorization_detail(
                results, doc_id, command, "success", fact_id=kb_result.get("fact_id")
            )
        else:
            results["failed"] += 1
            _add_vectorization_detail(
                results,
                doc_id,
                command,
                "failed",
                reason=kb_result.get("message", "Unknown error"),
            )

    except Exception as e:
        logger.error("Vectorization failed for %s: %s", command, e)
        results["failed"] += 1
        _add_vectorization_detail(results, doc_id, command, "error", reason=str(e))


async def _process_vectorization(kb, scanner, result: dict, machine_id: str) -> dict:
    """Process vectorization for added/updated documents (Issue #281: extracted)."""
    vectorization_results = _create_vectorization_result()

    # Vectorize added and updated documents
    documents_to_vectorize = result["changes"]["added"] + result["changes"]["updated"]

    for doc_change in documents_to_vectorize:
        await _vectorize_single_document(
            kb, scanner, doc_change, machine_id, vectorization_results
        )

    logger.info(
        f"Vectorization completed: "
        f"{vectorization_results['successful']}/{vectorization_results['attempted']} successful"
    )

    return vectorization_results


def _extract_scan_params(request_data: ScanHostChangesRequest) -> tuple:
    """
    Extract and return scan parameters from request. Issue #620.

    Args:
        request_data: The scan host changes request

    Returns:
        Tuple of (machine_id, force, scan_type, auto_vectorize)
    """
    return (
        request_data.machine_id,
        request_data.force,
        request_data.scan_type,
        request_data.auto_vectorize,
    )


def _perform_fast_scan(
    redis_client, machine_id: str, scan_type: str, force: bool
) -> tuple:
    """
    Initialize scanner and perform fast document scan. Issue #620.

    Args:
        redis_client: Redis client instance
        machine_id: Machine identifier
        scan_type: Type of scan to perform
        force: Whether to force rescan

    Returns:
        Tuple of (scanner instance, scan result dict)
    """
    from backend.services.fast_document_scanner import FastDocumentScanner

    scanner = FastDocumentScanner(redis_client)
    result = scanner.scan_for_changes(
        machine_id=machine_id,
        scan_type=scan_type,
        limit=100,
        force=force,
    )
    return scanner, result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_host_changes",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/scan_host_changes")
async def scan_host_changes(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    request_data: ScanHostChangesRequest = None,
):
    """
    ULTRA-FAST document change scanner using file metadata.

    Issue #281: Refactored from 162 lines to use extracted helper methods.
    Issue #620: Further refactored with Extract Method pattern.
    Issue #744: Requires admin authentication.

    Performance: ~0.5 seconds for 10,000 documents (100x faster than subprocess approach)

    Args:
        request_data: Scan configuration with machine_id, force, and scan_type

    Returns:
        Dictionary with change detection results
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    machine_id, force, scan_type, auto_vectorize = _extract_scan_params(request_data)

    logger.info(
        f"Fast scan starting for {machine_id} (type={scan_type}, auto_vectorize={auto_vectorize})"
    )

    scanner, result = _perform_fast_scan(kb.redis_client, machine_id, scan_type, force)

    if auto_vectorize:
        result["vectorization"] = await _process_vectorization(
            kb, scanner, result, machine_id
        )

    return result


# ===== ORPHANED FACTS MANAGEMENT =====


def _decode_key(key) -> str:
    """Decode Redis key from bytes if needed."""
    return key.decode("utf-8") if isinstance(key, bytes) else key


def _check_orphaned_fact(key: str, metadata_str) -> tuple:
    """
    Check if a fact is orphaned (source file doesn't exist).

    Returns:
        Tuple of (is_file_based: bool, is_orphaned: bool, orphan_info: dict or None)
    """
    if not metadata_str:
        return False, False, None

    try:
        metadata = json.loads(metadata_str)
    except json.JSONDecodeError:
        logger.warning("Failed to parse metadata for %s", key)
        return False, False, None

    file_path = metadata.get("file_path")
    if not file_path:
        return False, False, None

    # This is a file-based fact
    if PathLib(file_path).exists():
        return True, False, None

    # File doesn't exist - this is an orphan
    return (
        True,
        True,
        {
            "fact_id": metadata.get("fact_id"),
            "fact_key": key,
            "title": metadata.get("title", "Unknown"),
            "category": metadata.get("category", "Unknown"),
            "file_path": file_path,
            "source": metadata.get("source", "Unknown"),
        },
    )


def _process_orphan_batch(keys: list, results: list) -> tuple:
    """
    Process a batch of facts and identify orphans.

    Returns:
        Tuple of (file_based_count, orphaned_facts_list)
    """
    file_based_count = 0
    orphaned_facts = []

    for key, metadata_str in zip(keys, results):
        key = _decode_key(key)
        is_file_based, is_orphan, orphan_info = _check_orphaned_fact(key, metadata_str)

        if is_file_based:
            file_based_count += 1
        if is_orphan and orphan_info:
            orphaned_facts.append(orphan_info)

    return file_based_count, orphaned_facts


def _scan_redis_for_orphans(redis_client) -> tuple:
    """
    Scan Redis for orphaned facts (file-based facts with missing source files). Issue #620.

    Args:
        redis_client: Redis client instance

    Returns:
        Tuple of (total_checked, orphaned_facts_list)
    """
    orphaned_facts = []
    cursor = 0
    total_checked = 0

    while True:
        cursor, keys = redis_client.scan(cursor, match="fact:*", count=100)

        if not keys:
            if cursor == 0:
                break
            continue

        pipe = redis_client.pipeline()
        for key in keys:
            pipe.hget(key, "metadata")
        results = pipe.execute()

        batch_checked, batch_orphans = _process_orphan_batch(keys, results)
        total_checked += batch_checked
        orphaned_facts.extend(batch_orphans)

        if cursor == 0:
            break

    return total_checked, orphaned_facts


def _build_orphan_response(total_checked: int, orphaned_facts: list) -> dict:
    """
    Build the response dict for orphan finding operations. Issue #620.

    Args:
        total_checked: Number of facts checked
        orphaned_facts: List of orphaned facts

    Returns:
        Response dict with status and orphan info
    """
    return {
        "status": "success",
        "total_facts_checked": total_checked,
        "orphaned_count": len(orphaned_facts),
        "orphaned_facts": orphaned_facts,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/orphans")
async def find_orphaned_facts(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """
    Find facts whose source files no longer exist.

    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.

    Returns:
        List of orphaned facts with file_path metadata
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    logger.info("Scanning for orphaned facts...")

    total_checked, orphaned_facts = await asyncio.to_thread(
        _scan_redis_for_orphans, kb.redis_client
    )

    logger.info(
        f"Checked {total_checked} facts with file paths, found {len(orphaned_facts)} orphans"
    )

    return _build_orphan_response(total_checked, orphaned_facts)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/orphans")
async def cleanup_orphaned_facts(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    dry_run: bool = True,
):
    """
    Remove facts whose source files no longer exist.

    Issue #744: Requires admin authentication.

    Args:
        dry_run: If True, only report orphans without deleting (default: True)

    Returns:
        Report of orphans found and removed
    """
    # First find orphans
    orphans_response = await find_orphaned_facts(req)
    orphaned_facts = orphans_response.get("orphaned_facts", [])

    if not orphaned_facts:
        return {
            "status": "success",
            "message": "No orphaned facts found",
            "deleted_count": 0,
        }

    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    # Delete orphans if not dry run
    deleted_count = 0
    if not dry_run:
        logger.info("Deleting %s orphaned facts...", len(orphaned_facts))

        fact_keys = [f["fact_key"] for f in orphaned_facts]

        # Issue #361 - avoid blocking - delete orphans in thread pool
        def _delete_orphan_batches():
            count = 0
            batch_size = 100
            for i in range(0, len(fact_keys), batch_size):
                batch = fact_keys[i : i + batch_size]
                kb.redis_client.delete(*batch)
                count += len(batch)
            return count

        deleted_count = await asyncio.to_thread(_delete_orphan_batches)

        logger.info("Deleted %s orphaned facts", deleted_count)

    return {
        "status": "success",
        "dry_run": dry_run,
        "orphaned_count": len(orphaned_facts),
        "deleted_count": deleted_count,
        "orphaned_facts": orphaned_facts[:20],  # Return first 20 for preview
    }


# ===== SESSION-ORPHAN MANAGEMENT (Issue #547) =====


def _parse_fact_metadata(fact_data: dict) -> dict | None:
    """Parse metadata from fact data, handling bytes/str and JSON parsing."""
    metadata_str = fact_data.get(b"metadata") or fact_data.get("metadata")
    if not metadata_str:
        return None

    try:
        if isinstance(metadata_str, bytes):
            metadata_str = metadata_str.decode("utf-8")
        return json.loads(metadata_str)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _build_orphan_fact_info(
    key, fact_data: dict, metadata: dict, source_session_id: str
) -> dict:
    """Build orphan fact information dictionary."""
    fact_key = key.decode("utf-8") if isinstance(key, bytes) else key
    fact_id = fact_key.replace("fact:", "")

    content = fact_data.get(b"content") or fact_data.get("content", b"")
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    return {
        "fact_id": fact_id,
        "fact_key": fact_key,
        "session_id": source_session_id,
        "content_preview": content[:200] + ("..." if len(content) > 200 else ""),
        "category": metadata.get("category", "unknown"),
        "created_at": metadata.get("created_at"),
        "important": metadata.get("important", False),
        "preserve": metadata.get("preserve", False),
    }


def _scan_redis_for_session_orphans(redis_client, existing_session_ids: set) -> tuple:
    """
    Scan Redis for session-orphan facts.

    Args:
        redis_client: Redis client for scanning
        existing_session_ids: Set of valid session IDs

    Returns:
        Tuple of (total_checked, total_with_session, orphaned_facts, session_stats)
    """
    orphaned_facts = []
    session_stats = {}  # session_id -> count
    cursor = 0
    total_checked = 0
    total_with_session = 0

    while True:
        cursor, keys = redis_client.scan(cursor, match="fact:*", count=100)

        if not keys:
            if cursor == 0:
                break
            continue

        # Use pipeline for batch metadata fetch
        pipe = redis_client.pipeline()
        for key in keys:
            pipe.hgetall(key)
        results = pipe.execute()

        for key, fact_data in zip(keys, results):
            if not fact_data:
                continue

            total_checked += 1
            metadata = _parse_fact_metadata(fact_data)
            if not metadata:
                continue

            source_session_id = metadata.get("source_session_id")
            if not source_session_id:
                continue

            total_with_session += 1

            # Check if this session still exists
            if source_session_id not in existing_session_ids:
                orphaned_facts.append(
                    _build_orphan_fact_info(key, fact_data, metadata, source_session_id)
                )
                session_stats[source_session_id] = (
                    session_stats.get(source_session_id, 0) + 1
                )

        if cursor == 0:
            break

    return total_checked, total_with_session, orphaned_facts, session_stats


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_session_orphans",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/session-orphans")
async def find_session_orphan_facts(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """
    Find facts from deleted chat sessions (session-orphans).

    Issue #547: Detects facts that have source_session_id metadata pointing
    to sessions that no longer exist. These are orphaned data from deleted
    conversations.
    Issue #744: Requires admin authentication.

    Returns:
        List of facts with their session_id and fact details
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    from backend.utils.chat_utils import get_chat_history_manager

    chat_manager = get_chat_history_manager(req)
    if chat_manager is None:
        raise HTTPException(
            status_code=500, detail="Chat history manager not available"
        )

    existing_sessions = await chat_manager.list_sessions_fast()
    existing_session_ids = {s["id"] for s in existing_sessions}

    logger.info(
        "Scanning for session-orphan facts (existing sessions: %d)",
        len(existing_session_ids),
    )

    (
        total_checked,
        total_with_session,
        orphaned_facts,
        session_stats,
    ) = await asyncio.to_thread(
        _scan_redis_for_session_orphans, kb.redis_client, existing_session_ids
    )

    logger.info(
        "Session-orphan scan: checked %d facts, %d with session tracking, %d orphans found",
        total_checked,
        total_with_session,
        len(orphaned_facts),
    )

    return {
        "status": "success",
        "total_facts_checked": total_checked,
        "facts_with_session_tracking": total_with_session,
        "orphaned_count": len(orphaned_facts),
        "orphaned_sessions": len(session_stats),
        "session_breakdown": session_stats,
        "orphaned_facts": orphaned_facts[:50],
    }


async def _delete_orphan_facts(
    kb, orphaned_facts: list, preserve_important: bool
) -> tuple:
    """
    Delete orphan facts with optional preservation (Issue #665: extracted helper).

    Returns:
        Tuple of (deleted_count, preserved_count, preserved_facts_list)
    """
    deleted_count = 0
    preserved_count = 0
    preserved_facts = []

    for fact in orphaned_facts:
        if preserve_important and (fact.get("important") or fact.get("preserve")):
            preserved_count += 1
            preserved_facts.append(
                {"fact_id": fact["fact_id"], "reason": "marked as important/preserve"}
            )
            continue

        try:
            result = await kb.delete_fact(fact["fact_id"])
            if result.get("status") == "success":
                deleted_count += 1
            else:
                logger.warning(
                    "Failed to delete fact %s: %s",
                    fact["fact_id"],
                    result.get("message"),
                )
        except Exception as e:
            logger.error("Error deleting fact %s: %s", fact["fact_id"], e)

    return deleted_count, preserved_count, preserved_facts


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_session_orphans",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/session-orphans")
async def cleanup_session_orphan_facts(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    dry_run: bool = Query(True, description="If True, only report without deleting"),
    preserve_important: bool = Query(
        True, description="Keep facts marked as important"
    ),
):
    """
    Remove facts from deleted chat sessions.

    Issue #547: Cleans up orphaned KB data from deleted conversations.
    Issue #665: Refactored to use extracted helper.
    Issue #744: Requires admin authentication.

    Args:
        dry_run: If True, only report orphans without deleting (default: True)
        preserve_important: If True, keep facts marked as important/preserve (default: True)
    """
    orphans_response = await find_session_orphan_facts(req)
    orphaned_facts = orphans_response.get("orphaned_facts", [])

    if not orphaned_facts:
        return {
            "status": "success",
            "message": "No session-orphaned facts found",
            "deleted_count": 0,
            "preserved_count": 0,
        }

    deleted_count = 0
    preserved_count = 0
    preserved_facts = []

    if not dry_run:
        logger.info(
            "Cleaning up %d session-orphan facts (preserve_important=%s)",
            len(orphaned_facts),
            preserve_important,
        )
        kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
        deleted_count, preserved_count, preserved_facts = await _delete_orphan_facts(
            kb, orphaned_facts, preserve_important
        )
        logger.info(
            "Session-orphan cleanup: deleted=%d, preserved=%d",
            deleted_count,
            preserved_count,
        )

    return {
        "status": "success",
        "dry_run": dry_run,
        "orphaned_count": orphans_response.get("orphaned_count", 0),
        "deleted_count": deleted_count,
        "preserved_count": preserved_count,
        "preserved_facts": preserved_facts[:20] if preserved_facts else None,
        "session_breakdown": orphans_response.get("session_breakdown", {}),
    }


# ===== IMPORT/EXPORT OPERATIONS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_for_unimported_files",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/import/scan")
async def scan_for_unimported_files(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    directory: str = "docs",
):
    """Scan directory for files that need to be imported

    Issue #744: Requires admin authentication.
    """
    from backend.models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    # Use project-relative path instead of absolute path
    base_path = PathLib(__file__).parent.parent.parent
    scan_path = base_path / directory

    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(scan_path.exists):
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    unimported = []
    needs_reimport = []

    # Scan for markdown files
    # Issue #358 - avoid blocking with lambda for proper rglob() execution in thread
    md_files = await asyncio.to_thread(lambda: list(scan_path.rglob("*.md")))
    for file_path in md_files:
        if tracker.needs_reimport(str(file_path)):
            if tracker.is_imported(str(file_path)):
                needs_reimport.append(str(file_path.relative_to(base_path)))
            else:
                unimported.append(str(file_path.relative_to(base_path)))

    return {
        "status": "success",
        "directory": directory,
        "unimported_files": unimported,
        "needs_reimport": needs_reimport,
        "total_unimported": len(unimported),
        "total_needs_reimport": len(needs_reimport),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_knowledge",
    error_code_prefix="KB",
)
@router.post("/export")
async def export_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: ExportRequest = None,
    req: Request = None,
):
    """
    Export knowledge base facts to JSON, CSV, or Markdown.

    Issue #79: Bulk Operations - Export functionality
    Issue #744: Requires admin authentication.

    Request body:
    - format: "json", "csv", or "markdown" (default: "json")
    - filters: Optional filters (categories, tags, date_from, date_to, fact_ids)
    - include_metadata: Include metadata in export (default: True)
    - include_tags: Include tags in export (default: True)
    - include_embeddings: Include vector embeddings (default: False, large file)

    Returns:
    - success: Boolean status
    - format: Export format used
    - total_facts: Number of facts exported
    - data: Export data as string
    - exported_at: ISO timestamp
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    # Extract filters
    filters = request.filters
    categories = filters.categories if filters else None
    tags = filters.tags if filters else None
    fact_ids = filters.fact_ids if filters else None
    date_from = filters.date_from if filters else None
    date_to = filters.date_to if filters else None

    logger.info(
        f"Export request: format={request.format.value}, include_metadata={request.include_metadata}"
    )

    result = await kb.export_facts(
        format=request.format.value,
        categories=categories,
        tags=tags,
        fact_ids=fact_ids,
        date_from=date_from,
        date_to=date_to,
        include_metadata=request.include_metadata,
        include_tags=request.include_tags,
        include_embeddings=request.include_embeddings,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="import_knowledge",
    error_code_prefix="KB",
)
@router.post("/import")
async def import_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: ImportRequest = None,
    req: Request = None,
    data: str = Query(..., description="Import data string"),
):
    """
    Import facts into the knowledge base from JSON or CSV.

    Issue #79: Bulk Operations - Import functionality
    Issue #744: Requires admin authentication.

    Query parameters:
    - data: The import data as a string

    Request body:
    - format: "json" or "csv" (default: "json")
    - validate_only: Only validate without importing (default: False)
    - skip_duplicates: Skip existing facts (default: True)
    - overwrite_existing: Overwrite existing facts (default: False)
    - default_category: Default category for imported facts (default: "imported")

    Returns:
    - success: Boolean status
    - total_facts: Total facts in import data
    - imported: Number of facts imported
    - skipped: Number of facts skipped
    - overwritten: Number of facts overwritten
    - errors: Any import errors
    - validation_errors: Any validation errors
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Import request: format={request.format.value}, validate_only={request.validate_only}"
    )

    result = await kb.import_facts(
        data=data,
        format=request.format.value,
        validate_only=request.validate_only,
        skip_duplicates=request.skip_duplicates,
        overwrite_existing=request.overwrite_existing,
        default_category=request.default_category,
    )

    return result


# ===== FACT MANAGEMENT ENDPOINTS =====


def _validate_update_fact_request(fact_id: str, request: UpdateFactRequest) -> None:
    """
    Validate update fact request parameters. Issue #620.

    Args:
        fact_id: The fact ID to validate
        request: The update request to validate

    Raises:
        HTTPException: If validation fails
    """
    if not fact_id or not isinstance(fact_id, str):
        raise HTTPException(status_code=400, detail="Invalid fact_id format")

    if request.content is None and request.metadata is None:
        raise HTTPException(
            status_code=400,
            detail="At least one field (content or metadata) must be provided",
        )


async def _get_kb_with_method(req: Request, method_name: str) -> object:
    """
    Get knowledge base instance and verify it has the required method. Issue #620.

    Args:
        req: FastAPI request object
        method_name: Name of method that must exist on kb

    Returns:
        Knowledge base instance

    Raises:
        HTTPException: If kb not initialized or method not available
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    if not hasattr(kb, method_name):
        op_name = method_name.replace("_", " ").title()
        raise HTTPException(
            status_code=501,
            detail=f"{op_name} operation not supported by current KB implementation",
        )

    return kb


def _handle_update_fact_result(result: dict, fact_id: str) -> dict:
    """
    Handle the result from kb.update_fact and return appropriate response. Issue #620.

    Args:
        result: Result dict from kb.update_fact
        fact_id: The fact ID that was updated

    Returns:
        Success response dict

    Raises:
        HTTPException: If update failed
    """
    if result.get("success"):
        return {
            "status": "success",
            "fact_id": fact_id,
            "updated_fields": result.get("updated_fields", []),
            "vector_updated": result.get("vector_updated", False),
            "message": result.get("message", "Fact updated successfully"),
        }

    error_message = result.get("message", "Unknown error")
    if "not found" in error_message.lower():
        raise HTTPException(status_code=404, detail=error_message)
    raise HTTPException(status_code=500, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_fact",
    error_code_prefix="KNOWLEDGE",
)
@router.put("/fact/{fact_id}")
async def update_fact(
    admin_check: bool = Depends(check_admin_permission),
    fact_id: str = Path(..., description="Fact ID to update"),
    request: UpdateFactRequest = ...,
    req: Request = None,
):
    """
    Update an existing knowledge base fact.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored using Extract Method pattern.

    Parameters:
    - fact_id: UUID of the fact to update
    - content (optional): New text content
    - metadata (optional): Metadata updates (title, source, category)

    Returns:
    - status: success or error
    - fact_id: ID of the updated fact
    - updated_fields: List of fields that were updated
    - message: Success or error message
    """
    _validate_update_fact_request(fact_id, request)

    kb = await _get_kb_with_method(req, "update_fact")

    content_status = "provided" if request.content else "unchanged"
    metadata_status = "provided" if request.metadata else "unchanged"
    logger.info(
        f"Updating fact {fact_id}: content={content_status}, metadata={metadata_status}"
    )

    result = await kb.update_fact(
        fact_id=fact_id, content=request.content, metadata=request.metadata
    )

    return _handle_update_fact_result(result, fact_id)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_fact",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/fact/{fact_id}")
async def delete_fact(
    admin_check: bool = Depends(check_admin_permission),
    fact_id: str = Path(..., description="Fact ID to delete"),
    req: Request = None,
):
    """
    Delete a knowledge base fact and its vectorization.

    Issue #744: Requires admin authentication.

    Parameters:
    - fact_id: UUID of the fact to delete

    Returns:
    - status: success or error
    - fact_id: ID of the deleted fact
    - message: Success or error message
    """
    # Validate fact_id format
    if not fact_id or not isinstance(fact_id, str):
        raise HTTPException(status_code=400, detail="Invalid fact_id format")

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    # Check if delete_fact method exists (KnowledgeBaseV2)
    if not hasattr(kb, "delete_fact"):
        raise HTTPException(
            status_code=501,
            detail="Delete operation not supported by current knowledge base implementation",
        )

    logger.info("Deleting fact %s", fact_id)

    # Call delete_fact method
    result = await kb.delete_fact(fact_id=fact_id)

    # Check if deletion was successful
    if result.get("success"):
        return {
            "status": "success",
            "fact_id": fact_id,
            "vector_deleted": result.get("vector_deleted", False),
            "message": result.get("message", "Fact deleted successfully"),
        }
    else:
        # Deletion failed - return error
        error_message = result.get("message", "Unknown error")
        if "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        else:
            raise HTTPException(status_code=500, detail=error_message)


# ===== BULK OPERATION ENDPOINTS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="bulk_delete",
    error_code_prefix="KB",
)
@router.delete("/bulk")
async def bulk_delete_facts(
    admin_check: bool = Depends(check_admin_permission),
    request: BulkDeleteRequest = None,
    req: Request = None,
):
    """
    Delete multiple facts at once.

    Issue #79: Bulk Operations - Bulk delete
    Issue #744: Requires admin authentication.

    Request body:
    - fact_ids: List of fact IDs to delete (max 500)
    - confirm: Must be True to actually delete (default: False)

    Returns:
    - success: Boolean status
    - deleted: Number of facts deleted
    - not_found: Number of facts not found
    - errors: Any deletion errors
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        "Bulk delete request: %s facts, confirm=%s",
        len(request.fact_ids),
        request.confirm,
    )

    result = await kb.bulk_delete(
        fact_ids=request.fact_ids,
        confirm=request.confirm,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="bulk_update_category",
    error_code_prefix="KB",
)
@router.post("/bulk/category")
async def bulk_update_category(
    admin_check: bool = Depends(check_admin_permission),
    request: BulkCategoryUpdateRequest = None,
    req: Request = None,
):
    """
    Update category for multiple facts at once.

    Issue #79: Bulk Operations - Bulk category update
    Issue #744: Requires admin authentication.

    Request body:
    - fact_ids: List of fact IDs to update (max 500)
    - new_category: New category to assign

    Returns:
    - success: Boolean status
    - updated: Number of facts updated
    - not_found: Number of facts not found
    - errors: Any update errors
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Bulk category update: {len(request.fact_ids)} facts → {request.new_category}"
    )

    result = await kb.bulk_update_category(
        fact_ids=request.fact_ids,
        new_category=request.new_category,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_knowledge_base",
    error_code_prefix="KB",
)
@router.post("/cleanup")
async def cleanup_knowledge_base(
    admin_check: bool = Depends(check_admin_permission),
    request: CleanupRequest = None,
    req: Request = None,
):
    """
    Clean up the knowledge base.

    Issue #79: Bulk Operations - Cleanup
    Issue #744: Requires admin authentication.

    Request body:
    - remove_empty: Remove facts with empty content (default: True)
    - remove_orphaned_tags: Remove tags with no facts (default: True)
    - fix_metadata: Fix malformed metadata JSON (default: True)
    - dry_run: Only report issues without fixing (default: True)

    Returns:
    - success: Boolean status
    - dry_run: Whether this was a dry run
    - issues_found: Count of issues by type
    - issues_details: Details of issues (only in dry_run mode)
    - fixes_applied: Count of fixes applied (only when not dry_run)
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Cleanup request: dry_run={request.dry_run}, "
        f"remove_empty={request.remove_empty}, remove_orphaned_tags={request.remove_orphaned_tags}"
    )

    result = await kb.cleanup(
        remove_empty=request.remove_empty,
        remove_orphaned_tags=request.remove_orphaned_tags,
        fix_metadata=request.fix_metadata,
        dry_run=request.dry_run,
    )

    return result


# ===== BACKUP AND RESTORE ENDPOINTS (Issue #419) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_backup",
    error_code_prefix="KB",
)
@router.post("/backup")
async def create_backup(
    admin_check: bool = Depends(check_admin_permission),
    request: BackupRequest = None,
    req: Request = None,
):
    """
    Create a backup of the knowledge base.

    Issue #419: Backup and restore functionality.
    Issue #744: Requires admin authentication.

    Request body:
    - include_embeddings: Include vector embeddings (default: True, larger file)
    - include_metadata: Include backup metadata (default: True)
    - compression: Use gzip compression (default: True)
    - description: Optional description for the backup

    Returns:
    - status: success or error
    - backup_file: Path to created backup file
    - backup_name: Name of the backup
    - facts_count: Number of facts in backup
    - file_size: Size of backup file in bytes
    - created_at: ISO timestamp of backup creation
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Backup request: embeddings={request.include_embeddings}, "
        f"compression={request.compression}"
    )

    result = await kb.create_backup(
        include_embeddings=request.include_embeddings,
        include_metadata=request.include_metadata,
        compression=request.compression,
        description=request.description,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="restore_backup",
    error_code_prefix="KB",
)
@router.post("/restore")
async def restore_backup(
    admin_check: bool = Depends(check_admin_permission),
    request: RestoreRequest = None,
    req: Request = None,
):
    """
    Restore knowledge base from a backup file.

    Issue #419: Backup and restore functionality.
    Issue #744: Requires admin authentication.

    Request body:
    - backup_file: Path to backup file (required)
    - overwrite_existing: Overwrite existing facts (default: False)
    - skip_duplicates: Skip duplicate facts (default: True)
    - restore_embeddings: Restore vector embeddings (default: True)
    - dry_run: Only validate, don't restore (default: True)

    Returns:
    - status: success or error
    - mode: "dry_run" or "restore"
    - backup_version: Version of backup format
    - backup_created_at: When the backup was created
    - total_facts_in_backup: Number of facts in backup
    - restored: Number of facts restored (if not dry_run)
    - skipped: Number of facts skipped (if not dry_run)
    - updated: Number of facts updated (if not dry_run)
    - errors: Number of errors (if not dry_run)
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Restore request: file={request.backup_file}, "
        f"dry_run={request.dry_run}, overwrite={request.overwrite_existing}"
    )

    result = await kb.restore_backup(
        backup_file=request.backup_file,
        overwrite_existing=request.overwrite_existing,
        skip_duplicates=request.skip_duplicates,
        restore_embeddings=request.restore_embeddings,
        dry_run=request.dry_run,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_backups",
    error_code_prefix="KB",
)
@router.get("/backups")
async def list_backups(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    limit: int = Query(
        default=QueryDefaults.DEFAULT_PAGE_SIZE,
        ge=1,
        le=200,
        description="Max backups to return",
    ),
):
    """
    List available knowledge base backups.

    Issue #419: Backup and restore functionality.
    Issue #744: Requires admin authentication.

    Query parameters:
    - limit: Maximum number of backups to return (default: 50, max: 200)

    Returns:
    - status: success or error
    - backup_dir: Directory containing backups
    - backups: List of backup files with metadata
    - total_count: Total number of backups found
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info("List backups request: limit=%s", limit)

    result = await kb.list_backups(limit=limit)

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_backup",
    error_code_prefix="KB",
)
@router.delete("/backup")
async def delete_backup(
    admin_check: bool = Depends(check_admin_permission),
    request: DeleteBackupRequest = None,
    req: Request = None,
):
    """
    Delete a knowledge base backup file.

    Issue #419: Backup and restore functionality.
    Issue #744: Requires admin authentication.

    Request body:
    - backup_file: Path to backup file to delete (required)

    Returns:
    - status: success or error
    - deleted_file: Path of deleted backup file
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info("Delete backup request: file=%s", request.backup_file)

    result = await kb.delete_backup(backup_file=request.backup_file)

    return result
