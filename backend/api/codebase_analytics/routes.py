# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI router endpoints for codebase analytics API
"""

import ast
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from .models import CodebaseStats, ProblemItem, HardcodeItem, DeclarationItem
from .storage import get_redis_connection, get_code_collection, InMemoryStorage
from .scanner import (
    scan_codebase,
    do_indexing_with_progress,
    indexing_tasks,
    _active_tasks,
    _indexing_lock,
    _tasks_lock,
    _tasks_sync_lock,
    _current_indexing_task_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/codebase", tags=["codebase-analytics"])

# Performance optimization: O(1) lookup for internal modules (Issue #326)
INTERNAL_MODULE_PREFIXES = {"src", "backend", "autobot"}

# In-memory storage fallback
_in_memory_storage = {}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="index_codebase",
    error_code_prefix="CODEBASE",
)
@router.post("/index")
async def index_codebase():
    """
    Start background indexing of the AutoBot codebase

    Returns immediately with a task_id that can be used to poll progress
    via GET /api/analytics/codebase/index/status/{task_id}

    Only one indexing task can run at a time - subsequent requests will
    return the existing task's ID if one is already running.
    """
    global _current_indexing_task_id

    logger.info("✅ ENTRY: index_codebase endpoint called!")

    # Check if there's already an indexing task running (under lock)
    async with _tasks_lock:
        if _current_indexing_task_id is not None:
            existing_task = _active_tasks.get(_current_indexing_task_id)
            if existing_task and not existing_task.done():
                current_task_id = _current_indexing_task_id
                logger.info(
                    f"🔒 Indexing already in progress: {current_task_id}"
                )
                return JSONResponse(
                    {
                        "task_id": current_task_id,
                        "status": "already_running",
                        "message": (
                            "Indexing is already in progress. Poll "
                            f"/api/analytics/codebase/index/status/{current_task_id} "
                            "for progress."
                        ),
                    }
                )

        # Always use project root (4 levels up from backend/api/codebase_analytics/routes.py)
        project_root = Path(__file__).parent.parent.parent.parent
        root_path = str(project_root)
        logger.info(f"📁 project_root = {root_path}")

        # Generate unique task ID
        task_id = str(uuid.uuid4())
        logger.info(f"🆔 Generated task_id = {task_id}")

        # Set the current indexing task
        _current_indexing_task_id = task_id

        # Add async background task using asyncio and store reference
        logger.info("🔄 About to create_task")
        task = asyncio.create_task(do_indexing_with_progress(task_id, root_path))
        logger.info(f"✅ Task created: {task}")
        _active_tasks[task_id] = task
        logger.info("💾 Task stored in _active_tasks")

    # Clean up task reference when done
    def cleanup_task(t):
        global _current_indexing_task_id
        with _tasks_sync_lock:
            _active_tasks.pop(task_id, None)
            if _current_indexing_task_id == task_id:
                _current_indexing_task_id = None
        logger.info(f"🧹 Task {task_id} cleaned up")

    task.add_done_callback(cleanup_task)
    logger.info("🧹 Cleanup callback added")

    logger.info("📤 About to return JSONResponse")
    return JSONResponse(
        {
            "task_id": task_id,
            "status": "started",
            "message": (
                "Indexing started in background. Poll "
                "/api/analytics/codebase/index/status/{task_id} for progress."
            ),
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_indexing_status",
    error_code_prefix="CODEBASE",
)
@router.get("/index/status/{task_id}")
async def get_indexing_status(task_id: str):
    """
    Get the status of a background indexing task

    Returns:
    - task_id: The unique task identifier
    - status: "running" | "completed" | "failed" | "not_found"
    - progress: {current, total, percent, current_file, operation} (if running)
    - result: Final indexing results (if completed)
    - error: Error message (if failed)
    """
    if task_id not in indexing_tasks:
        return JSONResponse(
            status_code=404,
            content={
                "task_id": task_id,
                "status": "not_found",
                "error": "Task not found. It may have expired or never existed.",
            },
        )

    task_data = indexing_tasks[task_id]

    response = {
        "task_id": task_id,
        "status": task_data["status"],
        "progress": task_data.get("progress"),
        "result": task_data.get("result"),
        "error": task_data.get("error"),
        "started_at": task_data.get("started_at"),
        "completed_at": task_data.get("completed_at"),
        "failed_at": task_data.get("failed_at"),
    }

    return JSONResponse(response)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_indexing_job",
    error_code_prefix="CODEBASE",
)
@router.get("/index/current")
async def get_current_indexing_job():
    """
    Get the status of the currently running indexing job (if any)

    Returns:
    - has_active_job: Whether an indexing job is currently running
    - task_id: The current job's task ID (if running)
    - status: Current job status
    - progress: Current progress details
    """
    # All accesses to shared state under lock
    async with _tasks_lock:
        if _current_indexing_task_id is None:
            return JSONResponse({
                "has_active_job": False,
                "task_id": None,
                "status": "idle",
                "message": "No indexing job is currently running",
            })

        current_task_id = _current_indexing_task_id

        # Check if task is still running
        existing_task = _active_tasks.get(current_task_id)
        if existing_task is None or existing_task.done():
            # Task finished or was cleaned up
            task_data = dict(indexing_tasks.get(current_task_id, {}))
            return JSONResponse({
                "has_active_job": False,
                "task_id": current_task_id,
                "status": task_data.get("status", "unknown"),
                "result": task_data.get("result"),
                "error": task_data.get("error"),
                "message": "Last indexing job has completed",
            })

        # Task is still running - get a copy of task data
        task_data = dict(indexing_tasks.get(current_task_id, {}))

    return JSONResponse({
        "has_active_job": True,
        "task_id": current_task_id,
        "status": task_data.get("status", "running"),
        "progress": task_data.get("progress"),
        "phases": task_data.get("phases"),
        "batches": task_data.get("batches"),
        "stats": task_data.get("stats"),
        "started_at": task_data.get("started_at"),
        "message": "Indexing job is in progress",
    })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_indexing_job",
    error_code_prefix="CODEBASE",
)
@router.post("/index/cancel")
async def cancel_indexing_job():
    """
    Cancel the currently running indexing job

    Returns:
    - success: Whether the cancellation was successful
    - task_id: The cancelled job's task ID
    - message: Status message
    """
    global _current_indexing_task_id

    # All accesses to shared state under lock
    async with _tasks_lock:
        if _current_indexing_task_id is None:
            return JSONResponse({
                "success": False,
                "task_id": None,
                "message": "No indexing job is currently running",
            })

        task_id = _current_indexing_task_id
        existing_task = _active_tasks.get(task_id)

        if existing_task is None or existing_task.done():
            return JSONResponse({
                "success": False,
                "task_id": task_id,
                "message": "Indexing job has already completed or was not found",
            })

        # Cancel the task
        try:
            existing_task.cancel()
            logger.info(f"🛑 Cancelled indexing task: {task_id}")

            # Update task status
            if task_id in indexing_tasks:
                indexing_tasks[task_id]["status"] = "cancelled"
                indexing_tasks[task_id]["error"] = "Cancelled by user"
                indexing_tasks[task_id]["failed_at"] = datetime.now().isoformat()

            # Clear current task
            _current_indexing_task_id = None
            _active_tasks.pop(task_id, None)

            return JSONResponse({
                "success": True,
                "task_id": task_id,
                "message": "Indexing job cancelled successfully",
            })

        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return JSONResponse({
                "success": False,
                "task_id": task_id,
                "message": f"Failed to cancel job: {str(e)}",
            })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_stats",
    error_code_prefix="CODEBASE",
)
@router.get("/stats")
async def get_codebase_stats():
    """Get real codebase statistics from storage"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    if code_collection:
        try:
            # Query ChromaDB for stats
            results = code_collection.get(ids=["codebase_stats"], include=["metadatas"])

            if results.get("metadatas") and len(results["metadatas"]) > 0:
                stats_metadata = results["metadatas"][0]

                # Extract stats from metadata
                stats = {}
                numeric_fields = [
                    "total_files",
                    "python_files",
                    "javascript_files",
                    "vue_files",
                    "config_files",
                    "other_files",
                    "total_lines",
                    "total_functions",
                    "total_classes",
                ]

                for field in numeric_fields:
                    if field in stats_metadata:
                        stats[field] = int(stats_metadata[field])

                if "average_file_size" in stats_metadata:
                    stats["average_file_size"] = float(
                        stats_metadata["average_file_size"]
                    )

                timestamp = stats_metadata.get("last_indexed", "Never")
                storage_type = "chromadb"

                return JSONResponse(
                    {
                        "status": "success",
                        "stats": stats,
                        "last_indexed": timestamp,
                        "storage_type": storage_type,
                    }
                )
            else:
                return JSONResponse(
                    {
                        "status": "no_data",
                        "message": "No codebase data found. Run indexing first.",
                        "stats": None,
                    }
                )

        except Exception as chroma_error:
            logger.warning(f"ChromaDB stats query failed: {chroma_error}")
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "stats": None,
                }
            )
    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "ChromaDB connection failed.",
                "stats": None,
            }
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardcoded_values",
    error_code_prefix="CODEBASE",
)
@router.get("/hardcodes")
async def get_hardcoded_values(hardcode_type: Optional[str] = None):
    """Get real hardcoded values found in the codebase"""
    redis_client = await get_redis_connection()

    all_hardcodes = []

    if redis_client:
        if hardcode_type:
            hardcodes_data = redis_client.get(f"codebase:hardcodes:{hardcode_type}")
            if hardcodes_data:
                all_hardcodes = json.loads(hardcodes_data)
        else:
            for key in redis_client.scan_iter(match="codebase:hardcodes:*"):
                hardcodes_data = redis_client.get(key)
                if hardcodes_data:
                    all_hardcodes.extend(json.loads(hardcodes_data))
        storage_type = "redis"
    else:
        if not _in_memory_storage:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "hardcodes": [],
                }
            )

        storage = _in_memory_storage
        if hardcode_type:
            hardcodes_data = storage.get(f"codebase:hardcodes:{hardcode_type}")
            if hardcodes_data:
                all_hardcodes = json.loads(hardcodes_data)
        else:
            for key in storage.scan_iter("codebase:hardcodes:*"):
                hardcodes_data = storage.get(key)
                if hardcodes_data:
                    all_hardcodes.extend(json.loads(hardcodes_data))
        storage_type = "memory"

    # Sort by file and line number
    all_hardcodes.sort(key=lambda x: (x.get("file_path", ""), x.get("line", 0)))

    return JSONResponse(
        {
            "status": "success",
            "hardcodes": all_hardcodes,
            "total_count": len(all_hardcodes),
            "hardcode_types": list(
                set(h.get("type", "unknown") for h in all_hardcodes)
            ),
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_problems",
    error_code_prefix="CODEBASE",
)
@router.get("/problems")
async def get_codebase_problems(problem_type: Optional[str] = None):
    """Get real code problems detected during analysis"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_problems = []

    if code_collection:
        try:
            # Query ChromaDB for problems
            where_filter = {"type": "problem"}
            if problem_type:
                where_filter["problem_type"] = problem_type

            results = code_collection.get(where=where_filter, include=["metadatas"])

            # Extract problems from metadata
            for metadata in results.get("metadatas", []):
                all_problems.append(
                    {
                        "type": metadata.get("problem_type", ""),
                        "severity": metadata.get("severity", ""),
                        "file_path": metadata.get("file_path", ""),
                        "line_number": (
                            int(metadata.get("line_number", 0))
                            if metadata.get("line_number")
                            else None
                        ),
                        "description": metadata.get("description", ""),
                        "suggestion": metadata.get("suggestion", ""),
                    }
                )

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_problems)} problems from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, falling back to Redis"
            ),
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        redis_client = await get_redis_connection()

        if redis_client:
            if problem_type:
                problems_data = redis_client.get(f"codebase:problems:{problem_type}")
                if problems_data:
                    all_problems = json.loads(problems_data)
            else:
                for key in redis_client.scan_iter(match="codebase:problems:*"):
                    problems_data = redis_client.get(key)
                    if problems_data:
                        all_problems.extend(json.loads(problems_data))
            storage_type = "redis"
        else:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "problems": [],
                }
            )

    # Sort by severity (high, medium, low)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    all_problems.sort(
        key=lambda x: (
            severity_order.get(x.get("severity", "low"), 3),
            x.get("file_path", ""),
        )
    )

    return JSONResponse(
        {
            "status": "success",
            "problems": all_problems,
            "total_count": len(all_problems),
            "problem_types": list(set(p.get("type", "unknown") for p in all_problems)),
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chart_data",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/charts")
async def get_chart_data():
    """
    Get aggregated data for analytics charts.

    Returns data structures optimized for ApexCharts:
    - problem_types: Pie chart data for problem type distribution
    - severity_counts: Bar chart data for severity levels
    - race_conditions: Donut chart data for race condition categories
    - top_files: Horizontal bar chart for files with most problems
    - summary: Overall summary statistics
    """
    code_collection = get_code_collection()

    # Initialize aggregation containers
    problem_types: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    race_conditions: Dict[str, int] = {}
    file_problems: Dict[str, int] = {}
    total_problems = 0

    if code_collection:
        try:
            # Query all problems from ChromaDB
            results = code_collection.get(
                where={"type": "problem"}, include=["metadatas"]
            )

            for metadata in results.get("metadatas", []):
                total_problems += 1

                # Aggregate by problem type
                ptype = metadata.get("problem_type", "unknown")
                problem_types[ptype] = problem_types.get(ptype, 0) + 1

                # Aggregate by severity
                severity = metadata.get("severity", "low")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

                # Aggregate race conditions separately
                if "race" in ptype.lower() or "thread" in ptype.lower():
                    race_conditions[ptype] = race_conditions.get(ptype, 0) + 1

                # Count problems per file
                file_path = metadata.get("file_path", "unknown")
                file_problems[file_path] = file_problems.get(file_path, 0) + 1

            storage_type = "chromadb"
            logger.info(f"Aggregated chart data for {total_problems} problems")

        except Exception as chroma_error:
            logger.warning(f"ChromaDB query failed: {chroma_error}")
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        redis_client = await get_redis_connection()

        if redis_client:
            try:
                for key in redis_client.scan_iter(match="codebase:problems:*"):
                    problems_data = redis_client.get(key)
                    if problems_data:
                        problems = json.loads(problems_data)
                        for problem in problems:
                            total_problems += 1

                            ptype = problem.get("type", "unknown")
                            problem_types[ptype] = problem_types.get(ptype, 0) + 1

                            severity = problem.get("severity", "low")
                            severity_counts[severity] = (
                                severity_counts.get(severity, 0) + 1
                            )

                            if "race" in ptype.lower() or "thread" in ptype.lower():
                                race_conditions[ptype] = (
                                    race_conditions.get(ptype, 0) + 1
                                )

                            file_path = problem.get("file_path", "unknown")
                            file_problems[file_path] = (
                                file_problems.get(file_path, 0) + 1
                            )

                storage_type = "redis"
            except Exception as redis_error:
                logger.error(f"Redis query failed: {redis_error}")
                return JSONResponse(
                    {
                        "status": "error",
                        "message": "Failed to retrieve chart data",
                        "error": str(redis_error),
                    },
                    status_code=500,
                )
        else:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "chart_data": None,
                }
            )

    # Convert to chart-friendly format

    # Problem types for pie chart (sorted by count descending)
    problem_types_data = [
        {"type": ptype, "count": count}
        for ptype, count in sorted(
            problem_types.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Severity for bar chart (ordered by severity level)
    severity_order = ["high", "medium", "low", "info", "hint"]
    severity_data = []
    for sev in severity_order:
        if sev in severity_counts:
            severity_data.append({"severity": sev, "count": severity_counts[sev]})
    # Add any unlisted severities
    for sev, count in severity_counts.items():
        if sev not in severity_order:
            severity_data.append({"severity": sev, "count": count})

    # Race conditions for donut chart
    race_conditions_data = [
        {"category": cat, "count": count}
        for cat, count in sorted(
            race_conditions.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Top files for horizontal bar chart (top 15)
    top_files_data = [
        {"file": file_path, "count": count}
        for file_path, count in sorted(
            file_problems.items(), key=lambda x: x[1], reverse=True
        )[:15]
    ]

    return JSONResponse(
        {
            "status": "success",
            "chart_data": {
                "problem_types": problem_types_data,
                "severity_counts": severity_data,
                "race_conditions": race_conditions_data,
                "top_files": top_files_data,
                "summary": {
                    "total_problems": total_problems,
                    "unique_problem_types": len(problem_types),
                    "files_with_problems": len(file_problems),
                    "race_condition_count": sum(race_conditions.values()),
                },
            },
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dependencies",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/dependencies")
async def get_dependencies():
    """
    Get file dependency analysis showing imports and module relationships.

    Returns:
    - modules: List of all modules/files in the codebase
    - imports: Import relationships (which file imports what)
    - dependency_graph: Graph structure for visualization
    - circular_dependencies: Detected circular import issues
    - external_dependencies: Third-party package dependencies
    """
    code_collection = get_code_collection()

    # Data structures
    modules: Dict[str, Dict] = {}  # file_path -> module info
    import_relationships: List[Dict] = []  # source -> target relationships
    external_deps: Dict[str, int] = {}  # external package -> usage count
    circular_deps: List[List[str]] = []

    if code_collection:
        try:
            # Query all Python files from ChromaDB
            # Get functions and classes to understand module structure
            results = code_collection.get(
                where={"type": {"$in": ["function", "class"]}}, include=["metadatas"]
            )

            # Build module map from stored data
            seen_files = set()
            for metadata in results.get("metadatas", []):
                file_path = metadata.get("file_path", "")
                if file_path and file_path not in seen_files:
                    seen_files.add(file_path)
                    modules[file_path] = {
                        "path": file_path,
                        "name": Path(file_path).stem,
                        "package": str(Path(file_path).parent),
                        "functions": 0,
                        "classes": 0,
                        "imports": [],
                    }

                if file_path in modules:
                    if metadata.get("type") == "function":
                        modules[file_path]["functions"] += 1
                    elif metadata.get("type") == "class":
                        modules[file_path]["classes"] += 1

            storage_type = "chromadb"
            logger.info(f"Found {len(modules)} modules in ChromaDB")

        except Exception as chroma_error:
            logger.warning(f"ChromaDB query failed: {chroma_error}")
            code_collection = None

    # Fallback: scan the actual filesystem for more detailed import analysis
    # This gives us actual import statements
    project_root = Path("/home/kali/Desktop/AutoBot")
    python_files = list(project_root.rglob("*.py"))

    # Filter out unwanted directories
    excluded_dirs = {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "archive",
        "dist",
        "build",
    }
    python_files = [
        f
        for f in python_files
        if not any(excluded in f.parts for excluded in excluded_dirs)
    ]

    # Analyze imports from each file
    stdlib_modules = {
        "os",
        "sys",
        "re",
        "json",
        "time",
        "datetime",
        "logging",
        "asyncio",
        "pathlib",
        "typing",
        "collections",
        "functools",
        "itertools",
        "subprocess",
        "threading",
        "multiprocessing",
        "uuid",
        "hashlib",
        "base64",
        "io",
        "contextlib",
        "abc",
        "dataclasses",
        "enum",
        "copy",
        "math",
        "random",
        "socket",
        "http",
        "urllib",
        "traceback",
        "inspect",
        "ast",
        "shutil",
        "tempfile",
        "warnings",
        "signal",
    }

    for py_file in python_files[:500]:  # Limit to 500 files for performance
        try:
            rel_path = str(py_file.relative_to(project_root))
            if rel_path not in modules:
                modules[rel_path] = {
                    "path": rel_path,
                    "name": py_file.stem,
                    "package": str(py_file.parent.relative_to(project_root)),
                    "functions": 0,
                    "classes": 0,
                    "imports": [],
                }

            # Use aiofiles for non-blocking file I/O
            try:
                async with aiofiles.open(py_file, "r", encoding="utf-8") as f:
                    content = await f.read()
            except OSError as e:
                logger.debug(f"Failed to read file {py_file}: {e}")
                continue

            tree = ast.parse(content)

            file_imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split(".")[0]
                        file_imports.append(module_name)
                        if module_name not in stdlib_modules:
                            external_deps[module_name] = (
                                external_deps.get(module_name, 0) + 1
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module.split(".")[0]
                        file_imports.append(node.module)
                        if module_name not in stdlib_modules:
                            external_deps[module_name] = (
                                external_deps.get(module_name, 0) + 1
                            )

            modules[rel_path]["imports"] = list(set(file_imports))

            # Create import relationships for graph
            for imp in file_imports:
                import_relationships.append(
                    {"source": rel_path, "target": imp, "type": "import"}
                )

        except Exception as e:
            logger.debug(f"Could not analyze {py_file}: {e}")
            continue

    # Detect circular dependencies (simplified check)
    import_map = {}
    for rel in import_relationships:
        source = rel["source"]
        target = rel["target"]
        if source not in import_map:
            import_map[source] = set()
        import_map[source].add(target)

    # Check for simple circular imports (A imports B, B imports A)
    for source, targets in import_map.items():
        for target in targets:
            # Check if target imports source (simple cycle)
            for other_source, other_targets in import_map.items():
                if target in other_source and source in other_targets:
                    cycle = sorted([source, other_source])
                    if cycle not in circular_deps:
                        circular_deps.append(cycle)

    # Build graph structure for visualization
    nodes = []
    edges = []

    for path, info in modules.items():
        nodes.append(
            {
                "id": path,
                "name": info["name"],
                "package": info["package"],
                "type": "module",
                "functions": info["functions"],
                "classes": info["classes"],
                "import_count": len(info["imports"]),
            }
        )

    for rel in import_relationships:
        edges.append({"from": rel["source"], "to": rel["target"], "type": rel["type"]})

    # Sort external dependencies by usage
    sorted_external = [
        {"package": pkg, "usage_count": count}
        for pkg, count in sorted(external_deps.items(), key=lambda x: x[1], reverse=True)
    ]

    return JSONResponse(
        {
            "status": "success",
            "dependency_data": {
                "modules": list(modules.values()),
                "import_relationships": import_relationships[:1000],  # Limit for UI
                "graph": {"nodes": nodes[:500], "edges": edges[:2000]},
                "circular_dependencies": circular_deps,
                "external_dependencies": sorted_external[:50],
                "summary": {
                    "total_modules": len(modules),
                    "total_import_relationships": len(import_relationships),
                    "circular_dependency_count": len(circular_deps),
                    "external_dependency_count": len(external_deps),
                },
            },
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_tree",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/import-tree")
async def get_import_tree():
    """
    Get bidirectional file import relationships for tree visualization.

    Returns for each file:
    - imports: What this file imports (modules/files)
    - imported_by: What files import this file

    This enables bidirectional navigation in the import tree UI.
    """
    project_root = Path("/home/kali/Desktop/AutoBot")
    python_files = list(project_root.rglob("*.py"))

    # Filter out unwanted directories
    excluded_dirs = {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "archive",
        "dist",
        "build",
    }
    python_files = [
        f
        for f in python_files
        if not any(excluded in f.parts for excluded in excluded_dirs)
    ]

    # Standard library modules (to mark as external)
    stdlib_modules = {
        "os", "sys", "re", "json", "time", "datetime", "logging", "asyncio",
        "pathlib", "typing", "collections", "functools", "itertools", "subprocess",
        "threading", "multiprocessing", "uuid", "hashlib", "base64", "io",
        "contextlib", "abc", "dataclasses", "enum", "copy", "math", "random",
        "socket", "http", "urllib", "traceback", "inspect", "ast", "shutil",
        "tempfile", "warnings", "signal", "argparse", "pickle", "csv", "sqlite3",
        "email", "html", "xml", "struct", "array", "queue", "heapq", "bisect",
        "weakref", "types", "operator", "string", "textwrap", "codecs",
    }

    # Data structures
    file_imports: Dict[str, List[Dict]] = {}  # file -> list of imports
    file_imported_by: Dict[str, List[Dict]] = {}  # file -> list of importers
    module_to_file: Dict[str, str] = {}  # module path -> file path

    # First pass: Build module to file mapping
    for py_file in python_files[:500]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            # Convert file path to module path (e.g., src/utils/redis_client.py -> src.utils.redis_client)
            module_path = rel_path.replace("/", ".").replace(".py", "")
            module_to_file[module_path] = rel_path

            # Also map shorter versions (utils.redis_client, redis_client)
            parts = module_path.split(".")
            for i in range(len(parts)):
                short_module = ".".join(parts[i:])
                if short_module not in module_to_file:
                    module_to_file[short_module] = rel_path
        except Exception:
            continue

    # Second pass: Analyze imports
    for py_file in python_files[:500]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            file_imports[rel_path] = []

            # Use aiofiles for non-blocking file I/O
            try:
                async with aiofiles.open(py_file, "r", encoding="utf-8") as f:
                    content = await f.read()
            except OSError as e:
                logger.debug(f"Failed to read file for import analysis {py_file}: {e}")
                continue

            tree = ast.parse(content)

            for node in ast.walk(tree):
                import_info = None

                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name
                        base_module = module_name.split(".")[0]
                        is_external = base_module in stdlib_modules or base_module not in INTERNAL_MODULE_PREFIXES  # O(1) lookup (Issue #326)
                        target_file = module_to_file.get(module_name)

                        import_info = {
                            "module": module_name,
                            "file": target_file,
                            "is_external": is_external and target_file is None,
                        }
                        file_imports[rel_path].append(import_info)

                        # Track imported_by relationship for internal files
                        if target_file and target_file != rel_path:
                            if target_file not in file_imported_by:
                                file_imported_by[target_file] = []
                            file_imported_by[target_file].append({
                                "file": rel_path,
                                "module": module_name,
                            })

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module
                        base_module = module_name.split(".")[0]
                        is_external = base_module in stdlib_modules or base_module not in INTERNAL_MODULE_PREFIXES  # O(1) lookup (Issue #326)
                        target_file = module_to_file.get(module_name)

                        import_info = {
                            "module": module_name,
                            "file": target_file,
                            "is_external": is_external and target_file is None,
                        }
                        file_imports[rel_path].append(import_info)

                        # Track imported_by relationship for internal files
                        if target_file and target_file != rel_path:
                            if target_file not in file_imported_by:
                                file_imported_by[target_file] = []
                            file_imported_by[target_file].append({
                                "file": rel_path,
                                "module": module_name,
                            })

        except Exception as e:
            logger.debug(f"Could not analyze {py_file}: {e}")
            continue

    # Build result with bidirectional relationships
    import_tree = []
    all_files = set(file_imports.keys()) | set(file_imported_by.keys())

    for file_path in sorted(all_files):
        # Deduplicate imports
        imports = file_imports.get(file_path, [])
        seen_modules = set()
        unique_imports = []
        for imp in imports:
            if imp["module"] not in seen_modules:
                seen_modules.add(imp["module"])
                unique_imports.append(imp)

        import_tree.append({
            "path": file_path,
            "imports": unique_imports,
            "imported_by": file_imported_by.get(file_path, []),
        })

    # Sort by connectivity (most connected files first)
    import_tree.sort(
        key=lambda x: len(x["imports"]) + len(x["imported_by"]),
        reverse=True
    )

    return JSONResponse({
        "status": "success",
        "import_tree": import_tree,
        "summary": {
            "total_files": len(import_tree),
            "total_import_relationships": sum(len(f["imports"]) for f in import_tree),
            "most_imported_files": [
                {"file": f["path"], "count": len(f["imported_by"])}
                for f in sorted(import_tree, key=lambda x: len(x["imported_by"]), reverse=True)[:10]
            ],
            "most_importing_files": [
                {"file": f["path"], "count": len(f["imports"])}
                for f in sorted(import_tree, key=lambda x: len(x["imports"]), reverse=True)[:10]
            ],
        },
    })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_call_graph",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/call-graph")
async def get_call_graph():
    """
    Get function call graph for visualization.

    Analyzes Python files to extract:
    - Function definitions (nodes)
    - Function calls within functions (edges)
    - Call depth and frequency metrics

    Returns data suitable for network/graph visualization.
    """
    project_root = Path("/home/kali/Desktop/AutoBot")
    python_files = list(project_root.rglob("*.py"))

    # Filter out unwanted directories
    excluded_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "env", ".env", "archive", "dist", "build",
    }
    python_files = [
        f for f in python_files
        if not any(excluded in f.parts for excluded in excluded_dirs)
    ]

    # Data structures
    functions: Dict[str, Dict] = {}  # function_id -> function info
    call_edges: List[Dict] = []  # caller -> callee relationships
    builtin_funcs = {
        "print", "len", "range", "str", "int", "float", "list", "dict", "set",
        "tuple", "bool", "type", "isinstance", "hasattr", "getattr", "setattr",
        "open", "sorted", "enumerate", "zip", "map", "filter", "any", "all",
        "min", "max", "sum", "abs", "round", "format", "input", "super",
    }

    class FunctionCallVisitor(ast.NodeVisitor):
        """AST visitor to extract function definitions and calls."""

        def __init__(self, file_path: str, module_path: str):
            self.file_path = file_path
            self.module_path = module_path
            self.current_class = None
            self.current_function = None
            self.function_stack = []

        def visit_ClassDef(self, node):
            old_class = self.current_class
            self.current_class = node.name
            self.generic_visit(node)
            self.current_class = old_class

        def visit_FunctionDef(self, node):
            self._process_function(node)

        def visit_AsyncFunctionDef(self, node):
            self._process_function(node)

        def _process_function(self, node):
            # Build function ID
            if self.current_class:
                func_id = f"{self.module_path}.{self.current_class}.{node.name}"
                full_name = f"{self.current_class}.{node.name}"
            else:
                func_id = f"{self.module_path}.{node.name}"
                full_name = node.name

            # Store function info
            functions[func_id] = {
                "id": func_id,
                "name": node.name,
                "full_name": full_name,
                "file": self.file_path,
                "module": self.module_path,
                "class": self.current_class,
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "args": len(node.args.args),
                "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
            }

            # Track calls within this function
            old_function = self.current_function
            self.current_function = func_id
            self.function_stack.append(func_id)
            self.generic_visit(node)
            self.function_stack.pop() if self.function_stack else None
            self.current_function = old_function

        def _get_decorator_name(self, decorator):
            if isinstance(decorator, ast.Name):
                return decorator.id
            elif isinstance(decorator, ast.Attribute):
                return decorator.attr
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    return decorator.func.id
                elif isinstance(decorator.func, ast.Attribute):
                    return decorator.func.attr
            return "unknown"

        def visit_Call(self, node):
            if not self.current_function:
                self.generic_visit(node)
                return

            callee_name = None

            # Get the function being called
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name and callee_name not in builtin_funcs:
                # Look for matching function in our registry
                callee_id = None

                # Try module-level function
                possible_id = f"{self.module_path}.{callee_name}"
                if possible_id in functions:
                    callee_id = possible_id

                # Try class method if in a class
                if not callee_id and self.current_class:
                    possible_id = f"{self.module_path}.{self.current_class}.{callee_name}"
                    if possible_id in functions:
                        callee_id = possible_id

                # Create edge even if callee not fully resolved
                call_edges.append({
                    "from": self.current_function,
                    "to": callee_id or callee_name,
                    "to_name": callee_name,
                    "resolved": callee_id is not None,
                    "line": node.lineno,
                })

            self.generic_visit(node)

    # Analyze files (limit for performance)
    for py_file in python_files[:300]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            module_path = rel_path.replace("/", ".").replace(".py", "")

            # Use aiofiles for non-blocking file I/O
            try:
                async with aiofiles.open(py_file, "r", encoding="utf-8") as f:
                    content = await f.read()
            except OSError as e:
                logger.debug(f"Failed to read file for call graph {py_file}: {e}")
                continue

            tree = ast.parse(content)
            visitor = FunctionCallVisitor(rel_path, module_path)
            visitor.visit(tree)

        except Exception as e:
            logger.debug(f"Could not analyze {py_file}: {e}")
            continue

    # Build graph nodes (only functions with connections)
    connected_funcs = set()
    for edge in call_edges:
        connected_funcs.add(edge["from"])
        if edge["resolved"]:
            connected_funcs.add(edge["to"])

    nodes = []
    for func_id, info in functions.items():
        if func_id in connected_funcs:
            nodes.append({
                "id": func_id,
                "name": info["name"],
                "full_name": info["full_name"],
                "module": info["module"],
                "class": info["class"],
                "file": info["file"],
                "line": info["line"],
                "is_async": info["is_async"],
            })

    # Count call frequency
    call_counts = {}
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        call_counts[key] = call_counts.get(key, 0) + 1

    # Deduplicate edges with count
    unique_edges = []
    seen_edges = set()
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append({
                "from": edge["from"],
                "to": edge["to"],
                "to_name": edge["to_name"],
                "resolved": edge["resolved"],
                "count": call_counts[key],
            })

    # Calculate metrics
    outgoing_calls = {}
    incoming_calls = {}
    for edge in unique_edges:
        outgoing_calls[edge["from"]] = outgoing_calls.get(edge["from"], 0) + edge["count"]
        if edge["resolved"]:
            incoming_calls[edge["to"]] = incoming_calls.get(edge["to"], 0) + edge["count"]

    # Top callers and callees
    top_callers = sorted(
        [{"function": k, "calls": v} for k, v in outgoing_calls.items()],
        key=lambda x: x["calls"], reverse=True
    )[:10]

    top_called = sorted(
        [{"function": k, "calls": v} for k, v in incoming_calls.items()],
        key=lambda x: x["calls"], reverse=True
    )[:10]

    return JSONResponse({
        "status": "success",
        "call_graph": {
            "nodes": nodes[:500],  # Limit for UI performance
            "edges": unique_edges[:2000],
        },
        "summary": {
            "total_functions": len(functions),
            "connected_functions": len(nodes),
            "total_call_relationships": len(unique_edges),
            "resolved_calls": len([e for e in unique_edges if e["resolved"]]),
            "unresolved_calls": len([e for e in unique_edges if not e["resolved"]]),
            "top_callers": top_callers,
            "most_called": top_called,
        },
    })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_declarations",
    error_code_prefix="CODEBASE",
)
@router.get("/declarations")
async def get_code_declarations(declaration_type: Optional[str] = None):
    """Get code declarations (functions, classes, variables) detected during analysis"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_declarations = []

    if code_collection:
        try:
            # Query ChromaDB for functions and classes
            where_filter = {"type": {"$in": ["function", "class"]}}

            results = code_collection.get(where=where_filter, include=["metadatas"])

            # Extract declarations from metadata
            for metadata in results.get("metadatas", []):
                decl = {
                    "name": metadata.get("name", ""),
                    "type": metadata.get("type", ""),
                    "file_path": metadata.get("file_path", ""),
                    "line_number": (
                        int(metadata.get("start_line", 0))
                        if metadata.get("start_line")
                        else 0
                    ),
                    "usage_count": 1,  # Default, can be calculated later
                    "is_exported": True,  # Default
                    "parameters": (
                        metadata.get("parameters", "").split(",")
                        if metadata.get("parameters")
                        else []
                    ),
                }
                all_declarations.append(decl)

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_declarations)} declarations from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, returning empty declarations"
            )
            # Declarations don't exist in old Redis structure, so just return empty
            storage_type = "chromadb"

    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "declarations": [],
            }
        )

    # Count by type
    functions = sum(1 for d in all_declarations if d.get("type") == "function")
    classes = sum(1 for d in all_declarations if d.get("type") == "class")
    variables = sum(1 for d in all_declarations if d.get("type") == "variable")

    # Sort by usage count (most used first)
    all_declarations.sort(key=lambda x: x.get("usage_count", 0), reverse=True)

    return JSONResponse(
        {
            "status": "success",
            "declarations": all_declarations,
            "total_count": len(all_declarations),
            "functions": functions,
            "classes": classes,
            "variables": variables,
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_duplicate_code",
    error_code_prefix="CODEBASE",
)
@router.get("/duplicates")
async def get_duplicate_code():
    """Get duplicate code detected during analysis (using semantic similarity in ChromaDB)"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_duplicates = []

    if code_collection:
        try:
            # Query ChromaDB for duplicate markers
            # Note: Duplicates will be detected via semantic similarity when we regenerate
            results = code_collection.get(
                where={"type": "duplicate"}, include=["metadatas"]
            )

            # Extract duplicates from metadata
            for metadata in results.get("metadatas", []):
                duplicate = {
                    "code_snippet": metadata.get("code_snippet", ""),
                    "files": (
                        metadata.get("files", "").split(",")
                        if metadata.get("files")
                        else []
                    ),
                    "similarity_score": (
                        float(metadata.get("similarity_score", 0.0))
                        if metadata.get("similarity_score")
                        else 0.0
                    ),
                    "line_numbers": metadata.get("line_numbers", ""),
                }
                all_duplicates.append(duplicate)

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_duplicates)} duplicates from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, returning empty duplicates"
            )
            # Duplicates don't exist yet, will be generated during reindexing
            storage_type = "chromadb"

    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "duplicates": [],
            }
        )

    # Sort by number of files affected (most duplicated first)
    all_duplicates.sort(key=lambda x: len(x.get("files", [])), reverse=True)

    return JSONResponse(
        {
            "status": "success",
            "duplicates": all_duplicates,
            "total_count": len(all_duplicates),
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_codebase_cache",
    error_code_prefix="CODEBASE",
)
@router.delete("/cache")
async def clear_codebase_cache():
    """Clear codebase analysis cache from storage"""
    redis_client = await get_redis_connection()

    if redis_client:
        # Get all codebase keys
        keys_to_delete = []
        for key in redis_client.scan_iter(match="codebase:*"):
            keys_to_delete.append(key)

        if keys_to_delete:
            redis_client.delete(*keys_to_delete)

        storage_type = "redis"
    else:
        # Clear in-memory storage
        if _in_memory_storage:
            keys_to_delete = []
            for key in _in_memory_storage.scan_iter("codebase:*"):
                keys_to_delete.append(key)

            _in_memory_storage.delete(*keys_to_delete)
            deleted_count = len(keys_to_delete)
        else:
            deleted_count = 0

        storage_type = "memory"

    return JSONResponse(
        {
            "status": "success",
            "message": (
                f"Cleared {len(keys_to_delete) if redis_client else deleted_count} "
                f"cache entries from {storage_type}"
            ),
            "deleted_keys": len(keys_to_delete) if redis_client else deleted_count,
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_config_duplicates",
    error_code_prefix="CODEBASE",
)
@router.get("/config-duplicates")
async def detect_config_duplicates_endpoint():
    """
    Detect configuration value duplicates across codebase (Issue #341).

    Returns configuration values that appear in multiple files,
    helping enforce single-source-of-truth principle.

    Returns:
        JSONResponse with duplicate detection results
    """
    from .config_duplication_detector import detect_config_duplicates

    # Get project root (4 levels up from this file)
    project_root = Path(__file__).resolve().parents[3]

    # Run detection
    result = detect_config_duplicates(str(project_root))

    return JSONResponse(
        {
            "status": "success",
            "duplicates_found": result["duplicates_found"],
            "duplicates": result["duplicates"],
            "report": result["report"],
        }
    )
