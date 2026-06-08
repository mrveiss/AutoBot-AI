# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async Database Connection Pool Manager
Provides async connection pooling for SQLite and other databases using aiosqlite
to improve performance and prevent blocking operations.

Pool sizes are coordinated via SSOT config (#2860).
"""

import asyncio
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import aiosqlite

from autobot_shared.logging_manager import get_logger

# Import shared database helpers (Issue #292 - Eliminate duplicate code)
from constants.threshold_constants import TimingConstants
from utils.database_helpers import join_results  # noqa: F401 - re-export

logger = get_logger(__name__)


def _get_sqlite_pool_size() -> int:
    """Get SQLite pool size from SSOT config (#2860)."""
    try:
        from autobot_shared.ssot_config import get_config

        return get_config().database_pool.sqlite_pool_size
    except Exception:
        return 10


@dataclass
class PoolStats:
    """Connection pool statistics"""

    connections_created: int = 0
    connections_reused: int = 0
    total_wait_time: float = 0.0
    active_connections: int = 0
    max_connections_reached: int = 0


class AsyncSQLiteConnectionPool:
    """Async SQLite connection pool with proper resource management."""

    def __init__(
        self,
        db_path: str,
        pool_size: int | None = None,
        timeout: float = TimingConstants.SHORT_TIMEOUT,
    ):
        """
        Initialize async SQLite connection pool.

        Args:
            db_path: Path to SQLite database file
            pool_size: Maximum number of connections in pool.
                       Defaults to SSOT config sqlite_pool_size (#2860).
            timeout: Timeout for acquiring connection from pool
        """
        self.db_path = db_path
        self.pool_size = pool_size if pool_size is not None else _get_sqlite_pool_size()
        self.timeout = timeout
        self._pool = asyncio.Queue(maxsize=self.pool_size)
        self._lock = asyncio.Lock()
        self._created_connections = 0
        self._stats = PoolStats()
        self._initialized = False

    async def _apply_connection_pragmas(self, conn: aiosqlite.Connection) -> None:
        """Apply performance-tuning PRAGMA settings to connection. (Issue #315 - extracted)"""
        await conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        await conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        await conn.execute("PRAGMA cache_size=10000")  # Larger cache
        await conn.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
        await conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
        await conn.execute("PRAGMA foreign_keys=ON")  # Enable foreign keys

    async def _close_connection_safely(self, conn: aiosqlite.Connection) -> None:
        """Close connection with error suppression. (Issue #315 - extracted)"""
        try:
            await conn.close()
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new async SQLite connection with optimized settings."""
        conn = None
        try:
            conn = await aiosqlite.connect(self.db_path, timeout=self.timeout)
            await self._apply_connection_pragmas(conn)

            async with self._lock:
                self._created_connections += 1
                self._stats.connections_created += 1

            logger.debug("Created new async SQLite connection #%s", self._created_connections)
            return conn
        except aiosqlite.Error as e:
            logger.error("Failed to create async SQLite connection: %s", e)
            if conn:
                await self._close_connection_safely(conn)
            raise RuntimeError(f"Failed to create database connection: {e}")

    async def _initialize_pool(self):
        """Initialize the connection pool with pre-created connections."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            # Pre-create initial connections
            initial_size = min(5, self.pool_size)  # Start with 5 connections
            for _ in range(initial_size):
                try:
                    conn = await self._create_connection()
                    await self._pool.put(conn)
                except Exception as e:
                    logger.error("Failed to create initial async connection: %s", e)

            self._initialized = True
            logger.info(
                "Async connection pool initialized with %s connections",
                initial_size,
            )

    async def _acquire_connection(self) -> aiosqlite.Connection:
        """Acquire a connection from pool or create new one (Issue #315: extracted).

        Returns:
            aiosqlite.Connection from pool or newly created

        Raises:
            asyncio.TimeoutError if unable to get connection
        """
        # Try to get existing connection from pool
        try:
            conn = await asyncio.wait_for(self._pool.get(), timeout=self.timeout)
            self._stats.connections_reused += 1
            logger.debug("Reused async connection from pool")
            return conn
        except asyncio.TimeoutError:
            pass  # Pool empty, try to create new

        # Pool exhausted, create new connection if under limit
        async with self._lock:
            if self._created_connections < self.pool_size:
                return await self._create_connection()
            self._stats.max_connections_reached += 1
            logger.warning("Async connection pool exhausted, waiting...")

        # Wait for connection from pool
        return await asyncio.wait_for(self._pool.get(), timeout=self.timeout)

    async def _return_connection(self, conn: aiosqlite.Connection) -> None:
        """Return connection to pool (Issue #315: extracted).

        Args:
            conn: Connection to return
        """
        try:
            await conn.rollback()  # Reset any uncommitted transactions
            await self._pool.put(conn)
        except asyncio.QueueFull:
            await self._close_connection_safely(conn)
        except Exception as e:
            logger.error("Error returning connection to pool: %s", e)
            await self._close_connection_safely(conn)

    @asynccontextmanager
    async def get_connection(self):
        """
        Get a connection from the async pool (context manager).
        Issue #315: Refactored to use helpers for reduced nesting.

        Yields:
            aiosqlite.Connection: Async database connection
        """
        if not self._initialized:
            await self._initialize_pool()

        start_time = datetime.now(tz=timezone.utc)
        conn = None

        try:
            conn = await self._acquire_connection()

            # Record wait time
            wait_time = (datetime.now(tz=timezone.utc) - start_time).total_seconds()
            self._stats.total_wait_time += wait_time
            self._stats.active_connections += 1

            # Test connection is alive
            await conn.execute("SELECT 1")

            yield conn

        except Exception as e:
            logger.error("Error with async database connection: %s", e)
            # Connection is bad, don't return it to pool
            if conn:
                await self._close_connection_safely(conn)
                conn = None
            raise
        finally:
            self._stats.active_connections -= 1
            # Return good connection to pool
            if conn:
                await self._return_connection(conn)

    async def close_all(self):
        """Close all connections in the pool."""
        closed = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await conn.close()
                closed += 1
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error("Error closing connection: %s", e)

        logger.info("Closed %s async connections from pool", closed)
        async with self._lock:
            self._created_connections = 0
            self._initialized = False

    def get_stats(self) -> Dict[str, Any]:
        """Get pool usage statistics."""
        return {
            "connections_created": self._stats.connections_created,
            "connections_reused": self._stats.connections_reused,
            "total_wait_time": self._stats.total_wait_time,
            "active_connections": self._stats.active_connections,
            "max_connections_reached": self._stats.max_connections_reached,
            "current_pool_size": self._pool.qsize(),
            "total_connections_created": self._created_connections,
            "average_wait_time": (
                self._stats.total_wait_time / max(1, self._stats.connections_reused + self._stats.connections_created)
            ),
        }


# Global async connection pools per database
_async_connection_pools: Dict[str, AsyncSQLiteConnectionPool] = {}
_async_pools_lock = asyncio.Lock()


async def get_async_connection_pool(db_path: str, pool_size: int | None = None) -> AsyncSQLiteConnectionPool:
    """
    Get or create an async connection pool for a database.

    Args:
        db_path: Path to database file
        pool_size: Maximum pool size. Defaults to SSOT config (#2860).

    Returns:
        AsyncSQLiteConnectionPool: Async connection pool instance
    """
    # Normalize path
    db_path = str(Path(db_path).resolve())

    # Check if pool exists
    if db_path in _async_connection_pools:
        return _async_connection_pools[db_path]

    # Create new pool with lock
    async with _async_pools_lock:
        # Double-check after acquiring lock
        if db_path in _async_connection_pools:
            return _async_connection_pools[db_path]

        # Create new pool
        pool = AsyncSQLiteConnectionPool(db_path, pool_size)
        await pool._initialize_pool()
        _async_connection_pools[db_path] = pool
        logger.info(
            "Created async connection pool for %s with size %s",
            db_path,
            pool.pool_size,
        )
        return pool


async def close_all_async_pools():
    """Close all async connection pools."""
    async with _async_pools_lock:
        for db_path, pool in _async_connection_pools.items():
            logger.info("Closing async pool for %s", db_path)
            await pool.close_all()
        _async_connection_pools.clear()


# Async N+1 Query Prevention Helpers


class AsyncEagerLoader:
    """Helper class to prevent N+1 queries with async eager loading patterns."""

    @staticmethod
    async def batch_load_related(
        conn: aiosqlite.Connection,
        main_query: str,
        main_params: tuple,
        related_queries: Dict[str, tuple],
    ) -> Dict[str, Any]:
        """
        Execute main query and related queries efficiently with async.

        Args:
            conn: Async database connection
            main_query: Main SELECT query
            main_params: Parameters for main query
            related_queries: Dict of {name: (query, params, join_key)}

        Returns:
            Dict with 'main' results and related data
        """
        # Execute main query
        cursor = await conn.execute(main_query, main_params)
        main_results = await cursor.fetchall()

        result = {"main": [dict(row) for row in main_results]}

        # Execute related queries
        for name, (query, params, join_key) in related_queries.items():
            cursor = await conn.execute(query, params)
            related_results = await cursor.fetchall()

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


# Example usage for async knowledge base optimization
async def optimize_async_knowledge_base_queries():
    """Example of optimizing knowledge base queries to prevent N+1 with async."""
    db_path = "data/knowledge_base.db"
    pool = await get_async_connection_pool(db_path)

    async with pool.get_connection() as conn:
        # Use async batch loading to prevent N+1
        eager_loader = AsyncEagerLoader()
        results = await eager_loader.batch_load_related(
            conn,
            "SELECT * FROM entries WHERE category = ?",
            ("docs",),
            {
                "tags": (
                    "SELECT * FROM tags WHERE entry_id IN " "(SELECT id FROM entries WHERE category = ?)",
                    ("docs",),
                    "entry_id",
                ),
                "metadata": (
                    "SELECT * FROM metadata WHERE entry_id IN " "(SELECT id FROM entries WHERE category = ?)",
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


# Context manager for transaction handling
@asynccontextmanager
async def async_transaction(pool: AsyncSQLiteConnectionPool):
    """
    Context manager for async database transactions.

    Args:
        pool: Async connection pool

    Yields:
        aiosqlite.Connection: Connection with transaction started
    """
    async with pool.get_connection() as conn:
        try:
            await conn.execute("BEGIN")
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_sql_identifier(name: str, label: str = "identifier") -> str:
    """Validate a SQL identifier (table or column name) against an allowlist pattern.

    Only permits names composed of ASCII letters, digits, and underscores, starting
    with a letter or underscore. This prevents SQL injection via identifier interpolation
    in f-string query construction. (#2845)

    Args:
        name: The identifier to validate.
        label: Human-readable label used in the error message.

    Returns:
        The validated name unchanged.

    Raises:
        ValueError: If the name contains characters outside the allowed set.
    """
    if not _SQL_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL {label} '{name}': only letters, digits, and underscores allowed")
    return name


# Batch operation helpers
class AsyncBatchOperations:
    """Helper class for efficient batch database operations."""

    @staticmethod
    async def batch_insert(
        conn: aiosqlite.Connection,
        table: str,
        columns: list,
        data: list,
        batch_size: int = 1000,
    ):
        """
        Perform batch insert operations with async.

        Args:
            conn: Async database connection
            table: Table name
            columns: List of column names
            data: List of tuples with data to insert
            batch_size: Number of records per batch
        """
        _validate_sql_identifier(table, "table name")
        for col in columns:
            _validate_sql_identifier(col, "column name")
        placeholders = ", ".join(["?" for _ in columns])
        column_names = ", ".join(columns)
        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"  # nosec B608

        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            await conn.executemany(query, batch)
            logger.debug("Inserted batch %s: %s records", i // batch_size + 1, len(batch))

    @staticmethod
    async def batch_update(
        conn: aiosqlite.Connection,
        table: str,
        set_columns: list,
        where_column: str,
        data: list,
        batch_size: int = 1000,
    ):
        """
        Perform batch update operations with async.

        Args:
            conn: Async database connection
            table: Table name
            set_columns: List of columns to update
            where_column: Column for WHERE clause
            data: List of tuples with (set_values..., where_value)
            batch_size: Number of records per batch
        """
        _validate_sql_identifier(table, "table name")
        for col in set_columns:
            _validate_sql_identifier(col, "column name")
        _validate_sql_identifier(where_column, "column name")
        set_clause = ", ".join([f"{col} = ?" for col in set_columns])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_column} = ?"  # nosec B608

        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            await conn.executemany(query, batch)
            logger.debug("Updated batch %s: %s records", i // batch_size + 1, len(batch))
