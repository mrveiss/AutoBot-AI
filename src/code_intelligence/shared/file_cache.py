# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
File List Cache for Code Intelligence Analyzers

Issue #607: Provides centralized file discovery with caching to eliminate
redundant filesystem traversals across multiple analyzers.

Problem solved:
    - 10+ analyzers each call rglob("*.py") independently
    - Each traversal takes 100-500ms on large codebases
    - Total: 1-5 seconds wasted on redundant file discovery

Solution:
    - Single traversal, cached with TTL
    - All analyzers share the same file list
    - Automatic invalidation on timeout or explicit call

Usage:
    from src.code_intelligence.shared import get_python_files, get_frontend_files

    # Get cached Python files (fast after first call)
    python_files = await get_python_files()

    # Get cached frontend files
    frontend_files = await get_frontend_files()

    # Force refresh if needed
    invalidate_file_cache()
    python_files = await get_python_files()

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from src.constants.path_constants import PATH
from src.utils.file_categorization import SKIP_DIRS

logger = logging.getLogger(__name__)

# Configuration via environment variables
DEFAULT_CACHE_TTL = int(os.getenv("FILE_CACHE_TTL_SECONDS", "300"))  # 5 minutes
DEFAULT_ROOT_PATH = PATH.PROJECT_ROOT

# File extension sets for different categories
PYTHON_EXTENSIONS: FrozenSet[str] = frozenset({".py"})
TYPESCRIPT_EXTENSIONS: FrozenSet[str] = frozenset({".ts", ".tsx"})
JAVASCRIPT_EXTENSIONS: FrozenSet[str] = frozenset({".js", ".jsx", ".mjs"})
VUE_EXTENSIONS: FrozenSet[str] = frozenset({".vue"})
CSS_EXTENSIONS: FrozenSet[str] = frozenset({".css", ".scss", ".sass", ".less"})
HTML_EXTENSIONS: FrozenSet[str] = frozenset({".html", ".htm"})
CONFIG_EXTENSIONS: FrozenSet[str] = frozenset(
    {".json", ".yaml", ".yml", ".toml", ".ini"}
)
SHELL_EXTENSIONS: FrozenSet[str] = frozenset({".sh", ".bash", ".zsh"})

FRONTEND_EXTENSIONS: FrozenSet[str] = (
    TYPESCRIPT_EXTENSIONS
    | JAVASCRIPT_EXTENSIONS
    | VUE_EXTENSIONS
    | CSS_EXTENSIONS
    | HTML_EXTENSIONS
)

ALL_CODE_EXTENSIONS: FrozenSet[str] = (
    PYTHON_EXTENSIONS | FRONTEND_EXTENSIONS | SHELL_EXTENSIONS
)


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""

    files: List[Path]
    timestamp: float
    root_path: str
    extensions: FrozenSet[str]


@dataclass
class CacheStats:
    """Statistics for cache monitoring."""

    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    total_files_cached: int = 0
    last_refresh_time_ms: float = 0
    last_refresh_timestamp: float = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "invalidations": self.invalidations,
            "total_files_cached": self.total_files_cached,
            "last_refresh_time_ms": round(self.last_refresh_time_ms, 2),
            "last_refresh_timestamp": self.last_refresh_timestamp,
        }


