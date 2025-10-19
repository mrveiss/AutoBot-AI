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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import (
    RedisError,
)
from redis.exceptions import TimeoutError as RedisTimeoutError

from backend.utils.async_redis_manager import AsyncRedisDatabase, get_redis_manager
from src.constants.network_constants import NetworkConstants
from src.unified_config_manager import unified_config_manager

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
            storage_dir: Directory for file storage (default: env var or data/conversation_files/)
            db_path: Path to SQLite database (default: env var or data/conversation_files.db)
            redis_host: Redis server host (default: from config.yaml or env var)
            redis_port: Redis server port (default: from config.yaml or env var)

        Environment Variables:
            AUTOBOT_STORAGE_DIR: Override default storage directory
            AUTOBOT_DB_PATH: Override default database path
            AUTOBOT_SCHEMA_DIR: Override default schema directory (for migrations)
            AUTOBOT_REDIS_HOST: Override Redis host from config.yaml
            AUTOBOT_REDIS_PORT: Override Redis port from config.yaml

        Configuration:
            Redis configuration is read from config.yaml via unified_config_manager.
            Default values are defined in config/config.yaml under memory.redis section.
        """
        # Storage paths with environment variable support (no hardcoded absolute paths)
        project_root = Path(__file__).parent.parent
        default_storage = Path(
            os.getenv(
                "AUTOBOT_STORAGE_DIR", str(project_root / "data" / "conversation_files")
            )
        )
        default_db = Path(
            os.getenv(
                "AUTOBOT_DB_PATH", str(project_root / "data" / "conversation_files.db")
            )
        )

        self.storage_dir = storage_dir or default_storage
        self.db_path = db_path or default_db

        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Redis configuration from unified config system (no hardcoded defaults)
        redis_config = unified_config_manager.get_redis_config()
        self.redis_host = redis_host or redis_config.get("host")
        self.redis_port = redis_port or redis_config.get("port")
        self._redis_manager = None
        self._redis_sessions: Optional[AsyncRedisDatabase] = None

        # SQLite connection (will be created per-operation for thread safety)
        self._lock = asyncio.Lock()

        # CRITICAL: Database initialization removed from __init__() (Bug Fix #1 and #5)
        # Database creation must ONLY happen during initialize() via migration system
        # This prevents:
        #   1. Database creation before initialize() is called (wrong lifecycle phase)
        #   2. Double schema application (once in __init__, once in initialize())
        #   3. Race conditions during concurrent initialization
        # Call initialize() explicitly to create database

        logger.info(
            f"ConversationFileManager initialized - "
            f"storage: {self.storage_dir}, db: {self.db_path} "
            f"(database will be created during initialize() call)"
        )

    def _initialize_schema(self) -> None:
        """
        Initialize database schema from SQL file.

        This method is idempotent - safe to run multiple times.
        Uses CREATE TABLE IF NOT EXISTS statements from schema file.

        Raises:
            RuntimeError: If database schema initialization fails
        """
        project_root = Path(__file__).parent.parent
        schema_path = project_root / "database/schemas/conversation_files_schema.sql"

        if not schema_path.exists():
            logger.warning(f"Schema file not found at {schema_path}")
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
            logger.error(f"❌ Failed to initialize schema: {e}")
            raise RuntimeError(f"Database schema initialization failed: {e}")

        finally:
            connection.close()

    async def _get_redis_sessions(self) -> AsyncRedisDatabase:
        """
        Get Redis sessions database (DB 2) for caching.

        Returns:
            AsyncRedisDatabase: Redis sessions database connection

        Raises:
            RuntimeError: If Redis connection cannot be established
        """
        if self._redis_sessions is None:
            if self._redis_manager is None:
                self._redis_manager = await get_redis_manager(
                    host=self.redis_host, port=self.redis_port
                )

            self._redis_sessions = await self._redis_manager.sessions()

        return self._redis_sessions

    def _get_db_connection(self) -> sqlite3.Connection:
        """
        Create a new SQLite database connection with optimized settings.

        Returns:
            sqlite3.Connection: Database connection configured for async safety

        Raises:
            RuntimeError: If foreign keys cannot be enabled (data integrity requirement)
        """
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
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

            logger.debug(f"Cached {len(file_list)} files for session {session_id}")

        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis connection/timeout error caching session files: {e}")
            # Non-critical failure, continue without cache
        except RedisError as e:
            logger.warning(f"Redis error caching session files: {e}")
            # Non-critical failure, continue without cache
        except Exception as e:
            logger.error(f"Unexpected error caching session files: {e}")
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

            logger.debug(f"Invalidated cache for session {session_id}")

        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis connection/timeout error invalidating cache: {e}")
        except RedisError as e:
            logger.warning(f"Redis error invalidating cache: {e}")
        except Exception as e:
            logger.error(f"Unexpected error invalidating cache: {e}")

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
        """
        Add a file to the conversation file system.

        This method:
        1. Validates file size
        2. Computes file hash for deduplication
        3. Checks for existing files with same hash
        4. Stores file to disk
        5. Records metadata in database
        6. Logs access
        7. Schedules cleanup
        8. Invalidates cache

        Args:
            session_id: Chat session identifier
            file_content: File content bytes
            original_filename: Original filename from upload
            mime_type: MIME type (optional)
            uploaded_by: User identifier (optional)
            message_id: Associated message ID (optional)
            metadata: Additional metadata key-value pairs (optional)

        Returns:
            Dict[str, Any]: File metadata including file_id, stored_filename, file_path

        Raises:
            ValueError: If file size exceeds maximum
            RuntimeError: If database operation fails
        """
        async with self._lock:
            # Validate file size
            file_size = len(file_content)
            if file_size > self.MAX_FILE_SIZE:
                raise ValueError(
                    f"File size ({file_size} bytes) exceeds maximum "
                    f"({self.MAX_FILE_SIZE} bytes)"
                )

            # Compute file hash for deduplication
            file_hash = self._compute_file_hash(file_content)

            # Generate unique identifiers
            file_id = str(uuid.uuid4())
            stored_filename = self._generate_stored_filename(
                original_filename, file_hash
            )
            file_path = self.storage_dir / stored_filename

            # Database operations
            connection = self._get_db_connection()
            cursor = connection.cursor()

            try:
                # Check for existing file with same hash (deduplication)
                cursor.execute(
                    """
                    SELECT file_id, stored_filename, file_path
                    FROM conversation_files
                    WHERE file_hash = ? AND is_deleted = 0
                    LIMIT 1
                """,
                    (file_hash,),
                )

                existing_file = cursor.fetchone()

                if existing_file:
                    # File already exists, create association only
                    existing_file_id = existing_file["file_id"]
                    existing_path = Path(existing_file["file_path"])

                    logger.info(
                        f"File with hash {file_hash[:8]}... already exists, "
                        f"creating association only"
                    )

                    # Create session association
                    cursor.execute(
                        """
                        INSERT INTO session_file_associations
                        (session_id, file_id, message_id, association_type)
                        VALUES (?, ?, ?, 'reference')
                    """,
                        (session_id, existing_file_id, message_id),
                    )

                    connection.commit()

                    # Log access
                    await self._log_access(
                        existing_file_id,
                        "reference",
                        uploaded_by,
                        {"session_id": session_id, "deduplication": True},
                    )

                    # Invalidate cache
                    await self._invalidate_session_cache(session_id)

                    return {
                        "file_id": existing_file_id,
                        "session_id": session_id,
                        "original_filename": original_filename,
                        "stored_filename": existing_file["stored_filename"],
                        "file_path": str(existing_path),
                        "file_size": file_size,
                        "file_hash": file_hash,
                        "mime_type": mime_type,
                        "uploaded_at": datetime.now().isoformat(),
                        "deduplicated": True,
                    }

                # File doesn't exist, store it
                # Write file to disk
                with open(file_path, "wb") as f:
                    f.write(file_content)

                logger.info(f"Stored file: {stored_filename} ({file_size} bytes)")

                # Insert file record
                cursor.execute(
                    """
                    INSERT INTO conversation_files
                    (file_id, session_id, original_filename, stored_filename,
                     file_path, file_size, file_hash, mime_type, uploaded_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        file_id,
                        session_id,
                        original_filename,
                        stored_filename,
                        str(file_path),
                        file_size,
                        file_hash,
                        mime_type,
                        uploaded_by,
                    ),
                )

                # Create session association
                cursor.execute(
                    """
                    INSERT INTO session_file_associations
                    (session_id, file_id, message_id, association_type)
                    VALUES (?, ?, ?, 'upload')
                """,
                    (session_id, file_id, message_id),
                )

                # Add metadata if provided
                if metadata:
                    for key, value in metadata.items():
                        cursor.execute(
                            """
                            INSERT INTO file_metadata (file_id, metadata_key, metadata_value)
                            VALUES (?, ?, ?)
                        """,
                            (file_id, key, str(value)),
                        )

                connection.commit()

                logger.info(
                    f"Added file {file_id} to session {session_id}: "
                    f"{original_filename} ({file_size} bytes)"
                )

                # Invalidate cache
                await self._invalidate_session_cache(session_id)

                return {
                    "file_id": file_id,
                    "session_id": session_id,
                    "original_filename": original_filename,
                    "stored_filename": stored_filename,
                    "file_path": str(file_path),
                    "file_size": file_size,
                    "file_hash": file_hash,
                    "mime_type": mime_type,
                    "uploaded_at": datetime.now().isoformat(),
                    "deduplicated": False,
                }

            except Exception as e:
                connection.rollback()
                # Clean up file if database operation failed
                if file_path.exists():
                    file_path.unlink()
                logger.error(f"Error adding file: {e}")
                raise RuntimeError(f"Failed to add file: {e}")

            finally:
                cursor.close()
                connection.close()

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
            Dict with keys:
                - files: List of file metadata dictionaries
                - total_files: Total number of files
                - total_size: Total size of all files in bytes
        """
        connection = self._get_db_connection()
        cursor = connection.cursor()

        try:
            # Get total count
            cursor.execute(
                """
                SELECT COUNT(*) as total, COALESCE(SUM(cf.file_size), 0) as total_size
                FROM conversation_files cf
                JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
                WHERE sfa.session_id = ? AND cf.is_deleted = 0
            """,
                (session_id,),
            )

            totals = cursor.fetchone()
            total_files = totals["total"]
            total_size = totals["total_size"]

            # Get paginated files
            offset = (page - 1) * page_size
            cursor.execute(
                """
                SELECT
                    cf.file_id,
                    cf.session_id,
                    cf.original_filename as filename,
                    cf.original_filename,
                    cf.stored_filename,
                    cf.file_path,
                    cf.file_size as size,
                    cf.file_hash,
                    cf.mime_type,
                    cf.uploaded_at,
                    cf.uploaded_by,
                    cf.is_deleted,
                    cf.deleted_at,
                    sfa.association_type,
                    sfa.message_id,
                    sfa.associated_at,
                    LOWER(SUBSTR(cf.original_filename, INSTR(cf.original_filename, '.') + 1)) as extension
                FROM conversation_files cf
                JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
                WHERE sfa.session_id = ? AND cf.is_deleted = 0
                ORDER BY sfa.associated_at DESC
                LIMIT ? OFFSET ?
            """,
                (session_id, page_size, offset),
            )

            files = []
            for row in cursor.fetchall():
                file_info = dict(row)
                files.append(file_info)

            logger.info(
                f"Listed {len(files)} files for session {session_id} (page {page}/{(total_files + page_size - 1) // page_size})"
            )

            return {
                "files": files,
                "total_files": total_files,
                "total_size": total_size,
            }

        except Exception as e:
            logger.error(f"Error listing files: {e}")
            raise RuntimeError(f"Failed to list files: {e}")

        finally:
            cursor.close()
            connection.close()

    async def get_session_files(
        self, session_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all files associated with a chat session.

        Attempts to use Redis cache first, falls back to database query.

        Args:
            session_id: Chat session identifier
            include_deleted: Include soft-deleted files (default: False)

        Returns:
            List[Dict[str, Any]]: List of file metadata dictionaries
        """
        # Try cache first
        try:
            redis_db = await self._get_redis_sessions()
            cache_key = f"{self.CACHE_KEY_PREFIX}{session_id}"
            cached_data = await redis_db.get(cache_key)

            if cached_data:
                logger.debug(f"Cache hit for session {session_id}")
                return json.loads(cached_data)

        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis connection/timeout error during cache lookup: {e}")
        except RedisError as e:
            logger.warning(f"Redis error during cache lookup: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during cache lookup: {e}")

        # Cache miss or error, query database
        connection = self._get_db_connection()
        cursor = connection.cursor()

        try:
            deleted_filter = "" if include_deleted else "AND cf.is_deleted = 0"

            cursor.execute(
                f"""
                SELECT
                    cf.file_id,
                    cf.session_id,
                    cf.original_filename,
                    cf.stored_filename,
                    cf.file_path,
                    cf.file_size,
                    cf.file_hash,
                    cf.mime_type,
                    cf.uploaded_at,
                    cf.uploaded_by,
                    cf.is_deleted,
                    cf.deleted_at,
                    sfa.association_type,
                    sfa.message_id,
                    sfa.associated_at
                FROM conversation_files cf
                JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
                WHERE sfa.session_id = ? {deleted_filter}
                ORDER BY sfa.associated_at DESC
            """,
                (session_id,),
            )

            files = []
            for row in cursor.fetchall():
                file_info = dict(row)
                files.append(file_info)

            # Cache result
            if not include_deleted:
                await self._cache_session_files(session_id, files)

            logger.info(f"Retrieved {len(files)} files for session {session_id}")
            return files

        except Exception as e:
            logger.error(f"Error retrieving session files: {e}")
            return []

        finally:
            cursor.close()
            connection.close()

    async def delete_session_files(
        self, session_id: str, hard_delete: bool = False
    ) -> int:
        """
        Delete all files associated with a session.

        Args:
            session_id: Chat session identifier
            hard_delete: If True, permanently delete files. If False, soft delete.

        Returns:
            int: Number of files deleted
        """
        async with self._lock:
            connection = self._get_db_connection()
            cursor = connection.cursor()

            try:
                # Get all file IDs for session
                cursor.execute(
                    """
                    SELECT DISTINCT cf.file_id, cf.file_path, cf.stored_filename
                    FROM conversation_files cf
                    JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
                    WHERE sfa.session_id = ? AND cf.is_deleted = 0
                """,
                    (session_id,),
                )

                files_to_delete = cursor.fetchall()
                deleted_count = 0

                for file_row in files_to_delete:
                    file_id = file_row["file_id"]
                    file_path = Path(file_row["file_path"])

                    if hard_delete:
                        # Permanently delete file and records
                        # Delete from database (cascades to related tables)
                        cursor.execute(
                            """
                            DELETE FROM conversation_files WHERE file_id = ?
                        """,
                            (file_id,),
                        )

                        # Delete physical file
                        if file_path.exists():
                            file_path.unlink()
                            logger.info(f"Hard deleted file: {file_path}")

                    else:
                        # Soft delete (mark as deleted)
                        cursor.execute(
                            """
                            UPDATE conversation_files
                            SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP
                            WHERE file_id = ?
                        """,
                            (file_id,),
                        )

                        logger.info(f"Soft deleted file: {file_id}")

                    deleted_count += 1

                connection.commit()

                # Invalidate cache
                await self._invalidate_session_cache(session_id)

                logger.info(
                    f"Deleted {deleted_count} files from session {session_id} "
                    f"(hard_delete={hard_delete})"
                )

                return deleted_count

            except Exception as e:
                connection.rollback()
                logger.error(f"Error deleting session files: {e}")
                raise RuntimeError(f"Failed to delete session files: {e}")

            finally:
                cursor.close()
                connection.close()

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
        connection = self._get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(
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

            connection.commit()

        except Exception as e:
            logger.warning(f"Failed to log file access: {e}")

        finally:
            cursor.close()
            connection.close()

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
            project_root = Path(__file__).parent.parent
            default_schema_dir = project_root / "database" / "schemas"
            schema_dir = Path(os.getenv("AUTOBOT_SCHEMA_DIR", str(default_schema_dir)))

            # Create migration instance with same paths (Bug Fix #6 - pass custom db_path for testing)
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
                f"✅ Conversation files database initialized (schema version: {version})"
            )

        except Exception as e:
            logger.error(f"❌ Failed to initialize conversation files database: {e}")
            raise RuntimeError(f"Database initialization failed: {e}")

    async def get_schema_version(self) -> str:
        """
        Get current database schema version.

        This is a public method for use by health checks and monitoring systems.

        Returns:
            str: Current schema version or "unknown" if not found or table doesn't exist
        """
        try:

            def _query_version():
                """Thread-safe database query for schema version."""
                connection = sqlite3.connect(
                    str(self.db_path), timeout=30.0, check_same_thread=False
                )
                cursor = connection.cursor()

                try:
                    # CRITICAL: Check if schema_migrations table exists BEFORE querying (Bug Fix #3)
                    # Prevents race condition where query runs before migration creates the table
                    cursor.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type='table' AND name='schema_migrations'
                    """
                    )

                    if not cursor.fetchone():
                        # Table doesn't exist yet - this is not an error during initialization
                        return "unknown"

                    # Table exists, safe to query version
                    # Use migration_id for deterministic ordering (applied_at can have same timestamp)
                    cursor.execute(
                        """
                        SELECT version FROM schema_migrations
                        ORDER BY migration_id DESC LIMIT 1
                    """
                    )
                    result = cursor.fetchone()

                    return result[0] if result else "unknown"

                finally:
                    cursor.close()
                    connection.close()

            # Execute query in thread pool to avoid blocking event loop
            version = await asyncio.to_thread(_query_version)
            return version

        except Exception as e:
            logger.warning(f"Failed to get schema version: {e}")
            return "unknown"

    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dict[str, Any]: Storage statistics including file count, total size, etc.
        """
        connection = self._get_db_connection()
        cursor = connection.cursor()

        try:
            # Total active files
            cursor.execute(
                """
                SELECT COUNT(*) as total_files, SUM(file_size) as total_size
                FROM conversation_files
                WHERE is_deleted = 0
            """
            )
            totals = cursor.fetchone()

            # Files by session
            cursor.execute(
                """
                SELECT COUNT(DISTINCT session_id) as total_sessions
                FROM conversation_files
                WHERE is_deleted = 0
            """
            )
            sessions = cursor.fetchone()

            # Deleted files
            cursor.execute(
                """
                SELECT COUNT(*) as deleted_files, SUM(file_size) as deleted_size
                FROM conversation_files
                WHERE is_deleted = 1
            """
            )
            deleted = cursor.fetchone()

            return {
                "total_files": totals["total_files"] or 0,
                "total_size_bytes": totals["total_size"] or 0,
                "total_size_mb": round((totals["total_size"] or 0) / (1024 * 1024), 2),
                "total_sessions": sessions["total_sessions"] or 0,
                "deleted_files": deleted["deleted_files"] or 0,
                "deleted_size_bytes": deleted["deleted_size"] or 0,
                "storage_directory": str(self.storage_dir),
                "database_path": str(self.db_path),
                "schema_version": "unknown",  # Will be updated by caller if needed
            }

        finally:
            cursor.close()
            connection.close()


# Global instance (singleton pattern)
_conversation_file_manager_instance: Optional[ConversationFileManager] = None


async def get_conversation_file_manager() -> ConversationFileManager:
    """
    Get global ConversationFileManager instance.

    Returns:
        ConversationFileManager: Global manager instance
    """
    global _conversation_file_manager_instance

    if _conversation_file_manager_instance is None:
        _conversation_file_manager_instance = ConversationFileManager()
        logger.info("Created global ConversationFileManager instance")

    return _conversation_file_manager_instance
