# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Import tree visualization endpoints
"""

import ast
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiofiles
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from .shared import INTERNAL_MODULE_PREFIXES, STDLIB_MODULES, get_project_root

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_module_to_file_mapping(
    python_files: List[Path], project_root: Path
) -> Dict[str, str]:
    """Build module path to file path mapping (Issue #315)."""
    module_to_file: Dict[str, str] = {}

    for py_file in python_files[:500]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            module_path = rel_path.replace("/", ".").replace(".py", "")
            module_to_file[module_path] = rel_path

            # Also map shorter versions
            parts = module_path.split(".")
            for i in range(len(parts)):
                short_module = ".".join(parts[i:])
                if short_module not in module_to_file:
                    module_to_file[short_module] = rel_path
        except Exception:
            continue

    return module_to_file


def _process_import_node(
    module_name: str, module_to_file: Dict[str, str]
) -> Tuple[Dict, Optional[str]]:
    """Process a single import and return import info and target file (Issue #315)."""
    base_module = module_name.split(".")[0]
    is_external = (
        base_module in STDLIB_MODULES or base_module not in INTERNAL_MODULE_PREFIXES
    )
    target_file = module_to_file.get(module_name)

    import_info = {
        "module": module_name,
        "file": target_file,
        "is_external": is_external and target_file is None,
    }
    return import_info, target_file


def _add_imported_by_relation(
    file_imported_by: Dict[str, List[Dict]],
    target_file: str,
    source_file: str,
    module_name: str,
) -> None:
    """Add imported_by relationship (Issue #315)."""
    if target_file and target_file != source_file:
        if target_file not in file_imported_by:
            file_imported_by[target_file] = []
        file_imported_by[target_file].append(
            {
                "file": source_file,
                "module": module_name,
            }
        )


def _extract_imports_from_ast(
    node: ast.AST,
    module_to_file: Dict[str, str],
    rel_path: str,
    file_imports: Dict[str, List[Dict]],
    file_imported_by: Dict[str, List[Dict]],
) -> None:
    """Extract import info from AST node (Issue #315)."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            import_info, target_file = _process_import_node(alias.name, module_to_file)
            file_imports[rel_path].append(import_info)
            _add_imported_by_relation(
                file_imported_by, target_file, rel_path, alias.name
            )

    elif isinstance(node, ast.ImportFrom) and node.module:
        import_info, target_file = _process_import_node(node.module, module_to_file)
        file_imports[rel_path].append(import_info)
        _add_imported_by_relation(file_imported_by, target_file, rel_path, node.module)


def _deduplicate_imports(imports: List[Dict]) -> List[Dict]:
    """Deduplicate imports by module name (Issue #315)."""
    seen_modules = set()
    unique_imports = []
    for imp in imports:
        if imp["module"] not in seen_modules:
            seen_modules.add(imp["module"])
            unique_imports.append(imp)
    return unique_imports


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
    (Issue #315 - refactored to reduce nesting)
    """
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

    # Data structures
    file_imports: Dict[str, List[Dict]] = {}
    file_imported_by: Dict[str, List[Dict]] = {}

    # Build module to file mapping (Issue #315 - extracted)
    module_to_file = _build_module_to_file_mapping(python_files, project_root)

    # Analyze imports (Issue #315 - simplified loop)
    for py_file in python_files[:500]:
        await _analyze_file_imports(
            py_file, project_root, module_to_file, file_imports, file_imported_by
        )

    # Build result with bidirectional relationships
    import_tree = _build_import_tree(file_imports, file_imported_by)

    return JSONResponse(
        {
            "status": "success",
            "import_tree": import_tree,
            "summary": _build_summary(import_tree),
        }
    )


async def _analyze_file_imports(
    py_file: Path,
    project_root: Path,
    module_to_file: Dict[str, str],
    file_imports: Dict[str, List[Dict]],
    file_imported_by: Dict[str, List[Dict]],
) -> None:
    """Analyze imports for a single file (Issue #315)."""
    try:
        rel_path = str(py_file.relative_to(project_root))
        file_imports[rel_path] = []

        try:
            async with aiofiles.open(py_file, "r", encoding="utf-8") as f:
                content = await f.read()
        except OSError as e:
            logger.debug("Failed to read file for import analysis %s: %s", py_file, e)
            return

        tree = ast.parse(content)

        for node in ast.walk(tree):
            _extract_imports_from_ast(
                node, module_to_file, rel_path, file_imports, file_imported_by
            )

    except Exception as e:
        logger.debug("Could not analyze %s: %s", py_file, e)


def _build_import_tree(
    file_imports: Dict[str, List[Dict]],
    file_imported_by: Dict[str, List[Dict]],
) -> List[Dict]:
    """Build import tree from collected data (Issue #315)."""
    import_tree = []
    all_files = set(file_imports.keys()) | set(file_imported_by.keys())

    for file_path in sorted(all_files):
        imports = file_imports.get(file_path, [])
        unique_imports = _deduplicate_imports(imports)

        import_tree.append(
            {
                "path": file_path,
                "imports": unique_imports,
                "imported_by": file_imported_by.get(file_path, []),
            }
        )

    # Sort by connectivity (most connected files first)
    import_tree.sort(
        key=lambda x: len(x["imports"]) + len(x["imported_by"]), reverse=True
    )
    return import_tree


def _build_summary(import_tree: List[Dict]) -> Dict:
    """Build summary statistics for import tree (Issue #315)."""
    return {
        "total_files": len(import_tree),
        "total_import_relationships": sum(len(f["imports"]) for f in import_tree),
        "most_imported_files": [
            {"file": f["path"], "count": len(f["imported_by"])}
            for f in sorted(
                import_tree, key=lambda x: len(x["imported_by"]), reverse=True
            )[:10]
        ],
        "most_importing_files": [
            {"file": f["path"], "count": len(f["imports"])}
            for f in sorted(import_tree, key=lambda x: len(x["imports"]), reverse=True)[
                :10
            ]
        ],
    }
