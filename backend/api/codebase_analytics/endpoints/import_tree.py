# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Import tree visualization endpoints
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List

import aiofiles
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from .shared import get_project_root, STDLIB_MODULES, INTERNAL_MODULE_PREFIXES

logger = logging.getLogger(__name__)

router = APIRouter()


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
                        is_external = base_module in STDLIB_MODULES or base_module not in INTERNAL_MODULE_PREFIXES  # O(1) lookup (Issue #326)
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
                        is_external = base_module in STDLIB_MODULES or base_module not in INTERNAL_MODULE_PREFIXES  # O(1) lookup (Issue #326)
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
