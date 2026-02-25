"""
Migration: Create conversation_files database and schema
Version: 001
Created: 2025-09-30
Description: Initial migration to create conversation-specific file management database
"""

import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from constants.path_constants import PATH
from constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class ConversationFilesMigration:
    """
    Migration to create and initialize conversation files database.

    This migration:
    1. Creates the conversation_files.db SQLite database
    2. Executes the complete schema from conversation_files_schema.sql
    3. Validates the schema was created correctly
    4. Provides rollback capability for development
    """

    VERSION = "001"
    DESCRIPTION = "Create conversation_files database and schema"

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        schema_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ):
        """
        Initialize migration with configurable paths.

        Args:
            data_dir: Directory for database files (default: PATH.DATA_DIR)
            schema_dir: Directory containing schema files (default: PATH.DATABASE_DIR / "schemas")
            db_path: Full path to database file (optional, overrides data_dir/conversation_files.db)
        """
        self.data_dir = data_dir or PATH.DATA_DIR
        self.schema_dir = schema_dir or PATH.DATABASE_DIR / "schemas"

        # Allow custom database path OR use default in data_dir
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = self.data_dir / "conversation_files.db"

        self.schema_path = self.schema_dir / "conversation_files_schema.sql"

        self.connection: Optional[sqlite3.Connection] = None

    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured data directory exists: {self.data_dir}")

    def _read_schema(self) -> str:
        """
        Read the SQL schema file.

        Returns:
            str: Complete SQL schema content

        Raises:
            FileNotFoundError: If schema file doesn't exist
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(
                f"Schema file not found: {self.schema_path}\n"
                f"Expected location: {self.schema_path.absolute()}"
            )

        with open(self.schema_path, "r", encoding="utf-8") as f:
            schema_content = f.read()

        logger.info(f"Read schema from: {self.schema_path}")
        return schema_content

    def _connect_database(self) -> sqlite3.Connection:
        """
        Create database connection with optimized settings.

        Returns:
            sqlite3.Connection: Database connection
        """
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=TimingConstants.SHORT_TIMEOUT,
            isolation_level=None,  # Autocommit mode for DDL
        )

        # Enable foreign keys
        connection.execute("PRAGMA foreign_keys = ON")

        # Performance optimizations
        connection.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
        connection.execute("PRAGMA synchronous = NORMAL")  # Balance safety/performance
        connection.execute("PRAGMA cache_size = -64000")  # 64MB cache
        connection.execute("PRAGMA temp_store = MEMORY")  # Use memory for temp tables

        logger.info(f"Connected to database: {self.db_path}")
        return connection

    def _execute_schema(self, schema_sql: str) -> None:
        """
        Execute schema SQL with proper error handling.

        Args:
            schema_sql: Complete SQL schema to execute
        """
        if not self.connection:
            raise RuntimeError("Database connection not established")

        cursor = self.connection.cursor()

        try:
            # Execute schema as a script (handles multiple statements)
            cursor.executescript(schema_sql)
            logger.info("Schema executed successfully")

        except sqlite3.Error as e:
            logger.error(f"Error executing schema: {e}")
            raise

        finally:
            cursor.close()

    def _validate_tables(self, cursor: sqlite3.Cursor, expected_tables: set) -> bool:
        """
        Validate that all expected tables exist in the database.

        Called by _validate_schema to check table presence.

        Args:
            cursor: Active database cursor
            expected_tables: Set of table names that must exist

        Returns:
            bool: True if all tables are present, False otherwise
        """
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual_tables = {row[0] for row in cursor.fetchall()}
        missing_tables = expected_tables - actual_tables
        if missing_tables:
            logger.error(f"Missing tables: {missing_tables}")
            return False
        logger.info(f"✓ All {len(expected_tables)} tables created")
        return True

    def _validate_views(self, cursor: sqlite3.Cursor, expected_views: set) -> bool:
        """
        Validate that all expected views exist in the database.

        Called by _validate_schema to check view presence.

        Args:
            cursor: Active database cursor
            expected_views: Set of view names that must exist

        Returns:
            bool: True if all views are present, False otherwise
        """
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view'")
        actual_views = {row[0] for row in cursor.fetchall()}
        missing_views = expected_views - actual_views
        if missing_views:
            logger.error(f"Missing views: {missing_views}")
            return False
        logger.info(f"✓ All {len(expected_views)} views created")
        return True

    def _validate_indexes(self, cursor: sqlite3.Cursor, expected_indexes: set) -> bool:
        """
        Validate that all expected indexes exist in the database.

        Called by _validate_schema to check index presence.

        Args:
            cursor: Active database cursor
            expected_indexes: Set of index names that must exist

        Returns:
            bool: True if all indexes are present, False otherwise
        """
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
        )
        actual_indexes = {row[0] for row in cursor.fetchall()}
        missing_indexes = expected_indexes - actual_indexes
        if missing_indexes:
            logger.error(f"Missing indexes: {missing_indexes}")
            return False
        logger.info(f"✓ All {len(expected_indexes)} indexes created")
        return True

    def _validate_triggers(
        self, cursor: sqlite3.Cursor, expected_triggers: set
    ) -> bool:
        """
        Validate that all expected triggers exist in the database.

        Called by _validate_schema to check trigger presence.

        Args:
            cursor: Active database cursor
            expected_triggers: Set of trigger names that must exist

        Returns:
            bool: True if all triggers are present, False otherwise
        """
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        actual_triggers = {row[0] for row in cursor.fetchall()}
        missing_triggers = expected_triggers - actual_triggers
        if missing_triggers:
            logger.error(f"Missing triggers: {missing_triggers}")
            return False
        logger.info(f"✓ All {len(expected_triggers)} triggers created")
        return True

    def _get_expected_schema_objects(self):
        """
        Return the expected sets of tables, views, indexes, and triggers.

        Called by _validate_schema to obtain the canonical schema object names.

        Returns:
            Tuple[set, set, set, set]: expected_tables, expected_views,
                expected_indexes, expected_triggers
        """
        expected_tables = {
            "conversation_files",
            "file_metadata",
            "session_file_associations",
            "file_access_log",
            "file_cleanup_queue",
        }
        expected_views = {
            "v_active_files",
            "v_session_file_summary",
            "v_pending_cleanups",
        }
        expected_indexes = {
            "idx_conversation_files_session",
            "idx_conversation_files_hash",
            "idx_conversation_files_uploaded_at",
            "idx_file_metadata_file_id",
            "idx_session_associations_session",
            "idx_session_associations_file",
            "idx_file_access_log_file",
            "idx_cleanup_queue_processed",
        }
        expected_triggers = {
            "trg_conversation_files_soft_delete",
            "trg_conversation_files_upload_log",
            "trg_session_association_cleanup_schedule",
        }
        return expected_tables, expected_views, expected_indexes, expected_triggers

    def _validate_schema(self) -> bool:
        """
        Validate that all expected tables, indexes, triggers, and views were created.

        Orchestrates _validate_tables, _validate_views, _validate_indexes,
        and _validate_triggers helpers.

        Returns:
            bool: True if schema is valid, False otherwise
        """
        if not self.connection:
            raise RuntimeError("Database connection not established")

        cursor = self.connection.cursor()

        try:
            (
                expected_tables,
                expected_views,
                expected_indexes,
                expected_triggers,
            ) = self._get_expected_schema_objects()

            if not self._validate_tables(cursor, expected_tables):
                return False
            if not self._validate_views(cursor, expected_views):
                return False
            if not self._validate_indexes(cursor, expected_indexes):
                return False
            if not self._validate_triggers(cursor, expected_triggers):
                return False

            # Validate foreign key constraints are enabled
            cursor.execute("PRAGMA foreign_keys")
            fk_enabled = cursor.fetchone()[0]
            if not fk_enabled:
                logger.error("Foreign keys are not enabled")
                return False

            logger.info("✓ Foreign keys enabled")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error validating schema: {e}")
            return False

        finally:
            cursor.close()

    def _record_migration(self) -> None:
        """Record migration completion in migrations table."""
        if not self.connection:
            raise RuntimeError("Database connection not established")

        cursor = self.connection.cursor()

        try:
            # Create migrations tracking table if it doesn't exist
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'completed',
                    execution_time_ms INTEGER
                )
            """
            )

            # Record this migration (INSERT OR IGNORE for idempotency - safe for concurrent initialization)
            # If version already exists, silently skip (no error) - critical for multi-VM distributed environment
            cursor.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, description, status)
                VALUES (?, ?, 'completed')
            """,
                (self.VERSION, self.DESCRIPTION),
            )

            self.connection.commit()
            logger.info(f"Recorded migration {self.VERSION} in schema_migrations table")

        except sqlite3.Error as e:
            logger.error(f"Error recording migration: {e}")
            raise

        finally:
            cursor.close()

    async def up(self) -> bool:
        """
        Execute migration to create database and schema.

        Returns:
            bool: True if migration succeeded, False otherwise
        """
        start_time = datetime.now()

        try:
            logger.info("=" * 80)
            logger.info(f"Starting migration {self.VERSION}: {self.DESCRIPTION}")
            logger.info("=" * 80)

            # Step 1: Ensure directories exist
            self._ensure_directories()

            # Step 2: Check if database already exists
            if self.db_path.exists():
                logger.warning(f"Database already exists at: {self.db_path}")
                logger.info("Migration will attempt to create missing schema elements")

            # Step 3: Read schema
            schema_sql = self._read_schema()
            logger.info(f"Schema size: {len(schema_sql)} characters")

            # Step 4: Connect to database
            self.connection = self._connect_database()

            # Step 5: Execute schema
            logger.info("Executing schema...")
            self._execute_schema(schema_sql)

            # Step 6: Validate schema
            logger.info("Validating schema...")
            if not self._validate_schema():
                raise RuntimeError("Schema validation failed")

            # Step 7: Record migration
            self._record_migration()

            execution_time = (datetime.now() - start_time).total_seconds()

            logger.info("=" * 80)
            logger.info(f"✓ Migration {self.VERSION} completed successfully")
            logger.info(f"Database: {self.db_path}")
            logger.info(f"Execution time: {execution_time:.2f}s")
            logger.info("=" * 80)

            return True

        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"✗ Migration {self.VERSION} failed: {e}")
            logger.error("=" * 80)
            return False

        finally:
            if self.connection:
                self.connection.close()
                logger.info("Database connection closed")

    async def down(self) -> bool:
        """
        Rollback migration by dropping all schema elements.

        WARNING: This will delete all data in the database!

        Returns:
            bool: True if rollback succeeded, False otherwise
        """
        try:
            logger.warning("=" * 80)
            logger.warning(f"Rolling back migration {self.VERSION}")
            logger.warning("This will delete all data in the database!")
            logger.warning("=" * 80)

            if not self.db_path.exists():
                logger.info("Database doesn't exist, nothing to rollback")
                return True

            # Connect to database
            self.connection = self._connect_database()
            cursor = self.connection.cursor()

            try:
                # Drop views
                cursor.execute("SELECT name FROM sqlite_master WHERE type='view'")
                views = [row[0] for row in cursor.fetchall()]
                for view in views:
                    cursor.execute(f"DROP VIEW IF EXISTS {view}")
                    logger.info(f"Dropped view: {view}")

                # Drop tables (in reverse dependency order)
                tables_to_drop = [
                    "file_cleanup_queue",
                    "file_access_log",
                    "session_file_associations",
                    "file_metadata",
                    "conversation_files",
                    "schema_migrations",
                ]

                for table in tables_to_drop:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    logger.info(f"Dropped table: {table}")

                self.connection.commit()

                logger.warning("=" * 80)
                logger.warning(f"✓ Migration {self.VERSION} rolled back successfully")
                logger.warning("=" * 80)

                return True

            finally:
                cursor.close()
                self.connection.close()

        except Exception as e:
            logger.error(f"✗ Rollback failed: {e}")
            return False


async def run_migration():
    """Execute the migration."""
    migration = ConversationFilesMigration()
    success = await migration.up()

    if success:
        logger.info("Migration completed successfully!")
        return 0
    else:
        logger.error("Migration failed!")
        return 1


async def rollback_migration():
    """Rollback the migration (for development only)."""
    migration = ConversationFilesMigration()
    success = await migration.down()

    if success:
        logger.warning("Migration rolled back successfully!")
        return 0
    else:
        logger.error("Rollback failed!")
        return 1


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run migration
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "down":
        exit_code = asyncio.run(rollback_migration())
    else:
        exit_code = asyncio.run(run_migration())

    sys.exit(exit_code)
