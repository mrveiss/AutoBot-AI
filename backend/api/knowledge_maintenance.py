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
from pathlib import Path as PathLib
from fastapi import APIRouter, HTTPException, Path, Query, Request

# Import Pydantic models from dedicated module
from backend.api.knowledge_models import (
    BulkCategoryUpdateRequest,
    BulkDeleteRequest,
    CleanupRequest,
    DeduplicationRequest,
    ExportRequest,
    ImportRequest,
    ScanHostChangesRequest,
    UpdateFactRequest,
)
from backend.knowledge_factory import get_or_create_knowledge_base
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
        logger.warning(f"Failed to parse metadata for {fact_key}")
        return None


def _group_fact_by_category_title(fact_info: dict, fact_groups: dict) -> None:
    """Add fact to appropriate group by category:title (Issue #315: extracted)."""
    group_key = f"{fact_info['category']}:{fact_info['title']}"
    if group_key not in fact_groups:
        fact_groups[group_key] = []
    fact_groups[group_key].append(fact_info)


# ===== DEDUPLICATION ENDPOINTS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="deduplicate_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/deduplicate")
async def deduplicate_facts(req: Request, dry_run: bool = True):
    """
    Remove duplicate facts based on category + title.
    Keeps the oldest fact and removes newer duplicates.

    Args:
        dry_run: If True, only report duplicates without deleting (default: True)

    Returns:
        Report of duplicates found and removed
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    logger.info(f"Starting deduplication scan (dry_run={dry_run})...")

    # Use SCAN to iterate through all fact keys
    fact_groups = {}  # category:title -> list of (fact_id, created_at, fact_key)
    cursor = 0
    total_facts = 0

    while True:
        # Issue #361 - run Redis ops in thread pool to avoid blocking
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
            # Group facts by category+title (Issue #315: uses helper for reduced nesting)
            for i in range(0, len(results), 2):
                fact_info = _process_fact_metadata(
                    results[i], keys[i // 2], results[i + 1]
                )
                if fact_info:
                    _group_fact_by_category_title(fact_info, fact_groups)
                    total_facts += 1

        if cursor == 0:
            break

    logger.info(
        f"Scanned {total_facts} facts, found {len(fact_groups)} unique category+title combinations"
    )

    # Find duplicates
    duplicates_found = []
    facts_to_delete = []

    for group_key, facts in fact_groups.items():
        if len(facts) > 1:
            # Sort by created_at to keep the oldest
            facts.sort(key=lambda x: x["created_at"])

            # Keep first (oldest), mark rest for deletion
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

    # Delete duplicates if not dry run
    deleted_count = 0
    if not dry_run and facts_to_delete:
        logger.info(f"Deleting {len(facts_to_delete)} duplicate facts...")

        # Delete in batches (Issue #361 - avoid blocking)
        batch_size = 100
        for i in range(0, len(facts_to_delete), batch_size):
            batch = facts_to_delete[i : i + batch_size]
            await asyncio.to_thread(kb.redis_client.delete, *batch)
            deleted_count += len(batch)

        logger.info(f"Deleted {deleted_count} duplicate facts")

    return {
        "status": "success",
        "dry_run": dry_run,
        "total_facts_scanned": total_facts,
        "unique_combinations": len(fact_groups),
        "duplicate_groups_found": len(duplicates_found),
        "total_duplicates": len(facts_to_delete),
        "deleted_count": deleted_count,
        "duplicates": duplicates_found[:50],  # Return first 50 for preview
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_duplicates",
    error_code_prefix="KB",
)
@router.post("/deduplicate/advanced")
async def find_duplicates(request: DeduplicationRequest, req: Request):
    """
    Find duplicate or near-duplicate facts in the knowledge base.

    Issue #79: Bulk Operations - Deduplication

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
        f"dry_run={request.dry_run}, category={request.category}"
    )

    result = await kb.find_duplicates(
        similarity_threshold=request.similarity_threshold,
        category=request.category,
        max_comparisons=request.max_comparisons,
    )

    return result


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


