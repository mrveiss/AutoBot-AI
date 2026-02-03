# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AST Cache for Code Intelligence Analyzers

Issue #607: Provides centralized AST parsing with caching to eliminate
redundant parsing of the same Python files across multiple analyzers.

Problem solved:
    - 5-10 analyzers each parse the same Python files independently
    - Each parse takes 5-50ms depending on file size
    - Total: Seconds wasted on redundant AST parsing

Solution:
    - Parse each file once, cache the AST
    - Invalidate on file modification (mtime check)
    - LRU eviction to bound memory usage

Usage:
    from src.code_intelligence.shared import get_ast, get_ast_safe

    # Get cached AST (raises on parse error)
    tree = get_ast("/path/to/file.py")

    # Get cached AST (returns None on error)
    tree = get_ast_safe("/path/to/file.py")

    # Force refresh if needed
    invalidate_ast_cache("/path/to/file.py")

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import ast
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Configuration via environment variables
DEFAULT_CACHE_SIZE = int(os.getenv("AST_CACHE_MAX_SIZE", "1000"))
DEFAULT_CONTENT_CACHE_SIZE = int(os.getenv("CONTENT_CACHE_MAX_SIZE", "500"))


@dataclass
class ASTCacheEntry:
    """Single AST cache entry with metadata."""
    tree: ast.AST
    mtime: float
    file_size: int
    parse_time_ms: float
    access_count: int = 1
    last_access: float = 0

    def __post_init__(self):
        self.last_access = time.time()


@dataclass
class ContentCacheEntry:
    """Single file content cache entry."""
    content: str
    mtime: float
    file_size: int


@dataclass
class ASTCacheStats:
    """Statistics for cache monitoring."""
    hits: int = 0
    misses: int = 0
    parse_errors: int = 0
    evictions: int = 0
    invalidations: int = 0
    total_parse_time_ms: float = 0
    current_size: int = 0
    max_size: int = DEFAULT_CACHE_SIZE

    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        avg_parse_time = (
            self.total_parse_time_ms / self.misses
            if self.misses > 0 else 0
        )
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "parse_errors": self.parse_errors,
            "evictions": self.evictions,
            "invalidations": self.invalidations,
            "total_parse_time_ms": round(self.total_parse_time_ms, 2),
            "avg_parse_time_ms": round(avg_parse_time, 2),
            "current_size": self.current_size,
            "max_size": self.max_size,
        }


