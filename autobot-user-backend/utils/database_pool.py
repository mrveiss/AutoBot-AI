# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Database Connection Pool Manager
Provides connection pooling for SQLite and other databases to improve performance
and prevent N+1 query issues.
"""

import asyncio
import logging
import sqlite3
import threading
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any, Dict

# Import shared database helpers (Issue #292 - Eliminate duplicate code)
from backend.constants.threshold_constants import TimingConstants
from backend.utils.database_helpers import join_results  # noqa: F401 - re-export

logger = logging.getLogger(__name__)


class SQLiteConnectionPool:
    """Thread-safe SQLite connection pool with proper resource management."""

    def __init__(self, db_path: str, pool_size: int = 10, timeout: float = TimingConstants.SHORT_TIMEOUT):
        """
        Initialize SQLite connection pool.

        Args:
            db_path: Path to SQLite database file
            pool_size: Maximum number of connections in pool
            timeout: Timeout for acquiring connection from pool
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._created_connections = 0
        self._stats = {
            "connections_created": 0,
            "connections_reused": 0,
            "pool_exhausted_count": 0,
            "total_wait_time": 0.0,
        }

        # Pre-create some connections
        self._initialize_pool()

    def _initialize_pool(self):
        """Pre-create initial connections for the pool."""
        initial_size = min(3, self.pool_size)  # Start with 3 connections
        for _ in range(initial_size):
            try:
                conn = self._create_connection()
                self._pool.put(conn)
            except Exception as e:
                logger.error("Failed to create initial connection: %s", e)

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with optimized settings."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,  # Allow connection sharing between threads
        )

        # Enable optimizations
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        conn.execute("PRAGMA cache_size=10000")  # Larger cache
        conn.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O

        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys=ON")

        conn.row_factory = sqlite3.Row  # Enable column access by name

        with self._lock:
            self._created_connections += 1
            self._stats["connections_created"] += 1

        logger.debug("Created new SQLite connection #%s", self._created_connections)
        return conn

    def _acquire_connection(self) -> sqlite3.Connection:
        """Acquire a connection from pool or create new one (Issue #315: extracted).

        Returns:
            sqlite3.Connection from pool or newly created

        Raises:
            Exception if unable to get connection
        """
        # Try to get existing connection from pool
        try:
            conn = self._pool.get(timeout=self.timeout)
            with self._lock:
                self._stats["connections_reused"] += 1
            logger.debug("Reused connection from pool")
            return conn
        except Exception:
            pass  # Pool empty, try to create new

        # Pool exhausted, create new connection if under limit
        with self._lock:
            if self._created_connections < self.pool_size:
                return self._create_connection()
            self._stats["pool_exhausted_count"] += 1
            logger.warning("Connection pool exhausted, waiting...")

        # Wait for connection from pool
        return self._pool.get(timeout=self.timeout)

    def _return_connection(self, conn: sqlite3.Connection) -> None:
        """Return connection to pool (Issue #315: extracted).

        Args:
            conn: Connection to return
        """
        try:
            conn.rollback()  # Reset any uncommitted transactions
            self._pool.put(conn)
        except Exception:
            # Pool is full, close connection
            self._close_connection_safely(conn)

    def _close_connection_safely(self, conn: sqlite3.Connection) -> None:
        """Close connection with error handling (Issue #315: extracted)."""
        try:
            conn.close()
        except Exception:
            pass  # Best-effort cleanup

    @contextmanager
    def get_connection(self):
        """
        Get a connection from the pool (context manager, thread-safe).
        Issue #315: Refactored to use helpers for reduced nesting.

        Yields:
            sqlite3.Connection: Database connection
        """
        start_time = datetime.now()
        conn = None

        try:
            conn = self._acquire_connection()

            # Record wait time (thread-safe)
            wait_time = (datetime.now() - start_time).total_seconds()
            with self._lock:
                self._stats["total_wait_time"] += wait_time

            # Test connection is alive
            conn.execute("SELECT 1")

            yield conn

        except Exception as e:
            logger.error("Error with database connection: %s", e)
            # Connection is bad, don't return it to pool
            if conn:
                self._close_connection_safely(conn)
                conn = None
            raise
        finally:
            # Return good connection to pool
            if conn:
                self._return_connection(conn)

    def close_all(self):
        """Close all connections in the pool (thread-safe)."""
        closed = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                closed += 1
            except Exception:
                break

        logger.info("Closed %s connections from pool", closed)
        with self._lock:
            self._created_connections = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get pool usage statistics (thread-safe)."""
        with self._lock:
            stats_copy = dict(self._stats)
            created = self._created_connections

        total_ops = stats_copy["connections_reused"] + stats_copy["connections_created"]
        avg_wait = stats_copy["total_wait_time"] / max(1, total_ops)

        return {
            **stats_copy,
            "current_pool_size": self._pool.qsize(),
            "total_connections_created": created,
            "average_wait_time": avg_wait,
        }


class AsyncSQLiteConnectionPool:
    """Async version of SQLite connection pool using asyncio."""

    def __init__(self, db_path: str, pool_size: int = 10):
        """Initialize async SQLite connection pool."""
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool = asyncio.Queue(maxsize=pool_size)
        self._created_connections = 0
        self._sync_pool = SQLiteConnectionPool(db_path, pool_size)
        self._executor = None

    async def initialize(self):
        """Initialize the async pool."""
        self._executor = asyncio.get_event_loop().run_in_executor

    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the async pool."""
        if not self._executor:
            await self.initialize()

        # Use sync pool in executor
        def _get_conn():
            """Get connection from sync pool within executor context."""
            with self._sync_pool.get_connection() as conn:
                return conn

        # This is a simplified version - in production you'd want
        # a proper async SQLite library like aiosqlite
        conn = await self._executor(None, _get_conn)
        try:
            yield conn
        finally:
            # Return connection to pool handled by sync pool
            pass

    async def close_all(self):
        """Close all connections."""
        await self._executor(None, self._sync_pool.close_all)