async def _vectorize_single_document(
    kb, scanner, doc_change: dict, machine_id: str, results: dict
) -> None:
    """Vectorize a single document and update results (Issue #281: extracted)."""
    results["attempted"] += 1

    command = doc_change.get("command")
    file_path = doc_change.get("file_path")
    doc_id = doc_change.get("document_id")

    if not file_path or not command:
        results["skipped"] += 1
        results["details"].append({
            "doc_id": doc_id,
            "command": command,
            "status": "skipped",
            "reason": "Missing file_path or command",
        })
        return

    try:
        # Read man page content
        content = scanner.read_man_page_content(file_path, command)

        if not content or len(content.strip()) < 10:
            results["failed"] += 1
            results["details"].append({
                "doc_id": doc_id,
                "command": command,
                "status": "failed",
                "reason": "Empty or too short content",
            })
            return

        # Add to knowledge base with metadata
        metadata = {
            "category": "system/manpages",
            "title": f"man {command}",
            "command": command,
            "machine_id": machine_id,
            "file_path": file_path,
            "document_id": doc_id,
            "change_type": doc_change.get("change_type"),
            "content_size": len(content),
        }

        kb_result = await kb.add_document(
            content=content, metadata=metadata, doc_id=doc_id
        )

        if kb_result.get("status") == "success":
            results["successful"] += 1
            results["details"].append({
                "doc_id": doc_id,
                "command": command,
                "status": "success",
                "fact_id": kb_result.get("fact_id"),
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "doc_id": doc_id,
                "command": command,
                "status": "failed",
                "reason": kb_result.get("message", "Unknown error"),
            })

    except Exception as e:
        logger.error(f"Vectorization failed for {command}: {e}")
        results["failed"] += 1
        results["details"].append({
            "doc_id": doc_id,
            "command": command,
            "status": "error",
            "reason": str(e),
        })


