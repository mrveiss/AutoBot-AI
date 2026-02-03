# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Memory API for AutoBot Phase 7
Provides endpoints for task execution tracking, markdown management, and memory analytics

Issue #357: Converted to use AsyncEnhancedMemoryManager to fix blocking I/O in async context.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.type_defs.common import Metadata
from src.enhanced_memory_manager_async import (
    AsyncEnhancedMemoryManager,
    TaskEntry,
    TaskPriority,
    TaskStatus,
    get_async_enhanced_memory_manager,
)
from src.markdown_reference_system import MarkdownReferenceSystem
from src.task_execution_tracker import task_tracker
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(tags=["enhanced_memory"])

# Thread-safe lock for lazy initialization of global state
_markdown_system_lock = asyncio.Lock()

# Performance optimization: O(1) lookup for terminal task statuses (Issue #326)
TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}

# Use the async memory manager singleton (Issue #357: non-blocking)
_markdown_system = None


async def _apply_task_status_update(
    memory_manager: AsyncEnhancedMemoryManager,
    task_id: str,
    status_enum: TaskStatus,
    outputs: dict | None,
    error_message: str | None,
) -> bool:
    """Apply task status update based on status type (Issue #315: extracted).

    Issue #357: Converted to async to fix blocking I/O.

    Returns:
        True if update succeeded, False otherwise

    Raises:
        HTTPException: If required fields are missing
    """
    metadata = {}
    if outputs:
        metadata["outputs"] = outputs
    if error_message:
        metadata["error_message"] = error_message

    return await memory_manager.update_task_status(task_id, status_enum, metadata)


async def get_memory_manager() -> (
    tuple[AsyncEnhancedMemoryManager, MarkdownReferenceSystem]
):
    """Lazy initialization of async memory manager to prevent startup blocking.

    Issue #357: Now uses AsyncEnhancedMemoryManager for non-blocking operations.
    Issue #395: Added asyncio.Lock for thread-safe lazy initialization.
    """
    global _markdown_system
    memory_manager = get_async_enhanced_memory_manager()
    if _markdown_system is None:
        async with _markdown_system_lock:
            # Double-check after acquiring lock to prevent race condition
            if _markdown_system is None:
                # Note: MarkdownReferenceSystem still uses sync manager internally
                # This is a compatibility bridge until it's also converted
                from src.enhanced_memory_manager import EnhancedMemoryManager

                _sync_memory_manager = EnhancedMemoryManager()
                _markdown_system = MarkdownReferenceSystem(_sync_memory_manager)
    return memory_manager, _markdown_system


class TaskCreateRequest(BaseModel):
    task_name: str
    description: str
    priority: str = "medium"  # low, medium, high, critical
    agent_type: Optional[str] = None
    inputs: Optional[Metadata] = None
    parent_task_id: Optional[str] = None
    metadata: Optional[Metadata] = None


class TaskUpdateRequest(BaseModel):
    status: Optional[str] = None  # pending, in_progress, completed, failed, cancelled
    outputs: Optional[Metadata] = None
    error_message: Optional[str] = None


class MarkdownReferenceRequest(BaseModel):
    task_id: str
    markdown_file_path: str
    reference_type: str = "documentation"


