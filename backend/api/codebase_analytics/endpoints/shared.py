# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared utilities and constants for codebase analytics endpoints
"""

import logging
from pathlib import Path

# Logger
logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for internal modules (Issue #326)
INTERNAL_MODULE_PREFIXES = {"src", "backend", "autobot"}

# In-memory storage fallback
_in_memory_storage = {}

# Standard library modules (used by multiple endpoints)
STDLIB_MODULES = {
    "os", "sys", "re", "json", "time", "datetime", "logging", "asyncio",
    "pathlib", "typing", "collections", "functools", "itertools", "subprocess",
    "threading", "multiprocessing", "uuid", "hashlib", "base64", "io",
    "contextlib", "abc", "dataclasses", "enum", "copy", "math", "random",
    "socket", "http", "urllib", "traceback", "inspect", "ast", "shutil",
    "tempfile", "warnings", "signal", "argparse", "pickle", "csv", "sqlite3",
    "email", "html", "xml", "struct", "array", "queue", "heapq", "bisect",
    "weakref", "types", "operator", "string", "textwrap", "codecs",
}


# Common third-party packages to exclude from resolution (Issue #713)
COMMON_THIRD_PARTY = {
    "fastapi", "pydantic", "redis", "aiofiles", "aiohttp", "requests",
    "numpy", "pandas", "sqlalchemy", "alembic", "pytest", "httpx",
    "celery", "chromadb", "openai", "anthropic", "langchain", "torch",
    "transformers", "PIL", "cv2", "sklearn", "scipy", "matplotlib",
    "websockets", "uvicorn", "starlette", "jinja2", "click", "rich",
    "yaml", "toml", "dotenv", "paramiko", "fabric", "boto3", "google",
    "azure", "docker", "kubernetes", "jwt", "cryptography", "bcrypt",
}


# Project root helper
def get_project_root() -> Path:
    """
    Get the project root directory (4 levels up from this file).

    Returns:
        Path: Project root directory
    """
    return Path(__file__).resolve().parents[4]


# =============================================================================
# Import Context Utilities (Issue #713)
# =============================================================================


class ImportContext:
    """
    Tracks import context for a single file to enable cross-module resolution.

    Issue #713: Extracted from import_tree.py logic to share with call_graph.py.

    Attributes:
        name_to_module: Maps imported names to their source module paths
        module_to_names: Maps module paths to list of imported names
        aliases: Maps alias names to original names
    """

    def __init__(self):
        """Initialize empty import context."""
        self.name_to_module: dict[str, str] = {}
        self.module_to_names: dict[str, list[str]] = {}
        self.aliases: dict[str, str] = {}

    def add_import(self, module: str, name: str | None = None, alias: str | None = None):
        """
        Register an import statement.

        Args:
            module: The module being imported (e.g., 'src.utils.redis_client')
            name: Specific name imported (e.g., 'get_redis_client') or None for module import
            alias: Alias if any (e.g., 'redis' for 'import redis_client as redis')
        """
        if name:
            # from module import name [as alias]
            effective_name = alias if alias else name
            full_path = f"{module}.{name}"
            self.name_to_module[effective_name] = full_path
            if alias:
                self.aliases[alias] = name
        else:
            # import module [as alias]
            effective_name = alias if alias else module.split(".")[-1]
            self.name_to_module[effective_name] = module
            if alias:
                self.aliases[alias] = module

        if module not in self.module_to_names:
            self.module_to_names[module] = []
        if name and name not in self.module_to_names[module]:
            self.module_to_names[module].append(name)

    def resolve_name(self, name: str) -> str | None:
        """
        Resolve a called name to its full module path.

        Args:
            name: The name being called (e.g., 'get_redis_client')

        Returns:
            Full module path if found (e.g., 'src.utils.redis_client.get_redis_client')
            or None if not in imports
        """
        return self.name_to_module.get(name)

    def is_external(self, name: str) -> bool:
        """
        Check if a name refers to an external (non-project) import.

        Args:
            name: The name to check

        Returns:
            True if the name is from stdlib or third-party package
        """
        module_path = self.name_to_module.get(name)
        if not module_path:
            return False

        base_module = module_path.split(".")[0]
        return base_module in STDLIB_MODULES or base_module in COMMON_THIRD_PARTY


def is_external_module(module_name: str) -> bool:
    """
    Check if a module is external (stdlib or third-party).

    Issue #713: Used to filter external calls from unresolved count.

    Args:
        module_name: Module name or path to check

    Returns:
        True if external, False if internal project module
    """
    base = module_name.split(".")[0]
    if base in STDLIB_MODULES or base in COMMON_THIRD_PARTY:
        return True
    if base in INTERNAL_MODULE_PREFIXES:
        return False
    # Unknown - assume external if not matching internal prefixes
    return True