async def _process_vectorization(
    kb, scanner, result: dict, machine_id: str
) -> dict:
    """Process vectorization for added/updated documents (Issue #281: extracted)."""
    vectorization_results = _create_vectorization_result()

    # Vectorize added and updated documents
    documents_to_vectorize = (
        result["changes"]["added"] + result["changes"]["updated"]
    )

    for doc_change in documents_to_vectorize:
        await _vectorize_single_document(
            kb, scanner, doc_change, machine_id, vectorization_results
        )

    logger.info(
        f"Vectorization completed: "
        f"{vectorization_results['successful']}/{vectorization_results['attempted']} successful"
    )

    return vectorization_results


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_host_changes",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/scan_host_changes")
async def scan_host_changes(req: Request, request_data: ScanHostChangesRequest):
    """
    ULTRA-FAST document change scanner using file metadata.
    Issue #281: Refactored from 162 lines to use extracted helper methods.

    Performance: ~0.5 seconds for 10,000 documents (100x faster than subprocess approach)

    Detects:
    - New documents (software installed)
    - Updated documents (man pages changed via mtime/size)
    - Removed documents (software uninstalled)

    Method:
    - Uses file metadata (mtime, size) instead of content reading
    - Direct filesystem access (no subprocess overhead)
    - Redis caching for incremental scans

    Args:
        request_data: Scan configuration with machine_id, force, and scan_type

    Returns:
        Dictionary with change detection results:
        - added: List of new documents
        - updated: List of changed documents (mtime/size changed)
        - removed: List of removed documents
        - unchanged: Count of unchanged documents
        - scan_duration_seconds: Actual scan time
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Extract parameters from request
    machine_id = request_data.machine_id
    force = request_data.force
    scan_type = request_data.scan_type
    auto_vectorize = request_data.auto_vectorize

    logger.info(
        f"Fast scan starting for {machine_id} (type={scan_type}, auto_vectorize={auto_vectorize})"
    )

    # Use ultra-fast metadata-based scanner
    from backend.services.fast_document_scanner import FastDocumentScanner

    scanner = FastDocumentScanner(kb.redis_client)

    # Perform fast scan (limit to 100 for reasonable response time)
    result = scanner.scan_for_changes(
        machine_id=machine_id,
        scan_type=scan_type,
        limit=100,  # Process first 100 documents
        force=force,
    )

    # Auto-vectorization (Issue #281: uses helper)
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
        logger.warning(f"Failed to parse metadata for {key}")
        return False, False, None

    file_path = metadata.get("file_path")
    if not file_path:
        return False, False, None

    # This is a file-based fact
    if PathLib(file_path).exists():
        return True, False, None

    # File doesn't exist - this is an orphan
    return True, True, {
        "fact_id": metadata.get("fact_id"),
        "fact_key": key,
        "title": metadata.get("title", "Unknown"),
        "category": metadata.get("category", "Unknown"),
        "file_path": file_path,
        "source": metadata.get("source", "Unknown"),
    }


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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/orphans")
async def find_orphaned_facts(req: Request):
    """
    Find facts whose source files no longer exist.
    Only checks facts with file_path metadata.

    Returns:
        List of orphaned facts
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    logger.info("Scanning for orphaned facts...")

    # Issue #361 - avoid blocking - run scan/pipeline in thread pool
    def _scan_for_orphans():
        orphaned_facts = []
        cursor = 0
        total_checked = 0

        while True:
            cursor, keys = kb.redis_client.scan(cursor, match="fact:*", count=100)

            if not keys:
                if cursor == 0:
                    break
                continue

            # Use pipeline for batch operations
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.hget(key, "metadata")
            results = pipe.execute()

            # Process batch (extracted helper reduces nesting)
            batch_checked, batch_orphans = _process_orphan_batch(keys, results)
            total_checked += batch_checked
            orphaned_facts.extend(batch_orphans)

            if cursor == 0:
                break

        return total_checked, orphaned_facts

    total_checked, orphaned_facts = await asyncio.to_thread(_scan_for_orphans)

    logger.info(
        f"Checked {total_checked} facts with file paths, found {len(orphaned_facts)} orphans"
    )

    return {
        "status": "success",
        "total_facts_checked": total_checked,
        "orphaned_count": len(orphaned_facts),
        "orphaned_facts": orphaned_facts,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/orphans")
async def cleanup_orphaned_facts(req: Request, dry_run: bool = True):
    """
    Remove facts whose source files no longer exist.

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
        logger.info(f"Deleting {len(orphaned_facts)} orphaned facts...")

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

        logger.info(f"Deleted {deleted_count} orphaned facts")

    return {
        "status": "success",
        "dry_run": dry_run,
        "orphaned_count": len(orphaned_facts),
        "deleted_count": deleted_count,
        "orphaned_facts": orphaned_facts[:20],  # Return first 20 for preview
    }


# ===== IMPORT/EXPORT OPERATIONS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_for_unimported_files",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/import/scan")
async def scan_for_unimported_files(req: Request, directory: str = "docs"):
    """Scan directory for files that need to be imported"""
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
async def export_knowledge(request: ExportRequest, req: Request):
    """
    Export knowledge base facts to JSON, CSV, or Markdown.

    Issue #79: Bulk Operations - Export functionality

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
        f"Export request: format={request.format.value}, include_metadata={request.include_metadata}")

    result = await kb.export_facts(
        format=request.format.value,
        categories=categories,
        tags=tags,
        fact_ids=fact_ids,
        date_from=date_from,
        date_to=date_to,
        include_metadata=request.include_metadata,
        include_tags=request.include_tags,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="import_knowledge",
    error_code_prefix="KB",
)
@router.post("/import")
async def import_knowledge(
    request: ImportRequest,
    req: Request,
    data: str = Query(..., description="Import data string"),
):
    """
    Import facts into the knowledge base from JSON or CSV.

    Issue #79: Bulk Operations - Import functionality

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_fact",
    error_code_prefix="KNOWLEDGE",
)
@router.put("/fact/{fact_id}")
async def update_fact(
    fact_id: str = Path(..., description="Fact ID to update"),
    request: UpdateFactRequest = ...,
    req: Request = None,
):
    """
    Update an existing knowledge base fact.

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
    # Validate fact_id format
    if not fact_id or not isinstance(fact_id, str):
        raise HTTPException(status_code=400, detail="Invalid fact_id format")

    # Validate at least one field is provided
    if request.content is None and request.metadata is None:
        raise HTTPException(
            status_code=400,
            detail="At least one field (content or metadata) must be provided",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    # Check if update_fact method exists (KnowledgeBaseV2)
    if not hasattr(kb, "update_fact"):
        raise HTTPException(
            status_code=501,
            detail="Update operation not supported by current knowledge base implementation",
        )

    content_status = 'provided' if request.content else 'unchanged'
    metadata_status = 'provided' if request.metadata else 'unchanged'
    logger.info(
        f"Updating fact {fact_id}: content={content_status}, metadata={metadata_status}"
    )

    # Call update_fact method
    result = await kb.update_fact(
        fact_id=fact_id, content=request.content, metadata=request.metadata
    )

    # Check if update was successful
    if result.get("success"):
        return {
            "status": "success",
            "fact_id": fact_id,
            "updated_fields": result.get("updated_fields", []),
            "vector_updated": result.get("vector_updated", False),
            "message": result.get("message", "Fact updated successfully"),
        }
    else:
        # Update failed - return error
        error_message = result.get("message", "Unknown error")
        if "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        else:
            raise HTTPException(status_code=500, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_fact",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/fact/{fact_id}")
async def delete_fact(
    fact_id: str = Path(..., description="Fact ID to delete"), req: Request = None
):
    """
    Delete a knowledge base fact and its vectorization.

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

    logger.info(f"Deleting fact {fact_id}")

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
async def bulk_delete_facts(request: BulkDeleteRequest, req: Request):
    """
    Delete multiple facts at once.

    Issue #79: Bulk Operations - Bulk delete

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

    logger.info(f"Bulk delete request: {len(request.fact_ids)} facts, confirm={request.confirm}")

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
async def bulk_update_category(request: BulkCategoryUpdateRequest, req: Request):
    """
    Update category for multiple facts at once.

    Issue #79: Bulk Operations - Bulk category update

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
async def cleanup_knowledge_base(request: CleanupRequest, req: Request):
    """
    Clean up the knowledge base.

    Issue #79: Bulk Operations - Cleanup

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
