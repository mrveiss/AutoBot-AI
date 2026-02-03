# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dependency analysis endpoints
"""

import ast
import asyncio
import logging
from pathlib import Path
from typing import Dict, List

import aiofiles
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_code_collection
from .shared import STDLIB_MODULES, get_project_root

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_imports_from_ast(tree: ast.AST, stdlib_modules: set) -> tuple:
    """Extract import names and external dependencies from AST (Issue #315)."""
    file_imports = []
    external_deps = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".")[0]
                file_imports.append(module_name)
                if module_name not in stdlib_modules:
                    external_deps[module_name] = external_deps.get(module_name, 0) + 1
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_name = node.module.split(".")[0]
            file_imports.append(node.module)
            if module_name not in stdlib_modules:
                external_deps[module_name] = external_deps.get(module_name, 0) + 1

    return list(set(file_imports)), external_deps


def _process_chromadb_metadata(
    metadata: dict, modules: Dict[str, Dict], seen_files: set
) -> None:
    """Process a single metadata entry from ChromaDB (Issue #315: extracted).

    Updates modules dict and seen_files set in place.
    """
    file_path = metadata.get("file_path", "")
    if not file_path:
        return

    # Add new module if not seen
    if file_path not in seen_files:
        seen_files.add(file_path)
        modules[file_path] = {
            "path": file_path,
            "name": Path(file_path).stem,
            "package": str(Path(file_path).parent),
            "functions": 0,
            "classes": 0,
            "imports": [],
        }

    # Update counts based on type
    if file_path not in modules:
        return
    metadata_type = metadata.get("type")
    if metadata_type == "function":
        modules[file_path]["functions"] += 1
    elif metadata_type == "class":
        modules[file_path]["classes"] += 1


async def _read_file_content(py_file: Path) -> str | None:
    """Read file content safely with aiofiles (Issue #315)."""
    try:
        async with aiofiles.open(py_file, "r", encoding="utf-8") as f:
            return await f.read()
    except OSError as e:
        logger.debug("Failed to read file %s: %s", py_file, e)
        return None


def _build_import_map(import_relationships: List[Dict]) -> Dict[str, set]:
    """Build import map from relationships. (Issue #315 - extracted)"""
    import_map: Dict[str, set] = {}
    for rel in import_relationships:
        source = rel["source"]
        if source not in import_map:
            import_map[source] = set()
        import_map[source].add(rel["target"])
    return import_map


def _detect_circular_deps(import_relationships: List[Dict]) -> List[List[str]]:
    """Detect simple circular dependencies (A→B, B→A) (Issue #315)."""
    import_map = _build_import_map(import_relationships)

    # Find mutual imports (A imports B and B imports A)
    circular_deps = []
    seen = set()
    for source, targets in import_map.items():
        for target in targets:
            if target in import_map and source in import_map[target]:
                cycle = tuple(sorted([source, target]))
                if cycle not in seen:
                    seen.add(cycle)
                    circular_deps.append(list(cycle))
    return circular_deps


async def _analyze_file_imports(
    py_file: Path,
    project_root: Path,
    modules: Dict[str, Dict],
    import_relationships: List[Dict],
    external_deps: Dict[str, int],
) -> None:
    """
    Analyze imports from a single Python file and update data structures.

    Issue #281: Extracted helper for file import analysis.

    Args:
        py_file: Python file to analyze
        project_root: Root directory of the project
        modules: Dict to update with module info
        import_relationships: List to update with import relationships
        external_deps: Dict to update with external dependency counts
    """
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

    content = await _read_file_content(py_file)
    if content is None:
        return

    try:
        tree = ast.parse(content)
    except SyntaxError:
        logger.debug("Syntax error parsing %s", py_file)
        return

    file_imports, file_ext_deps = _extract_imports_from_ast(tree, STDLIB_MODULES)
    modules[rel_path]["imports"] = file_imports

    # Merge external dependencies
    for pkg, count in file_ext_deps.items():
        external_deps[pkg] = external_deps.get(pkg, 0) + count

    # Create import relationships for graph
    for imp in file_imports:
        import_relationships.append(
            {"source": rel_path, "target": imp, "type": "import"}
        )


def _build_visualization_graph(
    modules: Dict[str, Dict],
    import_relationships: List[Dict],
    external_deps: Dict[str, int],
    circular_deps: List[List[str]],
) -> Dict:
    """
    Build graph structure and response dict for visualization.

    Issue #281: Extracted helper for graph building.

    Args:
        modules: Module information dict
        import_relationships: List of import relationships
        external_deps: External dependency counts
        circular_deps: Detected circular dependencies

    Returns:
        Complete response dictionary for JSONResponse
    """
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
        for pkg, count in sorted(
            external_deps.items(), key=lambda x: x[1], reverse=True
        )
    ]

    return {
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dependencies",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/dependencies")
async def get_dependencies():
    """
    Get file dependency analysis showing imports and module relationships.

    Issue #281: Refactored from 146 lines to use extracted helper methods.

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

    if code_collection:
        try:
            # Query all Python files from ChromaDB
            results = code_collection.get(
                where={"type": {"$in": ["function", "class"]}}, include=["metadatas"]
            )

            # Build module map from stored data (Issue #315: uses helper)
            seen_files = set()
            for metadata in results.get("metadatas", []):
                _process_chromadb_metadata(metadata, modules, seen_files)

            logger.info("Found %s modules in ChromaDB", len(modules))

        except Exception as chroma_error:
            logger.warning("ChromaDB query failed: %s", chroma_error)
            code_collection = None

    # Scan filesystem for detailed import analysis
    project_root = get_project_root()
    # Issue #358 - avoid blocking (use lambda to defer rglob to thread)
    python_files = await asyncio.to_thread(lambda: list(project_root.rglob("*.py")))

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

    # Analyze imports from each file (Issue #281: uses extracted helper)
    for py_file in python_files[:500]:  # Limit to 500 files for performance
        await _analyze_file_imports(
            py_file, project_root, modules, import_relationships, external_deps
        )

    # Detect circular dependencies
    circular_deps = _detect_circular_deps(import_relationships)

    # Build and return visualization response (Issue #281: uses extracted helper)
    return JSONResponse(
        _build_visualization_graph(
            modules, import_relationships, external_deps, circular_deps
        )
    )