# Global connection pools per database
_connection_pools: Dict[str, SQLiteConnectionPool] = {}
_pools_lock = threading.Lock()


def get_connection_pool(db_path: str, pool_size: int = 10) -> SQLiteConnectionPool:
    """
    Get or create a connection pool for a database.

    Args:
        db_path: Path to database file
        pool_size: Maximum pool size

    Returns:
        SQLiteConnectionPool: Connection pool instance
    """
    # Normalize path
    db_path = str(Path(db_path).resolve())

    # Check if pool exists
    if db_path in _connection_pools:
        return _connection_pools[db_path]

    # Create new pool with lock
    with _pools_lock:
        # Double-check after acquiring lock
        if db_path in _connection_pools:
            return _connection_pools[db_path]

        # Create new pool
        pool = SQLiteConnectionPool(db_path, pool_size)
        _connection_pools[db_path] = pool
        logger.info("Created connection pool for %s with size %s", db_path, pool_size)
        return pool


def close_all_pools():
    """Close all connection pools."""
    with _pools_lock:
        for db_path, pool in _connection_pools.items():
            logger.info("Closing pool for %s", db_path)
            pool.close_all()
        _connection_pools.clear()


# N+1 Query Prevention Helpers


class EagerLoader:
    """Helper class to prevent N+1 queries with eager loading patterns."""

    @staticmethod
    def batch_load_related(
        conn: sqlite3.Connection,
        main_query: str,
        main_params: tuple,
        related_queries: Dict[str, tuple],
    ) -> Dict[str, Any]:
        """
        Execute main query and related queries efficiently.

        Args:
            conn: Database connection
            main_query: Main SELECT query
            main_params: Parameters for main query
            related_queries: Dict of {name: (query, params, join_key)}

        Returns:
            Dict with 'main' results and related data
        """
        cursor = conn.cursor()

        # Execute main query
        cursor.execute(main_query, main_params)
        main_results = cursor.fetchall()

        result = {"main": [dict(row) for row in main_results]}

        # Execute related queries
        for name, (query, params, join_key) in related_queries.items():
            cursor.execute(query, params)
            related_results = cursor.fetchall()

            # Group by join key for efficient lookup
            grouped = {}
            for row in related_results:
                key = row[join_key]
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(dict(row))

            result[name] = grouped

        return result

    # join_results moved to src/utils/database_helpers.py (Issue #292)
    # Re-exported at module level for backward compatibility


# Example usage for knowledge base optimization
def optimize_knowledge_base_queries():
    """Example of optimizing knowledge base queries to prevent N+1."""
    db_path = "data/knowledge_base.db"
    pool = get_connection_pool(db_path)

    with pool.get_connection() as conn:
        # Instead of N+1 pattern:
        # for entry in entries:
        #     tags = conn.execute("SELECT * FROM tags WHERE entry_id = ?", (entry['id'],))

        # Use batch loading:
        eager_loader = EagerLoader()
        results = eager_loader.batch_load_related(
            conn,
            "SELECT * FROM entries WHERE category = ?",
            ("docs",),
            {
                "tags": (
                    "SELECT * FROM tags WHERE entry_id IN "
                    "(SELECT id FROM entries WHERE category = ?)",
                    ("docs",),
                    "entry_id",
                ),
                "metadata": (
                    "SELECT * FROM metadata WHERE entry_id IN "
                    "(SELECT id FROM entries WHERE category = ?)",
                    ("docs",),
                    "entry_id",
                ),
            },
        )

        # Join results
        entries = results["main"]
        eager_loader.join_results(entries, results["tags"], "id", "tags")
        eager_loader.join_results(entries, results["metadata"], "id", "metadata")

        return entries