class FileListCache:
    """
    Thread-safe file list cache with TTL-based expiration.

    Issue #607: Eliminates redundant rglob() calls across analyzers.
    Issue #743: Implements CacheProtocol for CacheCoordinator integration.

    Attributes:
        ttl: Cache time-to-live in seconds (default: 300)
        root_path: Root directory for file discovery

    Thread Safety:
        Uses threading.Lock for thread-safe cache access.
        Safe to use from multiple async tasks and threads.
    """

    _instance: Optional["FileListCache"] = None
    _lock = threading.Lock()

    # CacheProtocol properties - Issue #743
    @property
    def name(self) -> str:
        """Unique cache identifier."""
        return "file_list_cache"

    @property
    def size(self) -> int:
        """Current number of cached file lists."""
        with self._cache_lock:
            return len(self._cache)

    @property
    def max_size(self) -> int:
        """Maximum capacity (0 = unlimited, TTL-based expiration)."""
        return 0  # TTL-based, not size-based

    def __new__(cls) -> "FileListCache":
        """Singleton pattern for global cache instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        ttl: int = DEFAULT_CACHE_TTL,
        root_path: Optional[Path] = None,
    ):
        """Initialize cache (only runs once due to singleton)."""
        if self._initialized:
            return

        self._ttl = ttl
        self._root_path = root_path or DEFAULT_ROOT_PATH
        self._cache: Dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        self._cache_lock = threading.Lock()
        self._initialized = True

        logger.info(
            "FileListCache initialized: ttl=%ds, root=%s", self._ttl, self._root_path
        )

    def _make_cache_key(self, extensions: FrozenSet[str], root_path: Path) -> str:
        """Generate cache key from extensions and root path."""
        ext_str = ",".join(sorted(extensions))
        return f"{root_path}:{ext_str}"

    def _is_valid(self, entry: CacheEntry) -> bool:
        """Check if cache entry is still valid."""
        return (time.time() - entry.timestamp) < self._ttl

    def _should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped based on SKIP_DIRS."""
        return any(skip_dir in path.parts for skip_dir in SKIP_DIRS)

    async def _scan_files(
        self,
        extensions: FrozenSet[str],
        root_path: Path,
    ) -> List[Path]:
        """
        Scan filesystem for files matching extensions.

        Runs in thread pool to avoid blocking event loop.
        """
        start_time = time.time()

        def _do_scan() -> List[Path]:
            files = []
            for ext in extensions:
                pattern = f"*{ext}"
                for file_path in root_path.rglob(pattern):
                    if file_path.is_file() and not self._should_skip_path(file_path):
                        files.append(file_path)
            return sorted(files)

        files = await asyncio.to_thread(_do_scan)

        elapsed_ms = (time.time() - start_time) * 1000
        self._stats.last_refresh_time_ms = elapsed_ms
        self._stats.last_refresh_timestamp = time.time()

        logger.debug(
            "FileListCache scan complete: %d files in %.1fms", len(files), elapsed_ms
        )

        return files

    async def get_files(
        self,
        extensions: FrozenSet[str],
        root_path: Optional[Path] = None,
    ) -> List[Path]:
        """
        Get list of files matching extensions, using cache if available.

        Args:
            extensions: Set of file extensions to match (e.g., {".py"})
            root_path: Root directory to search (default: project root)

        Returns:
            List of Path objects for matching files
        """
        root = root_path or self._root_path
        cache_key = self._make_cache_key(extensions, root)

        with self._cache_lock:
            if cache_key in self._cache and self._is_valid(self._cache[cache_key]):
                self._stats.hits += 1
                logger.debug(
                    "FileListCache HIT: %s (%d files)",
                    cache_key,
                    len(self._cache[cache_key].files),
                )
                return self._cache[cache_key].files.copy()

            self._stats.misses += 1

        # Cache miss - scan filesystem
        logger.debug("FileListCache MISS: %s", cache_key)
        files = await self._scan_files(extensions, root)

        with self._cache_lock:
            self._cache[cache_key] = CacheEntry(
                files=files,
                timestamp=time.time(),
                root_path=str(root),
                extensions=extensions,
            )
            self._stats.total_files_cached = sum(
                len(entry.files) for entry in self._cache.values()
            )

        return files.copy()

    def invalidate(self, extensions: Optional[FrozenSet[str]] = None) -> None:
        """
        Invalidate cache entries.

        Args:
            extensions: If provided, only invalidate entries matching these extensions.
                       If None, invalidate all entries.
        """
        with self._cache_lock:
            if extensions is None:
                self._cache.clear()
                self._stats.invalidations += 1
                logger.info("FileListCache: All entries invalidated")
            else:
                keys_to_remove = [
                    key
                    for key, entry in self._cache.items()
                    if entry.extensions == extensions
                ]
                for key in keys_to_remove:
                    del self._cache[key]
                    self._stats.invalidations += 1
                logger.info(
                    "FileListCache: Invalidated %d entries", len(keys_to_remove)
                )

    def get_stats(self) -> Dict:
        """
        Return cache statistics as dict (CacheProtocol).

        Issue #743: Returns Dict for CacheProtocol compliance.
        """
        stats = self._stats.to_dict()
        stats["name"] = self.name
        stats["size"] = self.size
        stats["max_size"] = self.max_size
        return stats

    def evict(self, count: int) -> int:
        """
        Evict oldest N cache entries (CacheProtocol).

        Issue #743: CacheProtocol method for coordinated eviction.
        Note: For TTL-based caches, eviction removes oldest entries.

        Args:
            count: Number of entries to evict

        Returns:
            Actual number of entries evicted
        """
        evicted = 0
        with self._cache_lock:
            # Sort by timestamp (oldest first)
            sorted_keys = sorted(
                self._cache.keys(), key=lambda k: self._cache[k].timestamp
            )
            for key in sorted_keys[:count]:
                del self._cache[key]
                evicted += 1
                self._stats.invalidations += 1
        return evicted

    def clear(self) -> None:
        """
        Clear all items from cache (CacheProtocol).

        Issue #743: CacheProtocol method for cache clearing.
        """
        self.invalidate(None)

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        global _cache_instance
        with cls._lock:
            cls._instance = None
            _cache_instance = None


