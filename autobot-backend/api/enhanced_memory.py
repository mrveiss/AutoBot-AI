# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Enhanced Memory API for AutoBot Phase 7
Provides endpoints for task execution tracking, markdown management, and memory analytics

Migrated (#10572): uses MemoryManager (memory/manager.py) exclusively.
AsyncEnhancedMemoryManager and the standalone enhanced_memory_manager module
are no longer referenced here.
"""

import asyncio
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, Query

from api.schemas_agent import (
    MemoryActiveTasksResponse,
    MemoryCleanupResponse,
    MemoryDocumentReferencesResponse,
    MemoryEmbeddingCacheStatsResponse,
    MemoryMarkdownReferenceResponse,
    MemoryMarkdownScanResponse,
    MemoryMarkdownSearchResponse,
    MemoryStatisticsResponse,
    MemoryTaskCreateResponse,
    MemoryTaskHistoryResponse,
    MemoryTaskUpdateResponse,
)
from api.schemas_knowledge import (
    MarkdownReferenceRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from markdown_reference_system import MarkdownReferenceSystem
from memory import TaskPriority, TaskStatus, MemoryManager
from task_execution_tracker import get_task_tracker

logger = get_logger(__name__)

router = APIRouter(tags=["enhanced_memory"])

# Thread-safe lock for lazy initialisation of the markdown subsystem singleton
_markdown_system_lock = asyncio.Lock()
_markdown_system: MarkdownReferenceSystem | None = None

# Performance optimisation: O(1) lookup for terminal task statuses
TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}

# Singleton memory manager (instantiated once per process)
get_memory_manager_singleton = lazy_singleton(MemoryManager)


async def _get_managers() -> tuple[MemoryManager, MarkdownReferenceSystem]:
    """Return the singleton MemoryManager and lazily-initialised MarkdownReferenceSystem."""
    global _markdown_system
    memory_manager: MemoryManager = get_memory_manager_singleton()
    if _markdown_system is None:
        async with _markdown_system_lock:
            if _markdown_system is None:
                _markdown_system = MarkdownReferenceSystem(memory_manager)
    return memory_manager, _markdown_system


@router.get("/statistics", response_model=MemoryStatisticsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_memory_statistics",
    error_code_prefix="MEMORY",
)
async def get_memory_statistics(days_back: int = Query(30, ge=1, le=365)):
    """Get comprehensive memory and task execution statistics."""
    try:
        memory_manager, markdown_system = await _get_managers()
        task_tracker = get_task_tracker()

        task_stats, markdown_stats, active_tasks, insights = await asyncio.gather(
            memory_manager.get_task_statistics(days_back),
            asyncio.to_thread(lambda: markdown_system.get_markdown_statistics()),
            asyncio.to_thread(lambda: task_tracker.get_active_tasks()),
            task_tracker.analyze_task_patterns(days_back),
        )

        return {
            "period_days": days_back,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "task_execution": task_stats,
            "markdown_system": markdown_stats,
            "active_tasks": {"count": len(active_tasks), "details": active_tasks},
            "performance_insights": insights,
        }
    except Exception as e:
        logger.error("Error getting memory statistics: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks/history", response_model=MemoryTaskHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_task_history",
    error_code_prefix="MEMORY",
)
async def get_task_history(
    agent_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    days_back: int = Query(30, ge=1, le=365),
):
    """Get task execution history with filtering options."""
    try:
        status_enum = None
        if status:
            try:
                status_enum = TaskStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        history = get_task_tracker().get_task_history(
            agent_type=agent_type, status=status_enum, limit=limit, days_back=days_back
        )

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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tasks", response_model=MemoryTaskCreateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_task",
    error_code_prefix="MEMORY",
)
async def create_task(request: TaskCreateRequest):
    """Create a new task record."""
    try:
        memory_manager, _ = await _get_managers()

        try:
            priority_enum = TaskPriority(request.priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}")

        task_id = await asyncio.to_thread(
            memory_manager.create_task_record,
            request.task_name,
            request.description,
            priority=priority_enum,
            agent_type=request.agent_type,
            inputs=None,
            parent_task_id=request.parent_task_id,
            metadata=request.metadata or {},
        )

        return {
            "task_id": task_id,
            "status": "created",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating task: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/tasks/{task_id}", response_model=MemoryTaskUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_task",
    error_code_prefix="MEMORY",
)
async def update_task(task_id: str, request: TaskUpdateRequest):
    """Update task status and information."""
    try:
        memory_manager, _ = await _get_managers()
        success = False

        if request.status:
            try:
                status_enum = TaskStatus(request.status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")

            if status_enum == TaskStatus.IN_PROGRESS:
                success = await asyncio.to_thread(memory_manager.start_task, task_id)
            elif status_enum == TaskStatus.COMPLETED:
                success = await asyncio.to_thread(memory_manager.complete_task, task_id, request.outputs)
            elif status_enum == TaskStatus.FAILED:
                success = await asyncio.to_thread(
                    memory_manager.fail_task,
                    task_id,
                    request.error_message or "Unknown error",
                )
            else:
                success = await memory_manager.update_task_status(task_id, status_enum)

        if not success:
            raise HTTPException(status_code=404, detail="Task not found or update failed")

        return {
            "task_id": task_id,
            "status": "updated",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating task %s: %s", task_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tasks/{task_id}/markdown-reference", response_model=MemoryMarkdownReferenceResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_markdown_reference",
    error_code_prefix="MEMORY",
)
async def add_markdown_reference(task_id: str, request: MarkdownReferenceRequest):
    """Add markdown file reference to a task."""
    try:
        memory_manager, _ = await _get_managers()

        success = await asyncio.to_thread(
            memory_manager.add_markdown_reference,
            task_id=request.task_id,
            markdown_file_path=request.markdown_file_path,
            reference_type=request.reference_type,
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to add markdown reference")

        return {
            "task_id": task_id,
            "markdown_file": request.markdown_file_path,
            "reference_type": request.reference_type,
            "status": "added",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error adding markdown reference: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/markdown/scan", response_model=MemoryMarkdownScanResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_markdown_system",
    error_code_prefix="MEMORY",
)
async def scan_markdown_system():
    """Initialise and scan markdown reference system."""
    try:
        _, markdown_system = await _get_managers()
        result = await asyncio.to_thread(lambda: markdown_system.initialize_system_scan())
        return {
            "status": "completed",
            "scan_results": result,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error scanning markdown system: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/markdown/search", response_model=MemoryMarkdownSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_markdown",
    error_code_prefix="MEMORY",
)
async def search_markdown(
    query: str = Query(..., min_length=2),
    document_type: str | None = Query(None),
    tags: List[str] | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Search markdown content and sections."""
    try:
        _, markdown_system = await _get_managers()
        results = await asyncio.to_thread(
            markdown_system.search_markdown_content,
            query=query,
            document_type=document_type,
            tags=tags,
            limit=limit,
        )

        return {
            "query": query,
            "filters": {"document_type": document_type, "tags": tags},
            "total_results": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error("Error searching markdown: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/markdown/{file_path:path}/references", response_model=MemoryDocumentReferencesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_document_references",
    error_code_prefix="MEMORY",
)
async def get_document_references(file_path: str):
    """Get all references for a specific markdown document."""
    try:
        _, markdown_system = await _get_managers()
        references = await asyncio.to_thread(lambda: markdown_system.get_document_references(file_path))

        return {
            "file_path": file_path,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "references": references,
        }

    except Exception as e:
        logger.error("Error getting document references: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/embeddings/cache-stats", response_model=MemoryEmbeddingCacheStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_embedding_cache_stats",
    error_code_prefix="MEMORY",
)
async def get_embedding_cache_stats():
    """Get embedding cache statistics."""
    try:
        memory_manager, _ = await _get_managers()
        cache_size = await asyncio.to_thread(lambda: memory_manager._get_embedding_cache_size())

        return {
            "cache_size": cache_size,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "status": "operational",
        }

    except Exception as e:
        logger.error("Error getting embedding cache stats: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/cleanup", response_model=MemoryCleanupResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_old_data",
    error_code_prefix="MEMORY",
)
async def cleanup_old_data(days_to_keep: int = Query(90, ge=30, le=365)):
    """Clean up old task records and cached data."""
    try:
        memory_manager, _ = await _get_managers()
        cleanup_result = await asyncio.to_thread(lambda: memory_manager.cleanup_old_data(days_to_keep))

        return {
            "status": "completed",
            "cleanup_results": cleanup_result,
            "days_kept": days_to_keep,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error("Error cleaning up old data: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/active-tasks", response_model=MemoryActiveTasksResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_tasks",
    error_code_prefix="MEMORY",
)
async def get_active_tasks():
    """Get currently active tasks."""
    try:
        task_tracker = get_task_tracker()
        active_tasks = task_tracker.get_active_tasks()

        return {
            "count": len(active_tasks),
            "active_tasks": active_tasks,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error("Error getting active tasks: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
