# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation File Manager - Conversation-Specific File Management System

This module provides comprehensive file management for chat sessions with:
- SQLite database for persistent file metadata
- Redis caching for fast session file lookups
- SHA-256 deduplication to prevent duplicate storage
- Comprehensive audit logging
- Automatic cleanup scheduling
- Thread-safe async operations
"""

import asyncio
import hashlib
import importlib
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import aiosqlite
import redis.asyncio as async_redis

from src.constants.threshold_constants import TimingConstants

# Module-level project root constant (Issue #380 - avoid repeated Path computation)
_PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class FileInfo:
    """Issue #375: Dataclass to group file-related parameters and reduce function signatures.

    Groups commonly passed file attributes to reduce long parameter lists across
    _store_new_file, _insert_file_record, _build_file_response, and related methods.
    """

    file_id: str
    session_id: str
    original_filename: str
    stored_filename: str
    file_path: Path
    file_size: int
    file_hash: str
    mime_type: Optional[str] = None
    uploaded_by: Optional[str] = None
    message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    deduplicated: bool = False

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to API response dictionary."""
        return {
            "file_id": self.file_id,
            "session_id": self.session_id,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "file_path": str(self.file_path),
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "mime_type": self.mime_type,
            "uploaded_at": datetime.now().isoformat(),
            "deduplicated": self.deduplicated,
        }

    def to_db_tuple(self) -> tuple:
        """Convert to database insert tuple (for conversation_files table)."""
        return (
            self.file_id,
            self.session_id,
            self.original_filename,
            self.stored_filename,
            str(self.file_path),
            self.file_size,
            self.file_hash,
            self.mime_type,
            self.uploaded_by,
        )


from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.config import unified_config_manager
from src.utils.redis_client import get_redis_client as get_redis_manager

logger = logging.getLogger(__name__)


