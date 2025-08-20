"""
Enhanced Memory API for AutoBot Phase 7
Provides endpoints for task execution tracking, markdown management, and memory analytics
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.enhanced_memory_manager_async import (
    get_async_enhanced_memory_manager,
    TaskPriority,
    TaskStatus,
)
from src.markdown_reference_system import MarkdownReferenceSystem

logger = logging.getLogger(__name__)

router = APIRouter(tags=["enhanced_memory"])

# URGENT FIX: Use lazy initialization to prevent blocking during module import
memory_manager = None
markdown_system = None

def get_memory_manager():
    """Lazy initialization of memory manager to prevent startup blocking"""
    global memory_manager, markdown_system
    if memory_manager is None:
        memory_manager = EnhancedMemoryManager()
        markdown_system = MarkdownReferenceSystem(memory_manager)
    return memory_manager, markdown_system


class TaskCreateRequest(BaseModel):
    task_name: str
    description: str
    priority: str = "medium"  # low, medium, high, critical
    agent_type: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    parent_task_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskUpdateRequest(BaseModel):
    status: Optional[str] = None  # pending, in_progress, completed, failed, cancelled
    outputs: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class MarkdownReferenceRequest(BaseModel):
    task_id: str
    markdown_file_path: str
    reference_type: str = "documentation"


@router.get("/health")
async def health_check():
    """Health check for enhanced memory system"""
    try:
        memory_mgr, markdown_sys = get_memory_manager()
        stats = memory_mgr.get_task_statistics(days_back=1)
        return {
            "status": "healthy",
            "memory_manager": "operational",
            "markdown_system": "operational",
            "recent_tasks": stats.get("total_tasks", 0),
        }
    except Exception as e:
        logger.error(f"Enhanced memory health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@router.get("/statistics")
async def get_memory_statistics(days_back: int = Query(30, ge=1, le=365)):
    """Get comprehensive memory and task execution statistics"""
    try:
        # Task execution statistics
        task_stats = memory_manager.get_task_statistics(days_back)

        # Markdown system statistics
        markdown_stats = markdown_system.get_markdown_statistics()

        # Active task information
        active_tasks = task_tracker.get_active_tasks()

        # Performance insights
        insights = await task_tracker.analyze_task_patterns(days_back)

        return {
            "period_days": days_back,
            "timestamp": datetime.now().isoformat(),
            "task_execution": task_stats,
            "markdown_system": markdown_stats,
            "active_tasks": {"count": len(active_tasks), "details": active_tasks},
            "performance_insights": insights,
        }
    except Exception as e:
        logger.error(f"Error getting memory statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        # Convert to JSON-serializable format
        history_data = []
        for task in history:
            task_dict = {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "description": task.description,
                "status": task.status.value,
                "priority": task.priority.value,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": (
                    task.completed_at.isoformat() if task.completed_at else None
                ),
                "duration_seconds": task.duration_seconds,
                "agent_type": task.agent_type,
                "inputs": task.inputs,
                "outputs": task.outputs,
                "error_message": task.error_message,
                "retry_count": task.retry_count,
                "parent_task_id": task.parent_task_id,
                "subtask_ids": task.subtask_ids,
                "markdown_references": task.markdown_references,
                "metadata": task.metadata,
            }
            history_data.append(task_dict)

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
        logger.error(f"Error getting task history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks")
async def create_task(request: TaskCreateRequest):
    """Create a new task record"""
    try:
        # Convert priority string to enum
        try:
            priority_enum = TaskPriority(request.priority)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid priority: {request.priority}"
            )

        task_id = memory_manager.create_task_record(
            task_name=request.task_name,
            description=request.description,
            priority=priority_enum,
            agent_type=request.agent_type,
            inputs=request.inputs,
            parent_task_id=request.parent_task_id,
            metadata=request.metadata,
        )

        return {
            "task_id": task_id,
            "status": "created",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: TaskUpdateRequest):
    """Update task status and information"""
    try:
        success = False

        if request.status:
            try:
                status_enum = TaskStatus(request.status)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid status: {request.status}"
                )

            if status_enum == TaskStatus.IN_PROGRESS:
                success = memory_manager.start_task(task_id)
            elif status_enum in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
                success = memory_manager.complete_task(
                    task_id, request.outputs, status_enum
                )
            elif status_enum == TaskStatus.FAILED:
                if not request.error_message:
                    raise HTTPException(
                        status_code=400,
                        detail="error_message required for failed status",
                    )
                success = memory_manager.fail_task(task_id, request.error_message)

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
        logger.error(f"Error updating task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/markdown-reference")
async def add_markdown_reference(task_id: str, request: MarkdownReferenceRequest):
    """Add markdown file reference to a task"""
    try:
        success = memory_manager.add_markdown_reference(
            task_id=request.task_id,
            markdown_file_path=request.markdown_file_path,
            reference_type=request.reference_type,
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
        logger.error(f"Error adding markdown reference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markdown/scan")
async def scan_markdown_system():
    """Initialize and scan markdown reference system"""
    try:
        result = markdown_system.initialize_system_scan()
        return {
            "status": "completed",
            "scan_results": result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error scanning markdown system: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markdown/search")
async def search_markdown(
    query: str = Query(..., min_length=2),
    document_type: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Search markdown content and sections"""
    try:
        results = markdown_system.search_markdown_content(
            query=query, document_type=document_type, tags=tags, limit=limit
        )

        return {
            "query": query,
            "filters": {"document_type": document_type, "tags": tags},
            "total_results": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error searching markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markdown/{file_path:path}/references")
async def get_document_references(file_path: str):
    """Get all references for a specific markdown document"""
    try:
        references = markdown_system.get_document_references(file_path)

        return {
            "file_path": file_path,
            "timestamp": datetime.now().isoformat(),
            "references": references,
        }

    except Exception as e:
        logger.error(f"Error getting document references: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embeddings/cache-stats")
async def get_embedding_cache_stats():
    """Get embedding cache statistics"""
    try:
        # This would integrate with the embedding cache in the memory manager
        cache_size = memory_manager._get_embedding_cache_size()

        return {
            "cache_size": cache_size,
            "timestamp": datetime.now().isoformat(),
            "status": "operational",
        }

    except Exception as e:
        logger.error(f"Error getting embedding cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cleanup")
async def cleanup_old_data(days_to_keep: int = Query(90, ge=30, le=365)):
    """Clean up old task records and cached data"""
    try:
        cleanup_result = memory_manager.cleanup_old_data(days_to_keep)

        return {
            "status": "completed",
            "cleanup_results": cleanup_result,
            "days_kept": days_to_keep,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error cleaning up old data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Error getting active tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
