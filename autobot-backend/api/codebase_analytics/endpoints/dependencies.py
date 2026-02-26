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
from typing import Dict, List, Set

import aiofiles
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_code_collection
from .shared import COMMON_THIRD_PARTY, STDLIB_MODULES, get_project_root

logger = logging.getLogger(__name__)

router = APIRouter()

# Combined set for fast lookup during import extraction (#1197)
_EXTERNAL_MODULES = STDLIB_MODULES | COMMON_THIRD_PARTY


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


# =====================================================================
# Circular import detection pipeline (#1197)
# =====================================================================


def _get_type_checking_lines(tree: ast.AST) -> Set[int]:
    """Identify line numbers inside TYPE_CHECKING blocks (#1197)."""
    tc_lines: Set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if is_tc:
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    tc_lines.add(child.lineno)
    return tc_lines


def _extract_runtime_imports(tree: ast.AST) -> List[str]:
    """Extract module-level imports only, excluding deferred/function-scoped.

    Walks the AST but skips FunctionDef/AsyncFunctionDef bodies, since
    imports inside functions are deferred and don't create circular
    dependency risks at module-load time. (#1197, #1210)
    """
    tc_lines = _get_type_checking_lines(tree)
    imports: List[str] = []

    def _walk_module_level(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Import):
                for alias in child.names:
                    top = alias.name.split(".")[0]
                    if child.lineno not in tc_lines and top not in _EXTERNAL_MODULES:
                        imports.append(alias.name)
            elif isinstance(child, ast.ImportFrom) and child.module:
                top = child.module.split(".")[0]
                if child.lineno not in tc_lines and top not in _EXTERNAL_MODULES:
                    imports.append(child.module)
            else:
                _walk_module_level(child)

    _walk_module_level(tree)
    return list(set(imports))


def _build_module_index(modules: Dict[str, Dict]) -> Dict[str, str]:
    """Build module name -> file path lookup from scanned modules (#1197).

    Registers each file under its dotted module name (with and without
    the top-level directory prefix) for import resolution.
    """
    index: Dict[str, str] = {}
    for file_path in modules:
        path = Path(file_path)
        parts = list(path.parts)
        if not parts:
            continue

        if parts[-1] == "__init__.py":
            mod_parts = parts[:-1]
        else:
            mod_parts = parts[:-1] + [parts[-1].replace(".py", "")]

        if not mod_parts:
            continue

        # Normalize hyphens to underscores (filesystem vs import convention)
        norm_parts = [p.replace("-", "_") for p in mod_parts]

        # Full dotted path (e.g., autobot_backend.utils.resource_factory)
        index[".".join(norm_parts)] = file_path

        # Short path without top-level dir (e.g., utils.resource_factory)
        if len(norm_parts) > 1:
            short = ".".join(norm_parts[1:])
            if short not in index:
                index[short] = file_path

        # Bare stem for top-level modules only (e.g., llm_interface, config)
        if len(norm_parts) == 2:
            stem = norm_parts[-1]
            if stem not in index:
                index[stem] = file_path

    return index


def _resolve_import(import_name: str, module_index: Dict[str, str]) -> str | None:
    """Resolve an import name to a known project file path (#1197)."""
    if import_name in module_index:
        return module_index[import_name]
    parts = import_name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in module_index:
            return module_index[candidate]
    return None


def _find_cycles_dfs(graph: Dict[str, Set[str]], max_length: int = 5) -> List[Dict]:
    """Find unique cycles in a directed graph using DFS (#1197)."""
    cycles: List[Dict] = []
    seen: Set[tuple] = set()

    def _dfs(start: str, node: str, path: List[str], depth: int):
        if depth > max_length:
            return
        for neighbor in graph.get(node, set()):
            if neighbor == start and len(path) > 1:
                raw = path[:]
                min_i = min(range(len(raw)), key=lambda i: raw[i])
                norm = tuple(raw[min_i:] + raw[:min_i])
                if norm not in seen:
                    seen.add(norm)
                    severity = (
                        "high"
                        if len(path) <= 2
                        else "medium"
                        if len(path) <= 4
                        else "low"
                    )
                    cycle_path = path + [start]
                    cycles.append(
                        {
                            "cycle": cycle_path,
                            "modules": cycle_path,
                            "length": len(path),
                            "severity": severity,
                        }
                    )
                return
            if neighbor not in set(path):
                _dfs(start, neighbor, path + [neighbor], depth + 1)

    for node in graph:
        _dfs(node, node, [node], 0)

    return sorted(cycles, key=lambda c: c["length"])[:50]


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


