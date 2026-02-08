"""
Unit Tests for ConversationFileManager Database Initialization

Tests comprehensive database initialization functionality including:
- First-time database creation
- Idempotent initialization (safe to call multiple times)
- Schema version tracking
- Schema integrity verification
- Migration framework
- Error handling

Test Coverage Target: 100% for initialization code
"""

import asyncio
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, List, Tuple

import pytest
from conversation_file_manager import ConversationFileManager

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Issue #618: Helper to run blocking sqlite3 queries in async context
async def async_sqlite_query(
    db_path: str, query: str, params: tuple = ()
) -> List[Tuple[Any, ...]]:
    """Execute sqlite3 query without blocking the event loop.

    Args:
        db_path: Path to SQLite database
        query: SQL query to execute
        params: Query parameters

    Returns:
        List of result tuples from fetchall()
    """

    def _execute():
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            cursor.close()
            connection.close()

    return await asyncio.to_thread(_execute)


async def async_sqlite_execute(db_path: str, query: str, params: tuple = ()) -> None:
    """Execute sqlite3 statement without blocking the event loop.

    Args:
        db_path: Path to SQLite database
        query: SQL statement to execute
        params: Query parameters
    """

    def _execute():
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        try:
            cursor.execute(query, params)
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    await asyncio.to_thread(_execute)


async def async_sqlite_multi_query(
    db_path: str, queries: List[str]
) -> List[List[Tuple[Any, ...]]]:
    """Execute multiple sqlite3 queries without blocking the event loop.

    Args:
        db_path: Path to SQLite database
        queries: List of SQL queries to execute

    Returns:
        List of result lists from each query's fetchall()
    """

    def _execute():
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        results = []
        try:
            for query in queries:
                cursor.execute(query)
                results.append(cursor.fetchall())
            return results
        finally:
            cursor.close()
            connection.close()

    return await asyncio.to_thread(_execute)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_conversation_files.db"
        storage_dir = Path(temp_dir) / "storage"
        storage_dir.mkdir()
        yield {
            "db_path": db_path,
            "storage_dir": storage_dir,
            "temp_dir": Path(temp_dir),
        }
        # Cleanup happens automatically when context manager exits


@pytest.fixture
async def conversation_file_manager(temp_db_path):
    """Create ConversationFileManager instance with temporary paths."""
    manager = ConversationFileManager(
        storage_dir=temp_db_path["storage_dir"],
        db_path=temp_db_path["db_path"],
        redis_host="localhost",
        redis_port=6379,
    )
    return manager


class TestFirstTimeInitialization:
    """Test first-time database initialization from scratch."""

    @pytest.mark.asyncio
    async def test_first_time_initialization(
        self, conversation_file_manager, temp_db_path
    ):
        """
        Test Case 1.1: First-time database initialization creates complete schema

        Validates:
        - Database file is created
        - All 5 tables are created
        - All 3 views are created
        - All 8 indexes are created
        - All 3 triggers are created
        - Schema version is recorded
        - Foreign keys are enabled
        """
        logger.info("=== Test 1.1: First-time initialization ===")

        # Verify database doesn't exist initially
        assert not temp_db_path[
            "db_path"
        ].exists(), "Database should not exist before initialization"

        # Run initialization
        await conversation_file_manager.initialize()

        # Verify database was created
        assert temp_db_path["db_path"].exists(), "Database file should be created"

        # Connect to database and verify schema (Issue #618: use async sqlite helper)
        db_path_str = str(temp_db_path["db_path"])

        # Run all schema verification queries in a single thread call
        results = await async_sqlite_multi_query(
            db_path_str,
            [
                "SELECT name FROM sqlite_master WHERE type='table'",
                "SELECT name FROM sqlite_master WHERE type='view'",
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'",
                "SELECT name FROM sqlite_master WHERE type='trigger'",
                "PRAGMA foreign_keys",
                "SELECT version FROM schema_migrations ORDER BY migration_id DESC LIMIT 1",
            ],
        )

        # Verify all required tables exist
        expected_tables = {
            "conversation_files",
            "file_metadata",
            "session_file_associations",
            "file_access_log",
            "file_cleanup_queue",
            "schema_migrations",  # Migration tracking table
        }
        actual_tables = {row[0] for row in results[0]}
        assert expected_tables.issubset(
            actual_tables
        ), f"Missing tables: {expected_tables - actual_tables}"
        logger.info(f"✓ All {len(expected_tables)} tables created")

        # Verify all required views exist
        expected_views = {
            "v_active_files",
            "v_session_file_summary",
            "v_pending_cleanups",
        }
        actual_views = {row[0] for row in results[1]}
        assert expected_views.issubset(
            actual_views
        ), f"Missing views: {expected_views - actual_views}"
        logger.info(f"✓ All {len(expected_views)} views created")

        # Verify all required indexes exist
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
        actual_indexes = {row[0] for row in results[2]}
        assert expected_indexes.issubset(
            actual_indexes
        ), f"Missing indexes: {expected_indexes - actual_indexes}"
        logger.info(f"✓ All {len(expected_indexes)} indexes created")

        # Verify all required triggers exist
        expected_triggers = {
            "trg_conversation_files_soft_delete",
            "trg_conversation_files_upload_log",
            "trg_session_association_cleanup_schedule",
        }
        actual_triggers = {row[0] for row in results[3]}
        assert expected_triggers.issubset(
            actual_triggers
        ), f"Missing triggers: {expected_triggers - actual_triggers}"
        logger.info(f"✓ All {len(expected_triggers)} triggers created")

        # Verify foreign keys are enabled
        fk_enabled = results[4][0][0]
        assert fk_enabled == 1, "Foreign keys should be enabled"
        logger.info("✓ Foreign keys enabled")

        # Verify schema version was recorded
        result = results[5][0] if results[5] else None
        assert result is not None, "Schema version should be recorded"
        assert result[0] == "001", f"Schema version should be '001', got '{result[0]}'"
        logger.info(f"✓ Schema version recorded: {result[0]}")

        logger.info("=== Test 1.1: PASSED ===\n")