# =============================================================================
# Convenience Functions (Module-Level API)
# =============================================================================

_cache_instance: Optional[FileListCache] = None
_cache_instance_lock = threading.Lock()


def _get_cache() -> FileListCache:
    """Get or create the global cache instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety while
    minimizing lock contention after initialization (Issue #613).
    """
    global _cache_instance
    if _cache_instance is None:
        with _cache_instance_lock:
            # Double-check after acquiring lock
            if _cache_instance is None:
                _cache_instance = FileListCache()
    return _cache_instance


async def get_python_files(root_path: Optional[Path] = None) -> List[Path]:
    """
    Get list of Python files (.py) in the codebase.

    Args:
        root_path: Root directory to search (default: project root)

    Returns:
        List of Path objects for Python files

    Example:
        python_files = await get_python_files()
        for f in python_files:
            logger.info("Processing: %s", f)
    """
    return await _get_cache().get_files(PYTHON_EXTENSIONS, root_path)


async def get_frontend_files(root_path: Optional[Path] = None) -> List[Path]:
    """
    Get list of frontend files (.ts, .tsx, .js, .jsx, .vue, .css, .html).

    Args:
        root_path: Root directory to search (default: project root)

    Returns:
        List of Path objects for frontend files
    """
    return await _get_cache().get_files(FRONTEND_EXTENSIONS, root_path)


async def get_all_code_files(root_path: Optional[Path] = None) -> List[Path]:
    """
    Get list of all code files (Python + frontend + shell).

    Args:
        root_path: Root directory to search (default: project root)

    Returns:
        List of Path objects for all code files
    """
    return await _get_cache().get_files(ALL_CODE_EXTENSIONS, root_path)


def invalidate_file_cache(extensions: Optional[FrozenSet[str]] = None) -> None:
    """
    Invalidate file list cache.

    Args:
        extensions: If provided, only invalidate entries matching these extensions.
                   If None, invalidate all entries.
    """
    _get_cache().invalidate(extensions)


def get_file_cache_stats() -> Dict:
    """Get file cache statistics as dictionary."""
    return _get_cache().get_stats().to_dict()
