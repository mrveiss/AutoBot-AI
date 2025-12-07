# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase scanning and indexing functions
"""

import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import HTTPException

from backend.type_defs.common import Metadata

from .analyzers import analyze_python_file, analyze_javascript_vue_file
from .storage import get_code_collection

logger = logging.getLogger(__name__)

# File extension categories (Issue #315)
PYTHON_EXTENSIONS = {".py"}
JS_EXTENSIONS = {".js", ".ts"}
VUE_EXTENSIONS = {".vue"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".conf"}

# Directories to skip during scanning (Issue #315)
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    "dist", "build", ".venv", "venv", ".DS_Store", "logs", "temp", "archives",
}


async def _get_file_analysis(
    file_path: Path, extension: str, stats: dict
) -> Optional[dict]:
    """Get analysis for a file based on its type (Issue #315)."""
    if extension in PYTHON_EXTENSIONS:
        stats["python_files"] += 1
        return await analyze_python_file(str(file_path))

    if extension in JS_EXTENSIONS:
        stats["javascript_files"] += 1
        return analyze_javascript_vue_file(str(file_path))

    if extension in VUE_EXTENSIONS:
        stats["vue_files"] += 1
        return analyze_javascript_vue_file(str(file_path))

    if extension in CONFIG_EXTENSIONS:
        stats["config_files"] += 1
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
# Helper Functions (Issue #298 - Reduce Deep Nesting)
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

        await asyncio.to_thread(
            collection.add,
            ids=[f"problem_{problem_idx}_{problem.get('type', 'unknown')}"],
            documents=[problem_doc],
            metadatas=[metadata],
        )
    except Exception as e:
        logger.debug(f"Failed to store problem immediately: {e}")


async def _store_problems_batch_to_chromadb(
    collection,
    problems: list,
    start_idx: int,
) -> None:
    """Store multiple problems to ChromaDB collection in a single batch operation."""
    if not collection or not problems:
        return

    try:
        ids = []
        documents = []
        metadatas = []

        for i, problem in enumerate(problems):
            problem_idx = start_idx + i
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

            ids.append(f"problem_{problem_idx}_{problem.get('type', 'unknown')}")
            documents.append(problem_doc)
            metadatas.append(metadata)

        # Single batch operation instead of N individual calls
        await asyncio.to_thread(
            collection.add,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug(f"Batch stored {len(problems)} problems to ChromaDB")
    except Exception as e:
        logger.debug(f"Failed to batch store problems: {e}")


def _aggregate_file_analysis(
    analysis_results: Dict,
    file_analysis: Dict,
    relative_path: str,
) -> None:
    """Aggregate file analysis results into main results dict."""
    analysis_results["files"][relative_path] = file_analysis
    analysis_results["stats"]["total_lines"] += file_analysis.get("line_count", 0)
    analysis_results["stats"]["total_functions"] += len(file_analysis.get("functions", []))
    analysis_results["stats"]["total_classes"] += len(file_analysis.get("classes", []))

    for func in file_analysis.get("functions", []):
        func["file_path"] = relative_path
        analysis_results["all_functions"].append(func)

    for cls in file_analysis.get("classes", []):
        cls["file_path"] = relative_path
        analysis_results["all_classes"].append(cls)

    for hardcode in file_analysis.get("hardcodes", []):
        hardcode["file_path"] = relative_path
        analysis_results["all_hardcodes"].append(hardcode)


async def _process_file_problems(
    file_analysis: Dict,
    relative_path: str,
    analysis_results: Dict,
    immediate_store_collection,
) -> None:
    """Process problems from file analysis and store to ChromaDB (Issue #315: extracted).

    This helper extracts problem processing logic to reduce nesting depth in scan_codebase.
    """
    file_problems = file_analysis.get("problems", [])
    if not file_problems:
        return

    # Track starting index for batch operation
    start_idx = len(analysis_results["all_problems"])

    # Add file_path to each problem and collect for batch storage
    for problem in file_problems:
        problem["file_path"] = relative_path
        analysis_results["all_problems"].append(problem)

    # Batch store all problems from this file in a single operation
    await _store_problems_batch_to_chromadb(
        immediate_store_collection, file_problems, start_idx
    )


# =============================================================================
# End of Helper Functions
# =============================================================================


async def scan_codebase(
    root_path: Optional[str] = None,
    progress_callback: Optional[callable] = None,
    immediate_store_collection=None,
) -> Metadata:
    """Scan the entire codebase using MCP-like file operations (Issue #315 - reduced nesting)."""
    # Use project-relative path if not specified
    if root_path is None:
        project_root = Path(__file__).parent.parent.parent
        root_path = str(project_root)

    analysis_results = {
        "files": {},
        "stats": {
            "total_files": 0,
            "python_files": 0,
            "javascript_files": 0,
            "vue_files": 0,
            "config_files": 0,
            "other_files": 0,
            "total_lines": 0,
            "total_functions": 0,
            "total_classes": 0,
        },
        "all_functions": [],
        "all_classes": [],
        "all_hardcodes": [],
        "all_problems": [],
    }

    try:
        root_path_obj = Path(root_path)

        # First pass: count total files for progress tracking
        total_files = 0
        if progress_callback:
            for file_path in root_path_obj.rglob("*"):
                if file_path.is_file():
                    if not any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                        total_files += 1

            # Report total files discovered
            await progress_callback(
                operation="Scanning files",
                current=0,
                total=total_files,
                current_file="Initializing...",
            )

        # Walk through all files
        files_processed = 0
        for file_path in root_path_obj.rglob("*"):
            if file_path.is_file():
                # Skip if in excluded directory
                if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                    continue

                extension = file_path.suffix.lower()
                relative_path = str(file_path.relative_to(root_path_obj))

                analysis_results["stats"]["total_files"] += 1
                files_processed += 1

                # Update progress every 10 files or if callback provided
                if progress_callback and files_processed % 10 == 0:
                    await progress_callback(
                        operation="Scanning files",
                        current=files_processed,
                        total=total_files,
                        current_file=relative_path,
                    )

                # Get file analysis using type dispatch (Issue #315)
                file_analysis = await _get_file_analysis(
                    file_path, extension, analysis_results["stats"]
                )

                if file_analysis:
                    # Aggregate functions, classes, and hardcodes
                    _aggregate_file_analysis(analysis_results, file_analysis, relative_path)

                    # Process and store problems (Issue #315: uses helper to reduce nesting)
                    await _process_file_problems(
                        file_analysis, relative_path, analysis_results, immediate_store_collection
                    )

        # Calculate average file size
        if analysis_results["stats"]["total_files"] > 0:
            analysis_results["stats"]["average_file_size"] = (
                analysis_results["stats"]["total_lines"]
                / analysis_results["stats"]["total_files"]
            )
        else:
            analysis_results["stats"]["average_file_size"] = 0

        analysis_results["stats"]["last_indexed"] = datetime.now().isoformat()

        return analysis_results

    except Exception as e:
        logger.error(f"Error scanning codebase: {e}")
        raise HTTPException(status_code=500, detail=f"Codebase scan failed: {str(e)}")


async def do_indexing_with_progress(task_id: str, root_path: str):
    """
    Background task: Index codebase with real-time progress updates

    Updates indexing_tasks[task_id] with progress information:
    - status: "running" | "completed" | "failed"
    - progress: {current, total, percent, current_file, operation}
    - result: final results when completed
    - error: error message if failed
    """
    try:
        logger.info(
            f"[Task {task_id}] Starting background codebase indexing for: {root_path}"
        )

        # Initialize task status with enhanced phase and batch tracking
        async with _tasks_lock:
            indexing_tasks[task_id] = {
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
                    "batch_size": 5000,  # ChromaDB max batch size
                    "items_per_batch": [],
                },
                "stats": {
                    "files_scanned": 0,
                    "problems_found": 0,
                    "functions_found": 0,
                    "classes_found": 0,
                    "items_stored": 0,
                },
                "result": None,
                "error": None,
                "started_at": datetime.now().isoformat(),
            }

        # Helper to update phase status
        def update_phase(phase_id: str, status: str):
            """Update phase status and track completion in task state."""
            phases = indexing_tasks[task_id]["phases"]
            phases["current_phase"] = phase_id
            for phase in phases["phase_list"]:
                if phase["id"] == phase_id:
                    phase["status"] = status
                    if status == "completed" and phase_id not in phases["phases_completed"]:
                        phases["phases_completed"].append(phase_id)
                    break

        # Helper to update batch info
        def update_batch_info(current_batch: int, total_batches: int, items_in_batch: int = 0):
            """Update batch progress tracking for indexing task."""
            batches = indexing_tasks[task_id]["batches"]
            batches["current_batch"] = current_batch
            batches["total_batches"] = total_batches
            if items_in_batch > 0 and current_batch > len(batches["items_per_batch"]):
                batches["items_per_batch"].append(items_in_batch)

        # Helper to update stats
        def update_stats(**kwargs):
            """Update task statistics with provided key-value pairs."""
            for key, value in kwargs.items():
                if key in indexing_tasks[task_id]["stats"]:
                    indexing_tasks[task_id]["stats"][key] = value

        # Progress callback function
        async def update_progress(
            operation: str, current: int, total: int, current_file: str,
            phase: str = None, batch_info: dict = None
        ):
            percent = int((current / total * 100)) if total > 0 else 0
            indexing_tasks[task_id]["progress"] = {
                "current": current,
                "total": total,
                "percent": percent,
                "current_file": current_file,
                "operation": operation,
            }

            # Update phase if specified
            if phase:
                update_phase(phase, "running")

            # Update batch info if specified
            if batch_info:
                update_batch_info(
                    batch_info.get("current", 0),
                    batch_info.get("total", 0),
                    batch_info.get("items", 0)
                )

            logger.debug(
                f"[Task {task_id}] Progress: {operation} - {current}/{total} ({percent}%)"
            )

        # Get ChromaDB collection FIRST so we can store problems immediately
        update_phase("init", "running")
        await update_progress(
            operation="Preparing ChromaDB",
            current=0,
            total=1,
            current_file="Connecting to ChromaDB...",
            phase="init",
        )

        code_collection = await asyncio.to_thread(get_code_collection)
        storage_type = "chromadb" if code_collection else "memory"

        if code_collection:
            # Clear existing data before scanning
            await update_progress(
                operation="Clearing old ChromaDB data",
                current=0,
                total=1,
                current_file="Removing existing entries...",
                phase="init",
            )

            try:
                existing_data = await asyncio.to_thread(code_collection.get)
                existing_ids = existing_data["ids"]
                if existing_ids:
                    await asyncio.to_thread(code_collection.delete, ids=existing_ids)
                    logger.info(
                        f"[Task {task_id}] Cleared {len(existing_ids)} existing items from ChromaDB"
                    )
            except Exception as e:
                logger.warning(f"[Task {task_id}] Error clearing collection: {e}")

        # Mark init phase as completed, start scan phase
        update_phase("init", "completed")
        update_phase("scan", "running")

        # Scan the codebase with progress tracking
        # Pass collection so problems can be stored immediately as they're found
        analysis_results = await scan_codebase(
            root_path,
            progress_callback=update_progress,
            immediate_store_collection=code_collection,
        )

        # Update stats from scan results
        update_stats(
            files_scanned=analysis_results["stats"]["total_files"],
            problems_found=len(analysis_results["all_problems"]),
            functions_found=len(analysis_results["all_functions"]),
            classes_found=len(analysis_results["all_classes"]),
        )

        # Mark scan phase completed
        update_phase("scan", "completed")

        if code_collection:
            # Start prepare phase
            update_phase("prepare", "running")

            # Problems were already stored during scan, now store functions and classes
            # Prepare batch data for ChromaDB (excluding problems which are already stored)
            batch_ids = []
            batch_documents = []
            batch_metadatas = []

            # Store functions and classes (problems were already stored during scan)
            total_items_to_store = (
                len(analysis_results["all_functions"])
                + len(analysis_results["all_classes"])
                + 1  # stats (problems already stored)
            )
            items_prepared = 0

            await update_progress(
                operation="Preparing functions",
                current=0,
                total=total_items_to_store,
                current_file="Processing functions...",
                phase="prepare",
            )

            for idx, func in enumerate(analysis_results["all_functions"]):
                doc_text = """
Function: {func['name']}
File: {func.get('file_path', 'unknown')}
Line: {func.get('line', 0)}
Parameters: {', '.join(func.get('args', []))}
Docstring: {func.get('docstring', 'No documentation')}
                """.strip()

                batch_ids.append(f"function_{idx}_{func['name']}")
                batch_documents.append(doc_text)
                batch_metadatas.append(
                    {
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
                )

                items_prepared += 1
                if items_prepared % 100 == 0:
                    await update_progress(
                        operation="Storing functions",
                        current=items_prepared,
                        total=total_items_to_store,
                        current_file=f"Function {idx+1}/{len(analysis_results['all_functions'])}",
                    )

            # Store classes
            await update_progress(
                operation="Storing classes",
                current=items_prepared,
                total=total_items_to_store,
                current_file="Processing classes...",
            )

            for idx, cls in enumerate(analysis_results["all_classes"]):
                doc_text = """
Class: {cls['name']}
File: {cls.get('file_path', 'unknown')}
Line: {cls.get('line', 0)}
Methods: {', '.join(cls.get('methods', []))}
Docstring: {cls.get('docstring', 'No documentation')}
                """.strip()

                batch_ids.append(f"class_{idx}_{cls['name']}")
                batch_documents.append(doc_text)
                batch_metadatas.append(
                    {
                        "type": "class",
                        "name": cls["name"],
                        "file_path": cls.get("file_path", ""),
                        "start_line": str(cls.get("line", 0)),
                        "methods": ",".join(cls.get("methods", [])),
                        "language": "python",
                    }
                )

                items_prepared += 1
                if items_prepared % 50 == 0:
                    await update_progress(
                        operation="Storing classes",
                        current=items_prepared,
                        total=total_items_to_store,
                        current_file=f"Class {idx+1}/{len(analysis_results['all_classes'])}",
                    )

            # NOTE: Problems were already stored immediately during scan phase
            # No need to store them again here

            # Store stats as a special document
            stats_doc = """
Codebase Statistics:
Total Files: {analysis_results['stats']['total_files']}
Total Lines: {analysis_results['stats']['total_lines']}
Python Files: {analysis_results['stats']['python_files']}
JavaScript Files: {analysis_results['stats']['javascript_files']}
Vue Files: {analysis_results['stats']['vue_files']}
Total Functions: {analysis_results['stats']['total_functions']}
Total Classes: {analysis_results['stats']['total_classes']}
Last Indexed: {analysis_results['stats']['last_indexed']}
            """.strip()

            batch_ids.append("codebase_stats")
            batch_documents.append(stats_doc)
            batch_metadatas.append(
                {
                    "type": "stats",
                    **{k: str(v) for k, v in analysis_results["stats"].items()},
                }
            )

            items_prepared += 1

            # Mark prepare phase completed
            update_phase("prepare", "completed")

            # Add all to ChromaDB in batches (ChromaDB has max batch size limit)
            if batch_ids:
                # Start store phase
                update_phase("store", "running")

                BATCH_SIZE = (
                    5000  # ChromaDB max batch size is ~5461, use 5000 for safety
                )
                total_items = len(batch_ids)
                items_stored = 0
                total_batches = (total_items + BATCH_SIZE - 1) // BATCH_SIZE

                # Initialize batch tracking
                update_batch_info(0, total_batches, 0)

                await update_progress(
                    operation="Writing to ChromaDB",
                    current=0,
                    total=total_items,
                    current_file="Batch storage in progress...",
                    phase="store",
                    batch_info={"current": 0, "total": total_batches, "items": 0}
                )

                for i in range(0, total_items, BATCH_SIZE):
                    batch_slice_ids = batch_ids[i : i + BATCH_SIZE]
                    batch_slice_docs = batch_documents[i : i + BATCH_SIZE]
                    batch_slice_metas = batch_metadatas[i : i + BATCH_SIZE]
                    batch_num = i // BATCH_SIZE + 1

                    # Run blocking ChromaDB add in thread pool
                    await asyncio.to_thread(
                        code_collection.add,
                        ids=batch_slice_ids,
                        documents=batch_slice_docs,
                        metadatas=batch_slice_metas,
                    )
                    items_stored += len(batch_slice_ids)

                    # Update batch tracking with completed batch info
                    indexing_tasks[task_id]["batches"]["completed_batches"] = batch_num

                    await update_progress(
                        operation="Writing to ChromaDB",
                        current=items_stored,
                        total=total_items,
                        current_file=f"Batch {batch_num}/{total_batches}",
                        phase="store",
                        batch_info={"current": batch_num, "total": total_batches, "items": len(batch_slice_ids)}
                    )

                    # Update items stored stats
                    update_stats(items_stored=items_stored)

                    logger.info(
                        f"[Task {task_id}] Stored batch {batch_num}/{total_batches}: "
                        f"{len(batch_slice_ids)} items ({items_stored}/{total_items})"
                    )

                # Mark store phase completed
                update_phase("store", "completed")

                logger.info(
                    f"[Task {task_id}] ✅ Stored total of {items_stored} items in ChromaDB"
                )
        else:
            storage_type = "failed"
            raise Exception("ChromaDB connection failed")

        # Mark finalize phase
        update_phase("finalize", "running")

        # Mark task as completed
        indexing_tasks[task_id]["status"] = "completed"
        total_files = analysis_results['stats']['total_files']
        indexing_tasks[task_id]["result"] = {
            "status": "success",
            "message": f"Indexed {total_files} files using {storage_type} storage",
            "stats": analysis_results["stats"],
            "storage_type": storage_type,
            "timestamp": datetime.now().isoformat(),
        }
        indexing_tasks[task_id]["completed_at"] = datetime.now().isoformat()

        # Mark finalize phase as completed
        update_phase("finalize", "completed")

        logger.info(f"[Task {task_id}] ✅ Indexing completed successfully")

    except Exception as e:
        logger.error(f"[Task {task_id}] ❌ Indexing failed: {e}", exc_info=True)
        indexing_tasks[task_id]["status"] = "failed"
        indexing_tasks[task_id]["error"] = str(e)
        indexing_tasks[task_id]["failed_at"] = datetime.now().isoformat()


