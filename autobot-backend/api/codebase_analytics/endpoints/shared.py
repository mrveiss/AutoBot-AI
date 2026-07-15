# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared utilities and constants for codebase analytics endpoints
"""

from pathlib import Path

from autobot_shared.logging_manager import get_logger

# Logger
logger = get_logger(__name__)

# Performance optimization: O(1) lookup for internal modules (Issue #326)
INTERNAL_MODULE_PREFIXES = {
    "a2a",
    "agents",
    "api",
    "autobot",
    "autobot_shared",
    "backend",
    "cache",
    "chat_workflow",
    "config",
    "constants",
    "database",
    "extensions",
    "initialization",
    "knowledge",
    "models",
    "orchestration",
    "routers",
    "security",
    "services",
    "src",
    "utils",
}

# In-memory storage fallback
_in_memory_storage = {}

# Standard library modules (used by multiple endpoints)
STDLIB_MODULES = {
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
    "argparse",
    "pickle",
    "csv",
    "sqlite3",
    "email",
    "html",
    "xml",
    "struct",
    "array",
    "queue",
    "heapq",
    "bisect",
    "weakref",
    "types",
    "operator",
    "string",
    "textwrap",
    "codecs",
}


# Common third-party packages to exclude from resolution (Issue #713)
COMMON_THIRD_PARTY = {
    "fastapi",
    "pydantic",
    "redis",
    "aiofiles",
    "aiohttp",
    "requests",
    "numpy",
    "pandas",
    "sqlalchemy",
    "alembic",
    "pytest",
    "httpx",
    "celery",
    "chromadb",
    "openai",
    "anthropic",
    "langchain",
    "torch",
    "transformers",
    "PIL",
    "cv2",
    "sklearn",
    "scipy",
    "matplotlib",
    "websockets",
    "uvicorn",
    "starlette",
    "jinja2",
    "click",
    "rich",
    "yaml",
    "toml",
    "dotenv",
    "paramiko",
    "fabric",
    "boto3",
    "google",
    "azure",
    "docker",
    "kubernetes",
    "jwt",
    "cryptography",
    "bcrypt",
}


async def resolve_source_root(source_id: "str | None") -> "Path | None":
    """Resolve the filesystem root for a given source ID.

    Issue #2760: Extracted from duplicated blocks in report.py and stats.py.
    Both endpoints contained identical 10-line blocks; this single helper
    replaces both.

    Args:
        source_id: The source identifier to look up, or None.

    Returns:
        Path to the source clone directory, or None if unresolvable.
    """
    if not source_id:
        return None
    try:
        from api.codebase_analytics.source_storage import get_source

        source = await get_source(source_id)
        if source and source.clone_path:
            return Path(source.clone_path)
    except Exception as exc:
        logger.debug("Could not resolve source root for %s: %s", source_id, exc)
    return None


# Project root helper
def get_project_root() -> Path:
    """
    Get the project root directory (4 levels up from this file).

    Returns:
        Path: Project root directory
    """
    return Path(__file__).resolve().parents[4]


def resolve_project_root() -> str:
    """
    Resolve the real git repository root robustly for dev and deployed layouts.

    Issue #10730: In the deployed layout autobot-backend is a standalone rsync
    dir under /opt/autobot, so ``parents[4]`` resolves to /opt/autobot which is
    NOT a git repo.  The actual repository lives in the sibling code_source dir.

    Strategy (first match wins):
    1. Walk up from this file looking for a directory containing `.git`.
    2. If no git repo found walking up, look for a sibling/child ``code_source``
       directory that itself contains ``.git`` (deployed layout).
    3. Fall back to ``parents[4]`` so dev checkouts keep working unchanged.

    Returns:
        str: Absolute path to the resolved project root.
    """
    current = Path(__file__).resolve()

    # Walk up the directory tree looking for a .git entry
    for parent in current.parents:
        if (parent / ".git").exists():
            logger.debug("resolve_project_root: found git root via walk-up: %s", parent)
            return str(parent)

    # No .git found walking up — check for deployed-layout sibling code_source
    # The walk exhausted all parents; the last ``parent`` is the filesystem root.
    # Re-anchor from the hard-coded parents[4] candidate and look around it.
    candidate = Path(__file__).resolve().parents[4]
    for probe in (
        candidate / "code_source",  # /opt/autobot/code_source
        candidate.parent / "code_source",  # one level higher, just in case
    ):
        if (probe / ".git").exists():
            logger.debug("resolve_project_root: found git root via code_source probe: %s", probe)
            return str(probe)

    # Final fallback: original parents[4] (works in dev checkout)
    logger.debug("resolve_project_root: falling back to parents[4]: %s", candidate)
    return str(candidate)


def filter_problems_by_file_existence(
    problems: list[dict],
    root_path: "Path | str | None" = None,
) -> list[dict]:
    """
    Filter LLM-indexed problems to only those whose file_path exists on disk.

    Issue #2724: The analytics problems scanner can produce findings that
    reference file paths that do not exist in the indexed repository (hallucinated
    paths from LLM analysis).  This validator resolves each relative file_path
    against root_path and drops any finding whose path cannot be confirmed on
    disk.  Validated findings receive ``file_verified: True`` so callers can
    distinguish them from raw, unvalidated data.

    Args:
        problems: List of problem dicts as returned by ChromaDB queries.
                  Each dict may contain a ``file_path`` key with a relative
                  path string.
        root_path: Absolute base directory to resolve relative paths against.
                   Defaults to the project root when None or empty.

    Returns:
        Filtered list containing only problems whose file_path exists.
        Each retained problem gains ``file_verified: True``.
    """
    if not problems:
        return problems

    base = Path(root_path) if root_path else get_project_root()

    validated: list[dict] = []
    dropped = 0

    for problem in problems:
        fp = problem.get("file_path", "")
        if not fp:
            # No file_path — keep as-is (cannot validate)
            validated.append({**problem, "file_verified": False})
            continue

        full_path = (base / fp).resolve()
        if not full_path.is_relative_to(base.resolve()):
            dropped += 1
            logger.debug(
                "Dropping problem with path traversal outside root: %s (resolved: %s)",
                fp,
                full_path,
            )
            continue
        if full_path.exists():
            validated.append({**problem, "file_verified": True})
        else:
            dropped += 1
            logger.debug(
                "Dropping problem with non-existent file path: %s (resolved: %s)",
                fp,
                full_path,
            )

    if dropped:
        logger.info(
            "File path validation: dropped %d/%d problems with non-existent paths (#2724)",
            dropped,
            len(problems),
        )

    return validated


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