class ConversationFileManager:
    """
    Manages conversation-specific file uploads with SQLite persistence and Redis caching.

    Features:
    - Persistent metadata storage in SQLite
    - Redis caching for session file lookups (Redis DB 2)
    - File deduplication using SHA-256 hashing
    - Soft delete with cleanup scheduling
    - Comprehensive audit logging
    - Thread-safe async operations
    """

    # Constants
    CACHE_DB = 2  # Redis database for session file caching
    CACHE_TTL = 3600  # Cache TTL: 1 hour
    CACHE_KEY_PREFIX = "conv_files:"
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
    CLEANUP_DAYS = 30  # Schedule cleanup 30 days after session end

    @staticmethod
    def _get_default_paths() -> tuple:
        """Get default storage directory and database path from environment or defaults."""
        storage = Path(
            os.getenv(
                "AUTOBOT_STORAGE_DIR",
                str(_PROJECT_ROOT / "data" / "conversation_files"),
            )
        )
        db = Path(
            os.getenv(
                "AUTOBOT_DB_PATH", str(_PROJECT_ROOT / "data" / "conversation_files.db")
            )
        )
        return storage, db

    def _init_redis_config(
        self, redis_host: Optional[str], redis_port: Optional[int]
    ) -> None:
        """Initialize Redis configuration from params or unified config."""
        redis_config = unified_config_manager.get_redis_config()
        self.redis_host = redis_host or redis_config.get("host")
        self.redis_port = redis_port or redis_config.get("port")
        self._redis_manager = None
        self._redis_sessions: Optional[async_redis.Redis] = None

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
        redis_host: str = None,
        redis_port: int = None,
    ):
        """
        Initialize ConversationFileManager.

        Args:
            storage_dir: Directory for file storage
            db_path: Path to SQLite database
            redis_host: Redis server host
            redis_port: Redis server port
        """
        default_storage, default_db = self._get_default_paths()
        self.storage_dir = storage_dir or default_storage
        self.db_path = db_path or default_db
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._init_redis_config(redis_host, redis_port)
        self._lock = asyncio.Lock()

        logger.info(
            "ConversationFileManager initialized - storage: %s, "
            "db: %s (database will be created during initialize() call)",
            self.storage_dir,
            self.db_path,
        )

    def _initialize_schema(self) -> None:
        """
        Initialize database schema from SQL file.

        This method is idempotent - safe to run multiple times.
        Uses CREATE TABLE IF NOT EXISTS statements from schema file.

        Raises:
            RuntimeError: If database schema initialization fails
        """
        schema_path = _PROJECT_ROOT / "database/schemas/conversation_files_schema.sql"

        if not schema_path.exists():
            logger.warning("Schema file not found at %s", schema_path)
            return

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        connection = self._get_db_connection()
        try:
            with open(schema_path, "r") as f:
                schema_sql = f.read()

            # Validate SQL syntax before execution
            if not schema_sql.strip():
                raise ValueError("Schema SQL file is empty")

            connection.executescript(schema_sql)
            logger.info("✅ Database schema initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize schema: %s", e)
            raise RuntimeError(f"Database schema initialization failed: {e}")

        finally:
            connection.close()

    async def _get_redis_sessions(self) -> async_redis.Redis:
        """
        Get Redis sessions database (DB 2) for caching.

        Returns:
            async_redis.Redis: Redis sessions database connection

        Raises:
            RuntimeError: If Redis connection cannot be established
        """
        if self._redis_sessions is None:
            self._redis_sessions = await get_redis_manager(
                async_client=True, database="sessions"
            )

        return self._redis_sessions

    def _get_db_connection(self) -> sqlite3.Connection:
        """
        Create a new SQLite database connection with optimized settings.

        DEPRECATED: Use _get_async_db_connection() for async contexts.
        This method is kept for backward compatibility with sync operations.

        Returns:
            sqlite3.Connection: Database connection configured for async safety

        Raises:
            RuntimeError: If foreign keys cannot be enabled (data integrity requirement)
        """
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=TimingConstants.SHORT_TIMEOUT,
            check_same_thread=False,  # Allow connection use across threads
        )

        # Enable foreign keys
        connection.execute("PRAGMA foreign_keys = ON")

        # CRITICAL: Verify foreign keys are actually enabled (Bug Fix #4)
        # Without this verification, referential integrity is NOT guaranteed
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys")
        fk_status = cursor.fetchone()[0]
        cursor.close()

        if fk_status != 1:
            connection.close()
            raise RuntimeError(
                "Failed to enable foreign keys - data integrity cannot be guaranteed. "
                "This is a critical database configuration issue."
            )

        # Performance optimizations
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")

        # Return rows as dictionaries
        connection.row_factory = sqlite3.Row

        return connection

    async def _get_async_db_connection(self) -> aiosqlite.Connection:
        """
        Create a new async SQLite database connection with optimized settings.

        Returns:
            aiosqlite.Connection: Async database connection

        Raises:
            RuntimeError: If foreign keys cannot be enabled (data integrity requirement)
        """
        connection = await aiosqlite.connect(
            str(self.db_path),
            timeout=TimingConstants.SHORT_TIMEOUT,
        )

        # Enable foreign keys
        await connection.execute("PRAGMA foreign_keys = ON")

        # Verify foreign keys are enabled
        async with connection.execute("PRAGMA foreign_keys") as cursor:
            row = await cursor.fetchone()
            if row[0] != 1:
                await connection.close()
                raise RuntimeError(
                    "Failed to enable foreign keys - data integrity cannot be guaranteed."
                )

        # Performance optimizations
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute("PRAGMA synchronous = NORMAL")

        # Return rows as dictionaries
        connection.row_factory = aiosqlite.Row

        return connection

    def _compute_file_hash(self, file_content: bytes) -> str:
        """
        Compute SHA-256 hash of file content for deduplication.

        Args:
            file_content: File content bytes

        Returns:
            str: Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(file_content).hexdigest()

    def _generate_stored_filename(self, original_filename: str, file_hash: str) -> str:
        """
        Generate unique storage filename to prevent collisions.

        Format: {hash_prefix}_{uuid}_{original_filename}

        Args:
            original_filename: Original filename from upload
            file_hash: SHA-256 hash of file content

        Returns:
            str: Unique storage filename
        """
        # Use first 8 characters of hash as prefix
        hash_prefix = file_hash[:8]

        # Generate UUID for uniqueness
        unique_id = str(uuid.uuid4())[:8]

        # Sanitize original filename (remove path separators)
        safe_filename = Path(original_filename).name

        return f"{hash_prefix}_{unique_id}_{safe_filename}"

    async def _cache_session_files(
        self, session_id: str, file_list: List[Dict[str, Any]]
    ) -> None:
        """
        Cache session file list in Redis for fast lookups.

        Args:
            session_id: Chat session identifier
            file_list: List of file metadata dictionaries
        """
        try:
            redis_db = await self._get_redis_sessions()
            cache_key = f"{self.CACHE_KEY_PREFIX}{session_id}"

            # Store as JSON with TTL
            await redis_db.set(cache_key, json.dumps(file_list), ex=self.CACHE_TTL)

            logger.debug("Cached %d files for session %s", len(file_list), session_id)

        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error caching session files: %s", e
            )
            # Non-critical failure, continue without cache
        except RedisError as e:
            logger.warning("Redis error caching session files: %s", e)
            # Non-critical failure, continue without cache
        except Exception as e:
            logger.error("Unexpected error caching session files: %s", e)
            # Non-critical failure, continue without cache

    async def _invalidate_session_cache(self, session_id: str) -> None:
        """
        Invalidate cached session file list.

        Args:
            session_id: Chat session identifier
        """
        try:
            redis_db = await self._get_redis_sessions()
            cache_key = f"{self.CACHE_KEY_PREFIX}{session_id}"
            await redis_db.delete(cache_key)

            logger.debug("Invalidated cache for session %s", session_id)

        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning("Redis connection/timeout error invalidating cache: %s", e)
        except RedisError as e:
            logger.warning("Redis error invalidating cache: %s", e)
        except Exception as e:
            logger.error("Unexpected error invalidating cache: %s", e)

    def _validate_file_size(self, file_content: bytes) -> int:
        """Validate file size and return size in bytes."""
        file_size = len(file_content)
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File size ({file_size} bytes) exceeds maximum "
                f"({self.MAX_FILE_SIZE} bytes)"
            )
        return file_size

    async def _check_existing_file(self, connection, file_hash: str):
        """Check for existing file with same hash for deduplication."""
        async with connection.execute(
            """
            SELECT file_id, stored_filename, file_path
            FROM conversation_files
            WHERE file_hash = ? AND is_deleted = 0
            LIMIT 1
            """,
            (file_hash,),
        ) as cursor:
            return await cursor.fetchone()

    async def _create_file_association(
        self,
        connection,
        session_id: str,
        file_id: str,
        message_id: Optional[str],
        association_type: str,
    ) -> None:
        """Create session file association record."""
        await connection.execute(
            """
            INSERT INTO session_file_associations
            (session_id, file_id, message_id, association_type)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, file_id, message_id, association_type),
        )

    async def _handle_deduplicated_file(
        self, connection, existing_file, file_info: FileInfo
    ) -> Dict[str, Any]:
        """Handle case where file already exists (Issue #375: uses FileInfo dataclass)."""
        existing_file_id = existing_file["file_id"]
        existing_path = Path(existing_file["file_path"])

        logger.info(
            "File with hash %s... already exists, creating association only",
            file_info.file_hash[:8],
        )

        await self._create_file_association(
            connection,
            file_info.session_id,
            existing_file_id,
            file_info.message_id,
            "reference",
        )
        await connection.commit()

        await self._log_access(
            existing_file_id,
            "reference",
            file_info.uploaded_by,
            {"session_id": file_info.session_id, "deduplication": True},
        )
        await self._invalidate_session_cache(file_info.session_id)

        # Create response FileInfo with existing file data
        response_info = FileInfo(
            file_id=existing_file_id,
            session_id=file_info.session_id,
            original_filename=file_info.original_filename,
            stored_filename=existing_file["stored_filename"],
            file_path=existing_path,
            file_size=file_info.file_size,
            file_hash=file_info.file_hash,
            mime_type=file_info.mime_type,
            deduplicated=True,
        )
        return response_info.to_response_dict()

    async def _write_file_to_disk(self, file_path: Path, file_content: bytes) -> None:
        """Write file content to disk asynchronously."""
        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file_content)
        except OSError as e:
            logger.error("Failed to write file to disk %s: %s", file_path, e)
            raise RuntimeError(f"Failed to write file to disk: {e}")

    async def _insert_file_record(self, connection, file_info: FileInfo) -> None:
        """Insert file record into database (Issue #375: uses FileInfo dataclass)."""
        await connection.execute(
            """
            INSERT INTO conversation_files
            (file_id, session_id, original_filename, stored_filename,
             file_path, file_size, file_hash, mime_type, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            file_info.to_db_tuple(),
        )

    async def _insert_file_metadata(
        self, connection, file_id: str, metadata: Dict[str, Any]
    ) -> None:
        """Insert file metadata records into database."""
        # Issue #397: Fix N+1 pattern - use executemany for batch insert
        if metadata:
            metadata_records = [
                (file_id, key, str(value)) for key, value in metadata.items()
            ]
            await connection.executemany(
                """
                INSERT INTO file_metadata (file_id, metadata_key, metadata_value)
                VALUES (?, ?, ?)
                """,
                metadata_records,
            )

    def _build_file_response(self, file_info: FileInfo) -> Dict[str, Any]:
        """Build standard file response dictionary (Issue #375: uses FileInfo dataclass)."""
        return file_info.to_response_dict()

    async def _store_new_file(
        self, connection, file_info: FileInfo, file_content: bytes
    ) -> Dict[str, Any]:
        """Store a new file to disk and database (Issue #375: uses FileInfo dataclass)."""
        await self._write_file_to_disk(file_info.file_path, file_content)
        logger.info(
            "Stored file: %s (%d bytes)", file_info.stored_filename, file_info.file_size
        )

        await self._insert_file_record(connection, file_info)
        await self._create_file_association(
            connection,
            file_info.session_id,
            file_info.file_id,
            file_info.message_id,
            "upload",
        )

        if file_info.metadata:
            await self._insert_file_metadata(
                connection, file_info.file_id, file_info.metadata
            )

        await connection.commit()
        logger.info(
            "Added file %s to session %s: %s (%d bytes)",
            file_info.file_id,
            file_info.session_id,
            file_info.original_filename,
            file_info.file_size,
        )
        await self._invalidate_session_cache(file_info.session_id)

        return self._build_file_response(file_info)

    async def add_file(
        self,
        session_id: str,
        file_content: bytes,
        original_filename: str,
        mime_type: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a file to the conversation file system."""
        async with self._lock:
            file_size = self._validate_file_size(file_content)
            file_hash = self._compute_file_hash(file_content)
            file_id = str(uuid.uuid4())
            stored_filename = self._generate_stored_filename(
                original_filename, file_hash
            )
            file_path = self.storage_dir / stored_filename

            # Issue #375: Create FileInfo dataclass to reduce parameter passing
            file_info = FileInfo(
                file_id=file_id,
                session_id=session_id,
                original_filename=original_filename,
                stored_filename=stored_filename,
                file_path=file_path,
                file_size=file_size,
                file_hash=file_hash,
                mime_type=mime_type,
                uploaded_by=uploaded_by,
                message_id=message_id,
                metadata=metadata,
                deduplicated=False,
            )

            connection = await self._get_async_db_connection()
            try:
                existing_file = await self._check_existing_file(connection, file_hash)
                if existing_file:
                    return await self._handle_deduplicated_file(
                        connection, existing_file, file_info
                    )
                return await self._store_new_file(connection, file_info, file_content)
            except Exception as e:
                await connection.rollback()
                if await asyncio.to_thread(file_path.exists):
                    await asyncio.to_thread(file_path.unlink)
                logger.error("Error adding file: %s", e)
                raise RuntimeError(f"Failed to add file: {e}")
            finally:
                await connection.close()

    async def _get_session_file_totals(self, connection, session_id: str) -> tuple:
        """Get total file count and size for a session."""
        async with connection.execute(
            """
            SELECT COUNT(*) as total, COALESCE(SUM(cf.file_size), 0) as total_size
            FROM conversation_files cf
            JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
            WHERE sfa.session_id = ? AND cf.is_deleted = 0
            """,
            (session_id,),
        ) as cursor:
            totals = await cursor.fetchone()
        return totals["total"], totals["total_size"]

    async def _get_paginated_files(
        self, connection, session_id: str, page_size: int, offset: int
    ) -> List[Dict]:
        """Get paginated files for a session."""
        async with connection.execute(
            """
            SELECT
                cf.file_id, cf.session_id, cf.original_filename as filename,
                cf.original_filename, cf.stored_filename, cf.file_path,
                cf.file_size as size, cf.file_hash, cf.mime_type, cf.uploaded_at,
                cf.uploaded_by, cf.is_deleted, cf.deleted_at, sfa.association_type,
                sfa.message_id, sfa.associated_at,
                LOWER(SUBSTR(cf.original_filename, INSTR(cf.original_filename, '.') + 1)) as extension
            FROM conversation_files cf
            JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
            WHERE sfa.session_id = ? AND cf.is_deleted = 0
            ORDER BY sfa.associated_at DESC
            LIMIT ? OFFSET ?
            """,
            (session_id, page_size, offset),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def list_files(
        self, session_id: str, page: int = 1, page_size: int = 50
    ) -> Dict[str, Any]:
        """
        List files for a session with pagination support.

        Args:
            session_id: Chat session identifier
            page: Page number (1-indexed)
            page_size: Number of files per page

        Returns:
            Dict with files, total_files, and total_size
        """
        connection = await self._get_async_db_connection()

        try:
            total_files, total_size = await self._get_session_file_totals(
                connection, session_id
            )
            offset = (page - 1) * page_size
            files = await self._get_paginated_files(
                connection, session_id, page_size, offset
            )

            logger.info(
                "Listed %d files for session %s (page %d/%d)",
                len(files),
                session_id,
                page,
                (total_files + page_size - 1) // page_size,
            )

            return {
                "files": files,
                "total_files": total_files,
                "total_size": total_size,
            }

        except Exception as e:
            logger.error("Error listing files: %s", e)
            raise RuntimeError(f"Failed to list files: {e}")

        finally:
            await connection.close()

    async def _try_get_cached_files(
        self, session_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Try to get cached files from Redis, return None on miss or error."""
        try:
            redis_db = await self._get_redis_sessions()
            cache_key = f"{self.CACHE_KEY_PREFIX}{session_id}"
            cached_data = await redis_db.get(cache_key)

            if cached_data:
                logger.debug("Cache hit for session %s", session_id)
                return json.loads(cached_data)
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning("Redis connection/timeout error during cache lookup: %s", e)
        except RedisError as e:
            logger.warning("Redis error during cache lookup: %s", e)
        except Exception as e:
            logger.error("Unexpected error during cache lookup: %s", e)
        return None

    async def _query_session_files_from_db(
        self, connection, session_id: str, include_deleted: bool
    ) -> List[Dict[str, Any]]:
        """Query session files from database."""
        deleted_filter = "" if include_deleted else "AND cf.is_deleted = 0"
        async with connection.execute(
            f"""
            SELECT cf.file_id, cf.session_id, cf.original_filename, cf.stored_filename,
                   cf.file_path, cf.file_size, cf.file_hash, cf.mime_type, cf.uploaded_at,
                   cf.uploaded_by, cf.is_deleted, cf.deleted_at, sfa.association_type,
                   sfa.message_id, sfa.associated_at
            FROM conversation_files cf
            JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
            WHERE sfa.session_id = ? {deleted_filter}
            ORDER BY sfa.associated_at DESC
            """,
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_session_files(
        self, session_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all files associated with a chat session (cache-first with DB fallback)."""
        cached = await self._try_get_cached_files(session_id)
        if cached is not None:
            return cached

        connection = await self._get_async_db_connection()
        try:
            files = await self._query_session_files_from_db(
                connection, session_id, include_deleted
            )
            if not include_deleted:
                await self._cache_session_files(session_id, files)
            logger.info("Retrieved %d files for session %s", len(files), session_id)
            return files
        except Exception as e:
            logger.error("Error retrieving session files: %s", e)
            return []
        finally:
            await connection.close()

    async def _hard_delete_file(
        self, connection, file_id: str, file_path: Path
    ) -> None:
        """Permanently delete a file (Issue #315 - extracted helper)."""
        await connection.execute(
            "DELETE FROM conversation_files WHERE file_id = ?", (file_id,)
        )
        # Issue #358 - avoid blocking
        if await asyncio.to_thread(file_path.exists):
            await asyncio.to_thread(file_path.unlink)
            logger.info("Hard deleted file: %s", file_path)

    async def _soft_delete_file(self, connection, file_id: str) -> None:
        """Soft delete a file by marking as deleted (Issue #315 - extracted helper)."""
        await connection.execute(
            """
            UPDATE conversation_files
            SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP
            WHERE file_id = ?
            """,
            (file_id,),
        )
        logger.info("Soft deleted file: %s", file_id)

    async def _get_session_file_ids(self, connection, session_id: str) -> List:
        """Get all file records for a session."""
        async with connection.execute(
            """
            SELECT DISTINCT cf.file_id, cf.file_path, cf.stored_filename
            FROM conversation_files cf
            JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
            WHERE sfa.session_id = ? AND cf.is_deleted = 0
            """,
            (session_id,),
        ) as cursor:
            return await cursor.fetchall()

    async def _delete_files_batch(
        self, connection, files: List, hard_delete: bool
    ) -> int:
        """Delete a batch of files, returning count deleted.

        Issue #397: Optimized to use batch SQL operations instead of N+1 pattern.
        """
        if not files:
            return 0

        file_ids = [file_row["file_id"] for file_row in files]

        if hard_delete:
            # For hard delete, we need to delete files from disk (can't batch filesystem ops)
            # but we can batch the SQL delete
            for file_row in files:
                file_path = Path(file_row["file_path"])
                if await asyncio.to_thread(file_path.exists):
                    await asyncio.to_thread(file_path.unlink)
                    logger.info("Hard deleted file: %s", file_path)

            # Issue #397: Batch SQL delete using IN clause
            placeholders = ",".join("?" * len(file_ids))
            await connection.execute(
                f"DELETE FROM conversation_files WHERE file_id IN ({placeholders})",
                file_ids,
            )
        else:
            # Issue #397: Batch soft delete using IN clause instead of N+1 pattern
            placeholders = ",".join("?" * len(file_ids))
            await connection.execute(
                f"""
                UPDATE conversation_files
                SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP
                WHERE file_id IN ({placeholders})
                """,
                file_ids,
            )
            logger.info("Soft deleted %d files in batch", len(file_ids))

        return len(file_ids)

    async def delete_session_files(
        self, session_id: str, hard_delete: bool = False
    ) -> int:
        """Delete all files associated with a session."""
        async with self._lock:
            connection = await self._get_async_db_connection()
            try:
                files = await self._get_session_file_ids(connection, session_id)
                deleted_count = await self._delete_files_batch(
                    connection, files, hard_delete
                )
                await connection.commit()
                await self._invalidate_session_cache(session_id)
                logger.info(
                    "Deleted %d files from session %s (hard_delete=%s)",
                    deleted_count,
                    session_id,
                    hard_delete,
                )
                return deleted_count
            except Exception as e:
                await connection.rollback()
                logger.error("Error deleting session files: %s", e)
                raise RuntimeError(f"Failed to delete session files: {e}")
            finally:
                await connection.close()

    async def _log_access(
        self,
        file_id: str,
        access_type: str,
        accessed_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log file access to audit trail.

        Args:
            file_id: File identifier
            access_type: Type of access ('upload', 'download', 'view', 'delete')
            accessed_by: User identifier
            metadata: Additional metadata for log entry
        """
        connection = await self._get_async_db_connection()

        try:
            await connection.execute(
                """
                INSERT INTO file_access_log
                (file_id, access_type, accessed_by, access_metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    file_id,
                    access_type,
                    accessed_by,
                    json.dumps(metadata) if metadata else None,
                ),
            )

            await connection.commit()

        except Exception as e:
            logger.warning("Failed to log file access: %s", e)

        finally:
            await connection.close()

    async def initialize(self) -> None:
        """
        Initialize the conversation file manager database.

        This method runs the database migration to create the schema if needed.
        Safe to run on already-initialized databases.

        Raises:
            RuntimeError: If database initialization fails
        """
        try:
            logger.info("Initializing conversation files database...")

            # Dynamic import to handle numeric module name
            migration_module = importlib.import_module(
                "database.migrations.001_create_conversation_files"
            )
            ConversationFilesMigration = getattr(
                migration_module, "ConversationFilesMigration"
            )

            # Resolve schema directory relative to project root (no hardcoded absolute paths)
            default_schema_dir = _PROJECT_ROOT / "database" / "schemas"
            schema_dir = Path(os.getenv("AUTOBOT_SCHEMA_DIR", str(default_schema_dir)))

            # Create migration instance with same paths (Bug Fix #6 - pass custom db_path for
            # testing)
            migration = ConversationFilesMigration(
                data_dir=self.db_path.parent,
                schema_dir=schema_dir,
                db_path=self.db_path,  # Use the exact database path specified in constructor
            )

            # Execute migration (safe to run on existing database)
            success = await migration.up()

            if not success:
                raise RuntimeError("Database migration failed")

            # Verify schema version
            version = await self.get_schema_version()
            logger.info(
                "Conversation files database initialized (schema version: %s)", version
            )

        except Exception as e:
            logger.error("Failed to initialize conversation files database: %s", e)
            raise RuntimeError(f"Database initialization failed: {e}")

    def _query_schema_version_sync(self) -> str:
        """Thread-safe database query for schema version (sync helper)."""
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=TimingConstants.SHORT_TIMEOUT,
            check_same_thread=False,
        )
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            )
            if not cursor.fetchone():
                return "unknown"
            cursor.execute(
                "SELECT version FROM schema_migrations ORDER BY migration_id DESC LIMIT 1"
            )
            result = cursor.fetchone()
            return result[0] if result else "unknown"
        finally:
            cursor.close()
            connection.close()

    async def get_schema_version(self) -> str:
        """Get current database schema version for health checks."""
        try:
            return await asyncio.to_thread(self._query_schema_version_sync)
        except Exception as e:
            logger.warning("Failed to get schema version: %s", e)
            return "unknown"

    async def _get_active_file_stats(self, connection) -> tuple:
        """Get active file count and total size."""
        async with connection.execute(
            "SELECT COUNT(*) as total_files, SUM(file_size) as total_size FROM conversation_files WHERE is_deleted = 0"
        ) as cursor:
            row = await cursor.fetchone()
        return row["total_files"] or 0, row["total_size"] or 0

    async def _get_session_count(self, connection) -> int:
        """Get count of sessions with files."""
        async with connection.execute(
            "SELECT COUNT(DISTINCT session_id) as total_sessions FROM conversation_files WHERE is_deleted = 0"
        ) as cursor:
            row = await cursor.fetchone()
        return row["total_sessions"] or 0

    async def _get_deleted_file_stats(self, connection) -> tuple:
        """Get deleted file count and size."""
        query = (
            "SELECT COUNT(*) as deleted_files, SUM(file_size) as deleted_size "
            "FROM conversation_files WHERE is_deleted = 1"
        )
        async with connection.execute(query) as cursor:
            row = await cursor.fetchone()
        return row["deleted_files"] or 0, row["deleted_size"] or 0

    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        connection = await self._get_async_db_connection()
        try:
            total_files, total_size = await self._get_active_file_stats(connection)
            total_sessions = await self._get_session_count(connection)
            deleted_files, deleted_size = await self._get_deleted_file_stats(connection)

            return {
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_sessions": total_sessions,
                "deleted_files": deleted_files,
                "deleted_size_bytes": deleted_size,
                "storage_directory": str(self.storage_dir),
                "database_path": str(self.db_path),
                "schema_version": "unknown",
            }
        finally:
            await connection.close()


# Global instance (singleton pattern, thread-safe)
import asyncio as _asyncio

_conversation_file_manager_instance: Optional[ConversationFileManager] = None
_conversation_file_manager_lock = _asyncio.Lock()


async def get_conversation_file_manager() -> ConversationFileManager:
    """
    Get global ConversationFileManager instance (thread-safe).

    Returns:
        ConversationFileManager: Global manager instance
    """
    global _conversation_file_manager_instance

    if _conversation_file_manager_instance is None:
        async with _conversation_file_manager_lock:
            # Double-check after acquiring lock
            if _conversation_file_manager_instance is None:
                _conversation_file_manager_instance = ConversationFileManager()
                logger.info("Created global ConversationFileManager instance")

    return _conversation_file_manager_instance
