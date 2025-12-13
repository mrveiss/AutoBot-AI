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


# Project root helper
def get_project_root() -> Path:
    """
    Get the project root directory (4 levels up from this file).

    Returns:
        Path: Project root directory
    """
    return Path(__file__).resolve().parents[4]