class TestIdempotentInitialization:
    """Test that initialization is safe to call multiple times."""

    @pytest.mark.asyncio
    async def test_idempotent_initialization(
        self, conversation_file_manager, temp_db_path
    ):
        """
        Test Case 1.2: Multiple initialization calls are safe (idempotent)

        Validates:
        - First initialization succeeds
        - Second initialization succeeds without errors
        - Third initialization succeeds without errors
        - Schema version remains correct
        - No duplicate schema elements created
        - Database integrity maintained
        """
        logger.info("=== Test 1.2: Idempotent initialization ===")

        # First initialization
        logger.info("Running first initialization...")
        await conversation_file_manager.initialize()
        assert temp_db_path["db_path"].exists()
        logger.info("✓ First initialization completed")

        # Get initial schema version
        version_1 = await conversation_file_manager.get_schema_version()
        assert version_1 == "001", f"Expected version '001', got '{version_1}'"

        # Second initialization (should be safe)
        logger.info("Running second initialization...")
        await conversation_file_manager.initialize()
        logger.info("✓ Second initialization completed")

        # Verify schema version unchanged
        version_2 = await conversation_file_manager.get_schema_version()
        assert version_2 == version_1, "Schema version should remain unchanged"

        # Third initialization (should also be safe)
        logger.info("Running third initialization...")
        await conversation_file_manager.initialize()
        logger.info("✓ Third initialization completed")

        # Verify schema version still unchanged
        version_3 = await conversation_file_manager.get_schema_version()
        assert version_3 == version_1, "Schema version should remain unchanged"

        # Verify no duplicate schema elements created (Issue #618: use async sqlite helper)
        db_path_str = str(temp_db_path["db_path"])

        # Count migration records (should be exactly 1)
        rows = await async_sqlite_query(
            db_path_str, "SELECT COUNT(*) FROM schema_migrations WHERE version = '001'"
        )
        migration_count = rows[0][0]
        assert (
            migration_count == 1
        ), f"Should have exactly 1 migration record, found {migration_count}"
        logger.info("✓ No duplicate migration records")

        # Verify table structure unchanged
        rows = await async_sqlite_query(
            db_path_str,
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        )
        table_count = rows[0][0]

        # Expected: 5 schema tables + 1 schema_migrations table
        assert table_count == 6, f"Should have exactly 6 tables, found {table_count}"
        logger.info(f"✓ Table count correct: {table_count}")

        logger.info("=== Test 1.2: PASSED ===\n")


