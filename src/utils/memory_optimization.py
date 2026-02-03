# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Optimization Utilities for AutoBot
Provides memory usage optimization and monitoring capabilities
"""

import gc
import logging
import os
import sys
import threading
import weakref
from functools import wraps
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union

import psutil

logger = logging.getLogger(__name__)

# Type variable for generic caching
T = TypeVar("T")


class MemoryOptimizedLogging:
    """Memory-efficient logging configuration with rotation"""

    @staticmethod
    def setup_rotating_logger(
        name: str,
        log_file: Union[str, Path],
        level: int = logging.INFO,
        max_bytes: int = int(
            os.getenv("AUTOBOT_LOG_MAX_BYTES", "52428800")
        ),  # 50MB default
        backup_count: int = int(os.getenv("AUTOBOT_LOG_BACKUP_COUNT", "5")),
        console_output: bool = True,
    ) -> logging.Logger:
        """
        Set up a logger with rotating file handler to prevent large log files

        Args:
            name: Logger name
            log_file: Path to log file
            level: Logging level
            max_bytes: Maximum size per log file
            backup_count: Number of backup files to keep
            console_output: Whether to also log to console
        """
        # Create logger
        log = logging.getLogger(name)
        log.setLevel(level)

        # Remove existing handlers to avoid duplicates
        for handler in log.handlers[:]:
            log.removeHandler(handler)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Set up rotating file handler
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)

        # Add console handler if requested
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            log.addHandler(console_handler)

        return log

    @staticmethod
    def setup_timed_rotating_logger(
        name: str,
        log_file: Union[str, Path],
        level: int = logging.INFO,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = int(os.getenv("AUTOBOT_LOG_BACKUP_COUNT", "7")),
        console_output: bool = True,
    ) -> logging.Logger:
        """
        Set up a logger with time-based rotation (daily, hourly, etc.)

        Args:
            name: Logger name
            log_file: Path to log file
            level: Logging level
            when: When to rotate ('midnight', 'H', 'D', etc.)
            interval: Rotation interval
            backup_count: Number of backup files to keep
            console_output: Whether to also log to console
        """
        # Create logger
        log = logging.getLogger(name)
        log.setLevel(level)

        # Remove existing handlers to avoid duplicates
        for handler in log.handlers[:]:
            log.removeHandler(handler)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Set up timed rotating file handler
        file_handler = TimedRotatingFileHandler(
            log_file,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)

        # Add console handler if requested
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            log.addHandler(console_handler)

        return log


class MemoryPool:
    """Object pooling for frequently created/destroyed objects"""

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = int(os.getenv("AUTOBOT_MEMORY_POOL_SIZE", "100")),
    ):
        """Initialize memory pool with object factory and maximum size."""
        self.factory = factory
        self.max_size = max_size
        self._pool: List[T] = []
        self._in_use: Set[int] = set()

    def acquire(self) -> T:
        """Get an object from the pool"""
        if self._pool:
            obj = self._pool.pop()
            self._in_use.add(id(obj))
            return obj
        else:
            obj = self.factory()
            self._in_use.add(id(obj))
            return obj

    def release(self, obj: T) -> None:
        """Return an object to the pool"""
        obj_id = id(obj)
        if obj_id in self._in_use:
            self._in_use.remove(obj_id)
            if len(self._pool) < self.max_size:
                # Reset object state if it has a reset method
                if hasattr(obj, "reset"):
                    obj.reset()
                self._pool.append(obj)

    def clear(self) -> None:
        """Clear the pool"""
        self._pool.clear()
        self._in_use.clear()


class WeakCache:
    """
    Cache using weak references to prevent memory leaks.

    Issue #743: Implements CacheProtocol for CacheCoordinator integration.
    """

    def __init__(
        self,
        maxsize: int = int(os.getenv("AUTOBOT_WEAK_CACHE_SIZE", "128")),
        cache_name: str = "weak_cache",
    ):
        """
        Initialize weak reference cache with maximum size limit.

        Args:
            maxsize: Maximum cache size
            cache_name: Unique cache identifier for CacheProtocol
        """
        self.maxsize = maxsize
        self._name = cache_name
        self._cache: Dict[Any, Any] = {}
        self._weak_refs: Dict[Any, weakref.ReferenceType] = {}
        self._hits = 0
        self._misses = 0

    # CacheProtocol properties - Issue #743
    @property
    def name(self) -> str:
        """Unique cache identifier."""
        return self._name

    @property
    def size(self) -> int:
        """Current number of items in cache."""
        return len(self._cache)

    @property
    def max_size(self) -> int:
        """Maximum capacity."""
        return self.maxsize

    def get(self, key: Any) -> Optional[Any]:
        """Get value from cache"""
        if key in self._weak_refs:
            ref = self._weak_refs[key]
            value = ref()
            if value is not None:
                self._hits += 1
                return value
            else:
                # Reference died, clean up
                del self._weak_refs[key]
                if key in self._cache:
                    del self._cache[key]
        self._misses += 1
        return None

    def set(self, key: Any, value: Any) -> None:
        """Set value in cache with weak reference"""
        if len(self._cache) >= self.maxsize:
            # Remove oldest entry
            oldest_key = next(iter(self._cache))
            self.remove(oldest_key)

        def cleanup(ref):
            """Remove cache entry when weak reference is garbage collected."""
            if key in self._weak_refs and self._weak_refs[key] is ref:
                del self._weak_refs[key]
                if key in self._cache:
                    del self._cache[key]

        self._cache[key] = value
        self._weak_refs[key] = weakref.ref(value, cleanup)

    def remove(self, key: Any) -> None:
        """Remove entry from cache"""
        if key in self._weak_refs:
            del self._weak_refs[key]
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cache entries (CacheProtocol)."""
        self._cache.clear()
        self._weak_refs.clear()
        self._hits = 0
        self._misses = 0

    def evict(self, count: int) -> int:
        """
        Evict oldest N items from cache (CacheProtocol).

        Issue #743: CacheProtocol method for coordinated eviction.

        Args:
            count: Number of items to evict

        Returns:
            Actual number of items evicted
        """
        evicted = 0
        keys = list(self._cache.keys())
        for key in keys[:count]:
            self.remove(key)
            evicted += 1
        return evicted

    def get_stats(self) -> Dict[str, Any]:
        """
        Return cache statistics (CacheProtocol).

        Issue #743: CacheProtocol method for statistics.
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "name": self.name,
            "size": self.size,
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


def memory_efficient_cache(
    maxsize: int = int(os.getenv("AUTOBOT_CACHE_SIZE", "128")), typed: bool = False
):
    """
    Decorator for memory-efficient caching with weak references

    Args:
        maxsize: Maximum cache size
        typed: Whether to cache based on argument types
    """

    def decorator(func: Callable) -> Callable:
        """Inner decorator that wraps function with memory-efficient caching."""
        cache = WeakCache(maxsize)
        hits = misses = 0

        @wraps(func)
        def wrapper(*args, **kwargs):
            """Wrapper that checks cache before calling function."""
            nonlocal hits, misses

            # Create cache key
            key = (args, tuple(sorted(kwargs.items())))
            if typed:
                key = (key, tuple(type(arg) for arg in args))

            # Try to get from cache
            result = cache.get(key)
            if result is not None:
                hits += 1
                return result

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result)
            misses += 1
            return result

        def cache_info():
            """Return cache statistics as formatted string."""
            return f"hits={hits}, misses={misses}, current_size={len(cache._cache)}"

        def cache_clear():
            """Clear all cached entries and reset hit/miss counters."""
            nonlocal hits, misses
            cache.clear()
            hits = misses = 0

        wrapper.cache_info = cache_info
        wrapper.cache_clear = cache_clear
        return wrapper

    return decorator


class MemoryMonitor:
    """Real-time memory usage monitoring (thread-safe)"""

    def __init__(
        self,
        threshold_mb: float = float(os.getenv("AUTOBOT_MEMORY_THRESHOLD_MB", "500.0")),
    ):
        """Initialize memory monitor with warning threshold in megabytes."""
        self.threshold_mb = threshold_mb
        self.process = psutil.Process()
        self.peak_memory = 0.0
        self.warnings_issued = 0
        self._lock = threading.Lock()  # Lock for thread-safe counter access

    def check_memory(self) -> Dict[str, Any]:
        """Check current memory usage (thread-safe)"""
        memory_info = self.process.memory_info()
        rss_mb = memory_info.rss / (1024**2)
        vms_mb = memory_info.vms / (1024**2)

        # CRITICAL: Protect shared state modifications with lock
        with self._lock:
            # Update peak memory
            if rss_mb > self.peak_memory:
                self.peak_memory = rss_mb

            # Check threshold
            if rss_mb > self.threshold_mb:
                self.warnings_issued += 1
                warning_count = self.warnings_issued
            else:
                warning_count = None

            # Capture current state for return
            peak_mb = self.peak_memory
            warnings = self.warnings_issued

        # Log outside lock to avoid holding lock during I/O
        if warning_count is not None:
            logger.warning(
                f"Memory usage {rss_mb:.1f}MB exceeds threshold {self.threshold_mb}MB "
                f"(warning #{warning_count})"
            )

        return {
            "rss_mb": rss_mb,
            "vms_mb": vms_mb,
            "peak_mb": peak_mb,
            "threshold_mb": self.threshold_mb,
            "above_threshold": rss_mb > self.threshold_mb,
            "warnings_issued": warnings,
        }

    def force_garbage_collection(self) -> Dict[str, int]:
        """Force garbage collection and return stats"""
        before_objects = len(gc.get_objects())
        collected = gc.collect()
        after_objects = len(gc.get_objects())

        logger.info(
            f"Garbage collection: {collected} objects collected, "
            f"{before_objects - after_objects} objects freed"
        )

        return {
            "collected": collected,
            "objects_before": before_objects,
            "objects_after": after_objects,
            "objects_freed": before_objects - after_objects,
        }


class SlottedClass:
    """Base class using __slots__ for memory efficiency"""

    __slots__ = ()

    def __repr__(self):
        """Return string representation with all slot attribute values."""
        attrs = []
        for slot in self.__slots__:
            if hasattr(self, slot):
                attrs.append(f"{slot}={getattr(self, slot)!r}")
        return f"{self.__class__.__name__}({', '.join(attrs)})"


def optimize_memory_usage():
    """Apply global memory optimizations"""
    logger.info("🔧 Applying memory optimizations...")

    # Force garbage collection
    collected = gc.collect()
    logger.info("Garbage collection freed %s objects", collected)

    # Configure garbage collection thresholds for better performance
    # (threshold0, threshold1, threshold2)
    # More aggressive collection for generation 0 (short-lived objects)
    gc_threshold0 = int(os.getenv("AUTOBOT_GC_THRESHOLD_0", "700"))
    gc_threshold1 = int(os.getenv("AUTOBOT_GC_THRESHOLD_1", "10"))
    gc_threshold2 = int(os.getenv("AUTOBOT_GC_THRESHOLD_2", "10"))
    gc.set_threshold(gc_threshold0, gc_threshold1, gc_threshold2)

    # Log current object counts
    object_counts = {}
    for obj in gc.get_objects():
        obj_type = type(obj).__name__
        object_counts[obj_type] = object_counts.get(obj_type, 0) + 1

    total_objects = len(gc.get_objects())
    logger.info("Current object count: %s total objects", f"{total_objects:,}")

    # Log top 5 object types
    top_objects = sorted(object_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for obj_type, count in top_objects:
        logger.info("  %s: %s instances", obj_type, f"{count:,}")

    return {
        "objects_collected": collected,
        "total_objects": total_objects,
        "top_object_types": dict(top_objects),
    }


def memory_usage_decorator(func: Callable) -> Callable:
    """Decorator to monitor memory usage of function calls"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        """Wrapper that measures memory before and after function execution."""
        process = psutil.Process()

        # Memory before
        mem_before = process.memory_info().rss / (1024**2)

        try:
            result = func(*args, **kwargs)
            return result
        finally:
            # Memory after
            mem_after = process.memory_info().rss / (1024**2)
            mem_diff = mem_after - mem_before

            memory_log_threshold = float(
                os.getenv("AUTOBOT_MEMORY_LOG_THRESHOLD_MB", "1.0")
            )
            if abs(mem_diff) > memory_log_threshold:  # Log if change > threshold MB
                logger.debug(
                    f"{func.__name__} memory usage: "
                    f"{mem_before:.1f}MB → {mem_after:.1f}MB "
                    f"({mem_diff:+.1f}MB)"
                )

    return wrapper


# Global memory monitor instance (thread-safe)
_memory_monitor = None
_memory_monitor_lock = threading.Lock()


def get_memory_monitor(
    threshold_mb: float = float(os.getenv("AUTOBOT_MEMORY_THRESHOLD_MB", "500.0"))
) -> MemoryMonitor:
    """Get global memory monitor instance (thread-safe)"""
    global _memory_monitor
    if _memory_monitor is None:
        with _memory_monitor_lock:
            # Double-check after acquiring lock
            if _memory_monitor is None:
                _memory_monitor = MemoryMonitor(threshold_mb)
    return _memory_monitor


# Export commonly used functions
__all__ = [
    "MemoryOptimizedLogging",
    "MemoryPool",
    "WeakCache",
    "memory_efficient_cache",
    "MemoryMonitor",
    "SlottedClass",
    "optimize_memory_usage",
    "memory_usage_decorator",
    "get_memory_monitor",
]
