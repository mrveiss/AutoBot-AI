# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dependency Tracker Service (Issue #907)

Tracks imports and dependencies for completion suggestions.
"""

import ast
import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class DependencyTracker:
    """
    Tracks import statements and module dependencies.

    Detects missing imports, tracks aliases, and suggests
    frequently co-imported modules.
    """

    def __init__(self):
        self.imports: List[str] = []
        self.import_aliases: Dict[str, str] = {}
        self.used_names: Set[str] = set()

    def extract_imports(self, tree: ast.AST) -> List[str]:
        """
        Extract all import statements from AST.

        Args:
            tree: Python AST

        Returns:
            List of import statements as strings
        """
        imports: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_stmt = f"import {alias.name}"
                    if alias.asname:
                        import_stmt += f" as {alias.asname}"
                        self.import_aliases[alias.asname] = alias.name
                    imports.append(import_stmt)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    import_stmt = f"from {module} import {alias.name}"
                    if alias.asname:
                        import_stmt += f" as {alias.asname}"
                        self.import_aliases[alias.asname] = f"{module}.{alias.name}"
                    imports.append(import_stmt)

        self.imports = imports
        return imports

    def extract_used_names(self, tree: ast.AST) -> Set[str]:
        """
        Extract all names used in code.

        Args:
            tree: Python AST

        Returns:
            Set of name identifiers
        """
        used: Set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                # Track attribute access like redis_client.get()
                if isinstance(node.value, ast.Name):
                    used.add(node.value.id)

        self.used_names = used
        return used

    def detect_missing_imports(self, tree: ast.AST) -> List[str]:
        """
        Detect names used but not imported.

        Args:
            tree: Python AST

        Returns:
            List of potentially missing import names
        """
        # Extract defined names (functions, classes, variables)
        defined_names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                defined_names.add(node.name)
            elif isinstance(node, ast.ClassDef):
                defined_names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_names.add(target.id)

        # Extract imported names
        imported_names: Set[str] = set()
        for imp in self.imports:
            # Simple heuristic: extract last part of import
            parts = imp.split()
            if "import" in parts:
                idx = parts.index("import")
                if idx + 1 < len(parts):
                    name = parts[idx + 1].split(".")[0]
                    imported_names.add(name)

        # Find used but not imported/defined
        used_names = self.extract_used_names(tree)
        missing = used_names - defined_names - imported_names

        # Filter out builtins
        builtins = {
            "print",
            "len",
            "str",
            "int",
            "float",
            "list",
            "dict",
            "set",
            "tuple",
            "True",
            "False",
            "None",
        }
        missing -= builtins

        return list(missing)

    def suggest_co_imports(self, current_imports: List[str]) -> List[str]:
        """
        Suggest frequently co-imported modules.

        Args:
            current_imports: Currently imported modules

        Returns:
            List of suggested additional imports
        """
        suggestions: List[str] = []

        # FastAPI ecosystem
        if any("fastapi" in imp for imp in current_imports):
            if not any("pydantic" in imp for imp in current_imports):
                suggestions.append("from pydantic import BaseModel")
            if not any("HTTPException" in imp for imp in current_imports):
                suggestions.append("from fastapi import HTTPException")

        # SQLAlchemy ecosystem
        if any("sqlalchemy" in imp for imp in current_imports):
            if not any("Session" in imp for imp in current_imports):
                suggestions.append("from sqlalchemy.orm import Session")

        # Async ecosystem
        if any("asyncio" in imp for imp in current_imports):
            if not any("aiohttp" in imp for imp in current_imports):
                suggestions.append("import aiohttp")

        # Redis ecosystem
        if any("redis" in imp for imp in current_imports):
            if not any("json" in imp for imp in current_imports):
                suggestions.append("import json")

        return suggestions

    def get_import_usage_stats(self, tree: ast.AST) -> Dict[str, int]:
        """
        Count usage frequency of each import.

        Args:
            tree: Python AST

        Returns:
            Dictionary mapping import name to usage count
        """
        usage: Dict[str, int] = {imp: 0 for imp in self.imports}
        used_names = self.extract_used_names(tree)

        for imp in self.imports:
            # Extract import name
            parts = imp.split()
            if "import" in parts:
                idx = parts.index("import")
                if idx + 1 < len(parts):
                    name = parts[idx + 1].split(".")[0]
                    # Count occurrences in used names
                    if name in used_names:
                        usage[imp] = len([n for n in used_names if n == name])

        return usage

    def analyze_dependencies(self, tree: ast.AST):
        """
        Comprehensive dependency analysis.

        Args:
            tree: Python AST

        Returns:
            Dictionary with dependency context
        """
        imports = self.extract_imports(tree)
        missing = self.detect_missing_imports(tree)
        co_imports = self.suggest_co_imports(imports)
        usage_stats = self.get_import_usage_stats(tree)

        return {
            "imports": imports,
            "import_aliases": self.import_aliases,
            "used_imports": [imp for imp, count in usage_stats.items() if count > 0],
            "missing_imports": missing,
            "suggested_co_imports": co_imports,
        }
