# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dependency analysis endpoints
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List

import aiofiles
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_code_collection
from .shared import get_project_root, STDLIB_MODULES

logger = logging.getLogger(__name__)

router = APIRouter()


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

            logger.info(f"Found {len(modules)} modules in ChromaDB")

        except Exception as chroma_error:
            logger.warning(f"ChromaDB query failed: {chroma_error}")
            code_collection = None

    # Fallback: scan the actual filesystem for more detailed import analysis
    # This gives us actual import statements
    project_root = get_project_root()
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
                        if module_name not in STDLIB_MODULES:
                            external_deps[module_name] = (
                                external_deps.get(module_name, 0) + 1
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module.split(".")[0]
                        file_imports.append(node.module)
                        if module_name not in STDLIB_MODULES:
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