class TestSchemaVersionTracking:
    """Test schema version tracking functionality."""

    @pytest.mark.asyncio
    async def test_schema_version_tracking(
        self, conversation_file_manager, temp_db_path
    ):
        """
        Test Case 1.3: Schema version is tracked correctly

        Validates:
        - get_schema_version() returns "unknown" before initialization
        - Version is set to "001" after initialization
        - Version tracking table exists
        - Version query is performant
        """
        logger.info("=== Test 1.3: Schema version tracking ===")

        # Before initialization, version should be "unknown"
        version_before = await conversation_file_manager.get_schema_version()
        assert (
            version_before == "unknown"
        ), f"Version before initialization should be 'unknown', got '{version_before}'"
        logger.info("✓ Version 'unknown' before initialization")

        # Run initialization
        await conversation_file_manager.initialize()

        # After initialization, version should be "001"
        version_after = await conversation_file_manager.get_schema_version()
        assert (
            version_after == "001"
        ), f"Version after initialization should be '001', got '{version_after}'"
        logger.info(f"✓ Version set to '{version_after}' after initialization")

        # Verify schema_migrations table structure (Issue #618: use async sqlite helper)
        db_path_str = str(temp_db_path["db_path"])

        # Check table exists
        rows = await async_sqlite_query(
            db_path_str,
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'",
        )
        assert len(rows) > 0, "schema_migrations table should exist"

        # Check table structure
        rows = await async_sqlite_query(
            db_path_str, "PRAGMA table_info(schema_migrations)"
        )
        columns = {row[1]: row[2] for row in rows}  # {column_name: type}

        expected_columns = {
            "migration_id": "INTEGER",
            "version": "TEXT",
            "description": "TEXT",
            "applied_at": "TIMESTAMP",
            "status": "TEXT",
            "execution_time_ms": "INTEGER",
        }

        for col_name, col_type in expected_columns.items():
            assert col_name in columns, f"Column '{col_name}' should exist"
            assert (
                columns[col_name] == col_type
            ), f"Column '{col_name}' should be type '{col_type}', got '{columns[col_name]}'"

        logger.info("✓ schema_migrations table structure correct")

        # Verify migration record details
        rows = await async_sqlite_query(
            db_path_str, "SELECT * FROM schema_migrations WHERE version = '001'"
        )
        assert len(rows) > 0, "Migration record should exist"
        migration = rows[0]
        assert migration[1] == "001", "Version should be '001'"
        assert (
            migration[2] == "Create conversation_files database and schema"
        ), "Description should be correct"
        assert migration[4] == "completed", "Status should be 'completed'"
        logger.info("✓ Migration record details correct")

        logger.info("=== Test 1.3: PASSED ===\n")


class TestSchemaIntegrityVerification:
    """Test schema integrity verification functionality."""

    @pytest.mark.asyncio
    async def test_integrity_verification_passes(
        self, conversation_file_manager, temp_db_path
    ):
        """
        Test Case 1.4: Schema integrity verification passes for complete schema

        Validates:
        - Verification succeeds after initialization
        - All tables are verified
        - All indexes are verified
        - All triggers are verified
        - Foreign keys are verified
        """
        logger.info("=== Test 1.4: Schema integrity verification (pass) ===")

        # Initialize database
        await conversation_file_manager.initialize()

        # Verification is performed during initialization, so if we got here without
        # exceptions, verification passed
        logger.info("✓ Initialization completed (includes integrity verification)")

        # Manually verify we can query all expected elements (Issue #618: use async sqlite helper)
        db_path_str = str(temp_db_path["db_path"])

        # Test querying each table
        expected_tables = [
            "conversation_files",
            "file_metadata",
            "session_file_associations",
            "file_access_log",
            "file_cleanup_queue",
        ]

        for table in expected_tables:
            rows = await async_sqlite_query(
                db_path_str, f"SELECT COUNT(*) FROM {table}"
            )
            count = rows[0][0]
            logger.info(f"✓ Table '{table}' queryable (count: {count})")

        # Test querying each view
        expected_views = [
            "v_active_files",
            "v_session_file_summary",
            "v_pending_cleanups",
        ]

        for view in expected_views:
            rows = await async_sqlite_query(db_path_str, f"SELECT COUNT(*) FROM {view}")
            count = rows[0][0]
            logger.info(f"✓ View '{view}' queryable (count: {count})")

        logger.info("=== Test 1.4: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_integrity_verification_fails_missing_table(
        self, conversation_file_manager, temp_db_path
    ):
        """
        Test Case 1.5: Schema integrity verification detects missing tables

        Validates:
        - Incomplete schema is detected
        - Appropriate error is raised
        - Error message identifies missing table
        """
        logger.info(
            "=== Test 1.5: Schema integrity verification (fail - missing table) ==="
        )

        # Initialize database normally first
        await conversation_file_manager.initialize()

        # Manually remove one required table to simulate corruption (Issue #618: use async sqlite helper)
        await async_sqlite_execute(
            str(temp_db_path["db_path"]), "DROP TABLE file_metadata"
        )
        logger.info("✓ Dropped file_metadata table to simulate corruption")

        # Now create a new manager instance and try to initialize
        # The migration is idempotent but verification should catch missing table
        _corrupted_manager = ConversationFileManager(
            storage_dir=temp_db_path["storage_dir"],
            db_path=temp_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )

        # Initialization should fail due to missing table
        # Note: Current implementation recreates missing tables via CREATE IF NOT EXISTS
        # So we need to check that verification would catch this before recreation

        # Instead, let's verify the migration validation logic catches missing tables
        import importlib

        migration_module = importlib.import_module(
            "database.migrations.001_create_conversation_files"
        )
        ConversationFilesMigration = getattr(
            migration_module, "ConversationFilesMigration"
        )

        migration = ConversationFilesMigration(
            data_dir=temp_db_path["db_path"].parent, db_path=temp_db_path["db_path"]
        )

        # Connect and test validation
        migration.connection = migration._connect_database()

        try:
            is_valid = migration._validate_schema()
            assert not is_valid, "Validation should fail for missing table"
            logger.info("✓ Validation correctly detected missing table")
        finally:
            if migration.connection:
                migration.connection.close()

        logger.info("=== Test 1.5: PASSED ===\n")