class ASTCache:
    """
    Thread-safe AST cache with LRU eviction and mtime-based invalidation.

    Issue #607: Eliminates redundant ast.parse() calls across analyzers.

    Features:
        - LRU eviction when cache is full
        - Automatic invalidation when file mtime changes
        - Thread-safe access
        - Optional content caching for file reads

    Thread Safety:
        Uses threading.Lock for thread-safe cache access.
        Safe to use from multiple async tasks and threads.
    """

    _instance: Optional["ASTCache"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ASTCache":
        """Singleton pattern for global cache instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        max_size: int = DEFAULT_CACHE_SIZE,
        content_cache_size: int = DEFAULT_CONTENT_CACHE_SIZE,
    ):
        """Initialize cache (only runs once due to singleton)."""
        if self._initialized:
            return

        self._max_size = max_size
        self._content_cache_size = content_cache_size

        # LRU cache using OrderedDict
        self._ast_cache: OrderedDict[str, ASTCacheEntry] = OrderedDict()
        self._content_cache: OrderedDict[str, ContentCacheEntry] = OrderedDict()

        self._stats = ASTCacheStats(max_size=max_size)
        self._cache_lock = threading.Lock()
        self._initialized = True

        logger.info(
            "ASTCache initialized: max_size=%d, content_cache_size=%d",
            self._max_size, self._content_cache_size
        )

    def _get_file_mtime(self, file_path: str) -> float:
        """Get file modification time, returns 0 on error."""
        try:
            return os.path.getmtime(file_path)
        except OSError:
            return 0

    def _get_file_size(self, file_path: str) -> int:
        """Get file size in bytes, returns 0 on error."""
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0

    def _evict_lru(self) -> None:
        """Evict least recently used entry (must hold lock)."""
        if self._ast_cache:
            oldest_key = next(iter(self._ast_cache))
            del self._ast_cache[oldest_key]
            self._stats.evictions += 1
            logger.debug("ASTCache: Evicted LRU entry: %s", oldest_key)

    def _read_file_content(self, file_path: str) -> str:
        """
        Read file content with optional caching.

        Uses content cache to avoid redundant file reads when
        multiple operations need the same file content.
        """
        mtime = self._get_file_mtime(file_path)

        with self._cache_lock:
            if file_path in self._content_cache:
                entry = self._content_cache[file_path]
                if entry.mtime == mtime:
                    # Move to end (most recently used)
                    self._content_cache.move_to_end(file_path)
                    return entry.content

        # Read file
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Cache content
        with self._cache_lock:
            if len(self._content_cache) >= self._content_cache_size:
                # Evict oldest entry
                oldest_key = next(iter(self._content_cache))
                del self._content_cache[oldest_key]

            self._content_cache[file_path] = ContentCacheEntry(
                content=content,
                mtime=mtime,
                file_size=len(content),
            )
            self._content_cache.move_to_end(file_path)

        return content

    def get(self, file_path: Union[str, Path]) -> ast.AST:
        """
        Get AST for file, using cache if available.

        Args:
            file_path: Path to Python file

        Returns:
            Parsed AST module

        Raises:
            FileNotFoundError: If file doesn't exist
            SyntaxError: If file has syntax errors
        """
        path_str = str(file_path)
        mtime = self._get_file_mtime(path_str)

        with self._cache_lock:
            if path_str in self._ast_cache:
                entry = self._ast_cache[path_str]
                if entry.mtime == mtime:
                    # Cache hit - update access info and move to end
                    entry.access_count += 1
                    entry.last_access = time.time()
                    self._ast_cache.move_to_end(path_str)
                    self._stats.hits += 1
                    logger.debug("ASTCache HIT: %s", path_str)
                    return entry.tree
                else:
                    # File modified - remove stale entry
                    del self._ast_cache[path_str]
                    self._stats.invalidations += 1
                    logger.debug("ASTCache STALE: %s (mtime changed)", path_str)

            self._stats.misses += 1

        # Cache miss - parse file
        logger.debug("ASTCache MISS: %s", path_str)

        try:
            start_time = time.time()
            content = self._read_file_content(path_str)
            tree = ast.parse(content, filename=path_str)
            parse_time_ms = (time.time() - start_time) * 1000

            with self._cache_lock:
                # Evict if needed
                while len(self._ast_cache) >= self._max_size:
                    self._evict_lru()

                self._ast_cache[path_str] = ASTCacheEntry(
                    tree=tree,
                    mtime=mtime,
                    file_size=len(content),
                    parse_time_ms=parse_time_ms,
                )
                self._ast_cache.move_to_end(path_str)
                self._stats.total_parse_time_ms += parse_time_ms
                self._stats.current_size = len(self._ast_cache)

            logger.debug(
                "ASTCache: Parsed %s in %.1fms",
                path_str, parse_time_ms
            )
            return tree

        except SyntaxError as e:
            self._stats.parse_errors += 1
            logger.warning("ASTCache: Syntax error in %s: %s", path_str, e)
            raise

        except FileNotFoundError:
            logger.warning("ASTCache: File not found: %s", path_str)
            raise

    def get_safe(self, file_path: Union[str, Path]) -> Optional[ast.AST]:
        """
        Get AST for file, returning None on any error.

        Args:
            file_path: Path to Python file

        Returns:
            Parsed AST module, or None if parsing failed
        """
        try:
            return self.get(file_path)
        except (SyntaxError, FileNotFoundError, OSError) as e:
            logger.debug("ASTCache: get_safe failed for %s: %s", file_path, e)
            return None

    def get_with_content(
        self, file_path: Union[str, Path]
    ) -> Tuple[Optional[ast.AST], str]:
        """
        Get AST and file content together.

        Useful when analyzer needs both AST and raw content.

        Returns:
            Tuple of (ast, content) - ast may be None on parse error
        """
        path_str = str(file_path)
        try:
            content = self._read_file_content(path_str)
            tree = self.get(file_path)
            return tree, content
        except (SyntaxError, FileNotFoundError, OSError):
            try:
                content = self._read_file_content(path_str)
                return None, content
            except (FileNotFoundError, OSError):
                return None, ""

    def invalidate(self, file_path: Optional[Union[str, Path]] = None) -> None:
        """
        Invalidate cache entries.

        Args:
            file_path: If provided, only invalidate this file.
                      If None, invalidate all entries.
        """
        with self._cache_lock:
            if file_path is None:
                count = len(self._ast_cache)
                self._ast_cache.clear()
                self._content_cache.clear()
                self._stats.invalidations += count
                self._stats.current_size = 0
                logger.info("ASTCache: All entries invalidated (%d)", count)
            else:
                path_str = str(file_path)
                if path_str in self._ast_cache:
                    del self._ast_cache[path_str]
                    self._stats.invalidations += 1
                    self._stats.current_size = len(self._ast_cache)
                if path_str in self._content_cache:
                    del self._content_cache[path_str]
                logger.debug("ASTCache: Invalidated %s", path_str)

    def get_stats(self) -> ASTCacheStats:
        """Get cache statistics."""
        with self._cache_lock:
            self._stats.current_size = len(self._ast_cache)
        return self._stats

    def get_cached_files(self) -> list:
        """Get list of currently cached file paths."""
        with self._cache_lock:
            return list(self._ast_cache.keys())

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

_cache_instance: Optional[ASTCache] = None
_cache_instance_lock = threading.Lock()


def _get_cache() -> ASTCache:
    """Get or create the global cache instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety while
    minimizing lock contention after initialization (Issue #613).
    """
    global _cache_instance
    if _cache_instance is None:
        with _cache_instance_lock:
            # Double-check after acquiring lock
            if _cache_instance is None:
                _cache_instance = ASTCache()
    return _cache_instance


def get_ast(file_path: Union[str, Path]) -> ast.AST:
    """
    Get AST for Python file, using cache if available.

    Args:
        file_path: Path to Python file

    Returns:
        Parsed AST module

    Raises:
        FileNotFoundError: If file doesn't exist
        SyntaxError: If file has syntax errors

    Example:
        tree = get_ast("/path/to/file.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                logger.info("Found function: %s", node.name)
    """
    return _get_cache().get(file_path)


def get_ast_safe(file_path: Union[str, Path]) -> Optional[ast.AST]:
    """
    Get AST for Python file, returning None on any error.

    Args:
        file_path: Path to Python file

    Returns:
        Parsed AST module, or None if parsing failed

    Example:
        tree = get_ast_safe("/path/to/file.py")
        if tree:
            # Process AST
            pass
    """
    return _get_cache().get_safe(file_path)


def get_ast_with_content(
    file_path: Union[str, Path]
) -> Tuple[Optional[ast.AST], str]:
    """
    Get AST and file content together.

    Returns:
        Tuple of (ast, content) - ast may be None on parse error
    """
    return _get_cache().get_with_content(file_path)


def invalidate_ast_cache(file_path: Optional[Union[str, Path]] = None) -> None:
    """
    Invalidate AST cache entries.

    Args:
        file_path: If provided, only invalidate this file.
                  If None, invalidate all entries.
    """
    _get_cache().invalidate(file_path)


def get_ast_cache_stats() -> Dict:
    """Get AST cache statistics as dictionary."""
    return _get_cache().get_stats().to_dict()