def _detect_circular_deps(
    runtime_rels: List[Dict], module_index: Dict[str, str]
) -> List[Dict]:
    """Detect circular dependencies with DFS and module resolution (#1197).

    Resolves import targets to file paths using module_index, builds a
    directed graph, and finds all cycles up to length 5.

    Replaces the previous mutual-import-only detection which was broken
    due to source/target namespace mismatch (file paths vs import names).
    """
    graph: Dict[str, Set[str]] = {}
    for rel in runtime_rels:
        source = rel["source"]
        target_path = _resolve_import(rel["target"], module_index)
        if target_path and target_path != source:
            graph.setdefault(source, set()).add(target_path)

    return _find_cycles_dfs(graph, max_length=5)


async def _analyze_file_imports(
    py_file: Path,
    project_root: Path,
    modules: Dict[str, Dict],
    import_relationships: List[Dict],
    external_deps: Dict[str, int],
    runtime_rels: List[Dict],
) -> None:
    """
    Analyze imports from a single Python file and update data structures.

    Issue #281: Extracted helper for file import analysis.
    Issue #1197: Also collects runtime-only imports for circular detection.

    Args:
        py_file: Python file to analyze
        project_root: Root directory of the project
        modules: Dict to update with module info
        import_relationships: List to update with import relationships
        external_deps: Dict to update with external dependency counts
        runtime_rels: List to update with runtime-only import edges
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

    # Create import relationships for graph visualization
    for imp in file_imports:
        import_relationships.append(
            {"source": rel_path, "target": imp, "type": "import"}
        )

    # Runtime-only imports for circular detection (#1197)
    for imp in _extract_runtime_imports(tree):
        runtime_rels.append({"source": rel_path, "target": imp})


def _build_visualization_graph(
    modules: Dict[str, Dict],
    import_relationships: List[Dict],
    external_deps: Dict[str, int],
    circular_deps: List[Dict],
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


async def _load_modules_from_chromadb(
    code_collection,
    modules: Dict[str, Dict],
) -> None:
    """Helper for get_dependencies. Load module map from ChromaDB. Ref: #1088."""
    try:
        results = code_collection.get(
            where={"type": {"$in": ["function", "class"]}}, include=["metadatas"]
        )
        seen_files: set = set()
        for metadata in results.get("metadatas", []):
            _process_chromadb_metadata(metadata, modules, seen_files)
        logger.info("Found %s modules in ChromaDB", len(modules))
    except Exception as chroma_error:
        logger.warning("ChromaDB query failed: %s", chroma_error)


async def _scan_filesystem_imports(
    project_root,
    modules: Dict[str, Dict],
    import_relationships: List[Dict],
    external_deps: Dict[str, int],
    runtime_rels: List[Dict],
) -> None:
    """Helper for get_dependencies. Scan filesystem Python files for imports.

    Ref: #1088. Issue #1197: also collects runtime_rels for circular detection.
    """
    # Issue #358 - avoid blocking (use lambda to defer rglob to thread)
    python_files = await asyncio.to_thread(lambda: list(project_root.rglob("*.py")))
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
    # Prioritize source directories over infrastructure/tooling (#1197)
    _priority = {"autobot-backend", "autobot-shared"}
    python_files.sort(key=lambda f: 0 if _priority & set(f.parts) else 1)
    for py_file in python_files[:1500]:  # Cover all backend+shared files
        await _analyze_file_imports(
            py_file,
            project_root,
            modules,
            import_relationships,
            external_deps,
            runtime_rels,
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

    Issue #281: Refactored from 146 lines to use extracted helper methods.
    Issue #1088: Further refactored with _load_modules_from_chromadb and
    _scan_filesystem_imports helpers.

    Returns:
    - modules: List of all modules/files in the codebase
    - imports: Import relationships (which file imports what)
    - dependency_graph: Graph structure for visualization
    - circular_dependencies: Detected circular import issues
    - external_dependencies: Third-party package dependencies
    """
    code_collection = get_code_collection()
    modules: Dict[str, Dict] = {}
    import_relationships: List[Dict] = []
    external_deps: Dict[str, int] = {}
    runtime_rels: List[Dict] = []

    if code_collection:
        await _load_modules_from_chromadb(code_collection, modules)

    project_root = get_project_root()
    await _scan_filesystem_imports(
        project_root,
        modules,
        import_relationships,
        external_deps,
        runtime_rels,
    )

    # Build module index and detect circular imports (#1197)
    module_index = _build_module_index(modules)
    circular_deps = _detect_circular_deps(runtime_rels, module_index)
    return JSONResponse(
        _build_visualization_graph(
            modules, import_relationships, external_deps, circular_deps
        )
    )