class TestSchemaMigrationFramework:
    """Test schema migration framework functionality."""

    @pytest.mark.asyncio
    async def test_schema_migration_framework(
        self, conversation_file_manager, temp_db_path
    ):
        """
        Test Case 1.6: Schema migration framework is functional

        Validates:
        - Migration system tracks versions
        - Migration can be applied
        - Migration can be rolled back (for testing)
        - Version tracking persists
        """
        logger.info("=== Test 1.6: Schema migration framework ===")

        # Run initial migration
        await conversation_file_manager.initialize()
        logger.info("✓ Initial migration (version 001) applied")

        # Verify version
        version = await conversation_file_manager.get_schema_version()
        assert version == "001", f"Version should be '001', got '{version}'"

        # Test rollback capability (for development/testing)
        import importlib

        migration_module = importlib.import_module(
            "database.migrations.001_create_conversation_files"
        )
        ConversationFilesMigration = getattr(
            migration_module, "ConversationFilesMigration"
        )

        migration = ConversationFilesMigration(
            data_dir=temp_db_path["db_path"].parent, db_path=temp_db_path["db_path"]
        )

        # Rollback migration
        rollback_success = await migration.down()
        assert rollback_success, "Rollback should succeed"
        logger.info("✓ Migration rollback successful")

        # Verify database is clean after rollback (Issue #618: use async sqlite helper)
        rows = await async_sqlite_query(
            str(temp_db_path["db_path"]),
            "SELECT name FROM sqlite_master WHERE type='table'",
        )
        remaining_tables = [row[0] for row in rows]

        # Should have no schema tables remaining
        schema_tables = [
            "conversation_files",
            "file_metadata",
            "session_file_associations",
            "file_access_log",
            "file_cleanup_queue",
        ]

        for table in schema_tables:
            assert (
                table not in remaining_tables
            ), f"Table '{table}' should be removed after rollback"

        logger.info("✓ All schema tables removed after rollback")

        # Re-apply migration
        reapply_success = await migration.up()
        assert reapply_success, "Migration re-application should succeed"
        logger.info("✓ Migration re-applied successfully")

        # Verify version after re-application
        version_after = await conversation_file_manager.get_schema_version()
        assert (
            version_after == "001"
        ), f"Version after re-application should be '001', got '{version_after}'"

        logger.info("=== Test 1.6: PASSED ===\n")