# Health check moved to consolidated health service
# See backend/services/consolidated_health_service.py
# Use /api/system/health?detailed=true for comprehensive status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_memory_statistics",
    error_code_prefix="MEMORY",
)
@router.get("/statistics")
async def get_memory_statistics(days_back: int = Query(30, ge=1, le=365)):
    """Get comprehensive memory and task execution statistics.

    Issue #357: Now uses async memory manager for non-blocking database operations.
    """
    try:
        memory_manager, markdown_system = await get_memory_manager()

        # Issue #379: Run all statistics collection in parallel
        task_stats, markdown_stats, active_tasks, insights = await asyncio.gather(
            memory_manager.get_task_statistics(),
            asyncio.to_thread(markdown_system.get_markdown_statistics),
            asyncio.to_thread(task_tracker.get_active_tasks),
            task_tracker.analyze_task_patterns(days_back),
        )

        return {
            "period_days": days_back,
            "timestamp": datetime.now().isoformat(),
            "task_execution": task_stats,
            "markdown_system": markdown_stats,
            "active_tasks": {"count": len(active_tasks), "details": active_tasks},
            "performance_insights": insights,
        }
    except Exception as e:
        logger.error("Error getting memory statistics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_task_history",
    error_code_prefix="MEMORY",
)
@router.get("/tasks/history")
async def get_task_history(
    agent_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    days_back: int = Query(30, ge=1, le=365),
):
    """Get task execution history with filtering options"""
    try:
        # Convert string status to enum if provided
        status_enum = None
        if status:
            try:
                status_enum = TaskStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        history = task_tracker.get_task_history(
            agent_type=agent_type, status=status_enum, limit=limit, days_back=days_back
        )

        # Issue #372: Use model method to reduce feature envy
        history_data = [task.to_response_dict() for task in history]

        return {
            "total_records": len(history_data),
            "filter_criteria": {
                "agent_type": agent_type,
                "status": status,
                "days_back": days_back,
            },
            "tasks": history_data,
        }

    except Exception as e:
        logger.error("Error getting task history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_task",
    error_code_prefix="MEMORY",
)
@router.post("/tasks")
async def create_task(request: TaskCreateRequest):
    """Create a new task record.

    Issue #357: Now uses async memory manager for non-blocking database operations.
    """
    try:
        memory_manager, _ = await get_memory_manager()

        # Convert priority string to enum
        # Map string priority to numeric Priority enum
        priority_map = {
            "low": TaskPriority.LOW,
            "medium": TaskPriority.MEDIUM,
            "high": TaskPriority.HIGH,
            "critical": TaskPriority.CRITICAL,
        }
        priority_enum = priority_map.get(request.priority.lower())
        if priority_enum is None:
            raise HTTPException(
                status_code=400, detail=f"Invalid priority: {request.priority}"
            )

        # Create TaskEntry for async manager
        task_entry = TaskEntry(
            task_id="",  # Will be generated
            description=f"{request.task_name}: {request.description}",
            status=TaskStatus.PENDING,
            priority=priority_enum,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            assigned_agent=request.agent_type,
            parent_task_id=request.parent_task_id,
            metadata=request.metadata or {},
        )

        task_id = await memory_manager.create_task(task_entry)

        return {
            "task_id": task_id,
            "status": "created",
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating task: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_task",
    error_code_prefix="MEMORY",
)
@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: TaskUpdateRequest):
    """Update task status and information.

    Issue #315: Refactored to use helper function for reduced nesting depth.
    Issue #357: Now uses async memory manager for non-blocking database operations.
    """
    try:
        memory_manager, _ = await get_memory_manager()
        success = False

        if request.status:
            try:
                status_enum = TaskStatus(request.status)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid status: {request.status}"
                )

            # Use helper for status-specific logic (Issue #315, #357)
            success = await _apply_task_status_update(
                memory_manager,
                task_id,
                status_enum,
                request.outputs,
                request.error_message,
            )

        if not success:
            raise HTTPException(
                status_code=404, detail="Task not found or update failed"
            )

        return {
            "task_id": task_id,
            "status": "updated",
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating task %s: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_markdown_reference",
    error_code_prefix="MEMORY",
)
@router.post("/tasks/{task_id}/markdown-reference")
async def add_markdown_reference(task_id: str, request: MarkdownReferenceRequest):
    """Add markdown file reference to a task.

    Issue #357: Wrapped sync operation in asyncio.to_thread for non-blocking.
    """
    try:
        _, _ = await get_memory_manager()  # Issue #382: markdown_system unused here

        # Wrap sync operation in thread (MarkdownReferenceSystem uses sync memory manager)
        from src.enhanced_memory_manager import EnhancedMemoryManager

        sync_manager = EnhancedMemoryManager()

        success = await asyncio.to_thread(
            sync_manager.add_markdown_reference,
            request.task_id,
            request.markdown_file_path,
            request.reference_type,
        )

        if not success:
            raise HTTPException(
                status_code=400, detail="Failed to add markdown reference"
            )

        return {
            "task_id": task_id,
            "markdown_file": request.markdown_file_path,
            "reference_type": request.reference_type,
            "status": "added",
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error adding markdown reference: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_markdown_system",
    error_code_prefix="MEMORY",
)
@router.get("/markdown/scan")
async def scan_markdown_system():
    """Initialize and scan markdown reference system.

    Issue #357: Wrapped sync operation in asyncio.to_thread for non-blocking.
    """
    try:
        _, markdown_system = await get_memory_manager()
        result = await asyncio.to_thread(markdown_system.initialize_system_scan)
        return {
            "status": "completed",
            "scan_results": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error scanning markdown system: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_markdown",
    error_code_prefix="MEMORY",
)
@router.get("/markdown/search")
async def search_markdown(
    query: str = Query(..., min_length=2),
    document_type: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Search markdown content and sections.

    Issue #357: Wrapped sync operation in asyncio.to_thread for non-blocking.
    """
    try:
        _, markdown_system = await get_memory_manager()
        results = await asyncio.to_thread(
            markdown_system.search_markdown_content, query, document_type, tags, limit
        )

        return {
            "query": query,
            "filters": {"document_type": document_type, "tags": tags},
            "total_results": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error("Error searching markdown: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_document_references",
    error_code_prefix="MEMORY",
)
@router.get("/markdown/{file_path:path}/references")
async def get_document_references(file_path: str):
    """Get all references for a specific markdown document.

    Issue #357: Wrapped sync operation in asyncio.to_thread for non-blocking.
    """
    try:
        _, markdown_system = await get_memory_manager()
        references = await asyncio.to_thread(
            markdown_system.get_document_references, file_path
        )

        return {
            "file_path": file_path,
            "timestamp": datetime.now().isoformat(),
            "references": references,
        }

    except Exception as e:
        logger.error("Error getting document references: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_embedding_cache_stats",
    error_code_prefix="MEMORY",
)
@router.get("/embeddings/cache-stats")
async def get_embedding_cache_stats():
    """Get embedding cache statistics.

    Issue #357: Wrapped sync operation in asyncio.to_thread for non-blocking.
    """
    try:
        # Use sync memory manager for embedding cache (async manager doesn't have this)
        from src.enhanced_memory_manager import EnhancedMemoryManager

        sync_manager = EnhancedMemoryManager()
        cache_size = await asyncio.to_thread(sync_manager._get_embedding_cache_size)

        return {
            "cache_size": cache_size,
            "timestamp": datetime.now().isoformat(),
            "status": "operational",
        }

    except Exception as e:
        logger.error("Error getting embedding cache stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_old_data",
    error_code_prefix="MEMORY",
)
@router.delete("/cleanup")
async def cleanup_old_data(days_to_keep: int = Query(90, ge=30, le=365)):
    """Clean up old task records and cached data.

    Issue #357: Now uses async memory manager for non-blocking database operations.
    """
    try:
        memory_manager, _ = await get_memory_manager()
        await memory_manager.cleanup_old_data(days_to_keep)

        return {
            "status": "completed",
            "cleanup_results": {"retention_days": days_to_keep},
            "days_kept": days_to_keep,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Error cleaning up old data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_tasks",
    error_code_prefix="MEMORY",
)
@router.get("/active-tasks")
async def get_active_tasks():
    """Get currently active tasks"""
    try:
        active_tasks = task_tracker.get_active_tasks()

        return {
            "count": len(active_tasks),
            "active_tasks": active_tasks,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Error getting active tasks: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