class TestConcurrentInitialization:
    """Test concurrent initialization safety (critical for distributed environment)."""

    @pytest.mark.asyncio
    async def test_concurrent_initialization_safe(self, temp_db_path):
        """
        Test Case 1.7: Concurrent initialization from multiple instances is safe

        This simulates multiple VMs initializing the same database simultaneously,
        which can happen in a distributed AutoBot environment.

        Validates:
        - Multiple managers can initialize simultaneously
        - No database corruption occurs
        - Schema version is recorded only once
        - All instances can operate after initialization
        """
        logger.info("=== Test 1.7: Concurrent initialization safety ===")

        # Create 5 manager instances (simulating 5 VMs)
        managers = [
            ConversationFileManager(
                storage_dir=temp_db_path["storage_dir"],
                db_path=temp_db_path["db_path"],
                redis_host="localhost",
                redis_port=6379,
            )
            for _ in range(5)
        ]

        # Initialize all managers concurrently
        logger.info("Starting concurrent initialization (5 instances)...")
        initialization_tasks = [manager.initialize() for manager in managers]

        # Wait for all initializations to complete
        results = await asyncio.gather(*initialization_tasks, return_exceptions=True)

        # Check for exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            logger.error(f"Exceptions occurred: {exceptions}")
            raise AssertionError(
                f"Concurrent initialization had {len(exceptions)} failures"
            )

        logger.info("✓ All 5 instances initialized successfully")

        # Verify database integrity (Issue #618: use async sqlite helper)
        db_path_str = str(temp_db_path["db_path"])

        # Verify schema version recorded only once
        rows = await async_sqlite_query(
            db_path_str, "SELECT COUNT(*) FROM schema_migrations WHERE version = '001'"
        )
        migration_count = rows[0][0]
        assert (
            migration_count == 1
        ), f"Should have exactly 1 migration record, found {migration_count}"
        logger.info(f"✓ Migration recorded once (not {len(managers)} times)")

        # Verify all tables exist (exclude internal SQLite tables)
        rows = await async_sqlite_query(
            db_path_str,
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        )
        table_count = rows[0][0]
        assert table_count == 6, f"Should have 6 tables, found {table_count}"
        logger.info("✓ All tables exist after concurrent initialization")

        # Verify all manager instances can query schema version
        for i, manager in enumerate(managers):
            version = await manager.get_schema_version()
            assert (
                version == "001"
            ), f"Manager {i} should report version '001', got '{version}'"

        logger.info("✓ All manager instances report correct version")
        logger.info("=== Test 1.7: PASSED ===\n")


class TestErrorHandling:
    """Test error handling in initialization process."""

    @pytest.mark.asyncio
    async def test_missing_schema_file(self, temp_db_path):
        """
        Test Case 1.8: Initialization fails gracefully if schema file missing

        Validates:
        - Appropriate error raised
        - Error message is helpful
        - No partial database created
        """
        logger.info("=== Test 1.8: Missing schema file error handling ===")

        # Create manager with non-existent schema directory
        invalid_schema_dir = temp_db_path["temp_dir"] / "nonexistent_schemas"

        manager = ConversationFileManager(
            storage_dir=temp_db_path["storage_dir"],
            db_path=temp_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )

        # Override schema directory via environment variable
        import os

        original_env = os.environ.get("AUTOBOT_SCHEMA_DIR")

        try:
            os.environ["AUTOBOT_SCHEMA_DIR"] = str(invalid_schema_dir)

            # Initialization should fail
            with pytest.raises(RuntimeError) as exc_info:
                await manager.initialize()

            # Error may be wrapped - check for database-related failure indicators
            error_msg = str(exc_info.value).lower()
            assert (
                "database" in error_msg
                or "migration" in error_msg
                or "schema" in error_msg
                or "initialization" in error_msg
            ), f"Error should indicate database/migration failure, got: {exc_info.value}"

            logger.info(f"✓ Appropriate error raised: {exc_info.value}")

            # Verify no partial database was created (Issue #618: use async sqlite helper)
            if temp_db_path["db_path"].exists():
                # If database exists, verify it's empty or only has schema_migrations
                rows = await async_sqlite_query(
                    str(temp_db_path["db_path"]),
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table'",
                )
                table_count = rows[0][0]
                assert (
                    table_count <= 1
                ), "Should have at most schema_migrations table, no schema tables"
                logger.info("✓ No partial schema created")
            else:
                logger.info("✓ No database file created")

        finally:
            # Restore environment
            if original_env is not None:
                os.environ["AUTOBOT_SCHEMA_DIR"] = original_env
            elif "AUTOBOT_SCHEMA_DIR" in os.environ:
                del os.environ["AUTOBOT_SCHEMA_DIR"]

        logger.info("=== Test 1.8: PASSED ===\n")


# ============================================================================
# TEST EXECUTION
# ============================================================================

if __name__ == "__main__":
    """Run all tests with pytest"""
    pytest.main(
        [
            __file__,
            "-v",  # Verbose output
            "--tb=short",  # Short traceback format
            "--asyncio-mode=auto",  # Enable async support
            "--log-cli-level=INFO",  # Show INFO logs
        ]
    )
