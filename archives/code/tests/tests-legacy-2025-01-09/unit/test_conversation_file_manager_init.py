"""
Unit Tests for ConversationFileManager Database Initialization

Tests for Week 1 - Task 1.5: Comprehensive Unit Testing
Tests cover database initialization, schema versioning, and integrity verification.

Coverage Target: 100% for initialization code
"""

import asyncio
import logging
import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.conversation_file_manager import ConversationFileManager
import importlib
# Dynamic import to handle numeric module name
_migration_module = importlib.import_module('database.migrations.001_create_conversation_files')
ConversationFilesMigration = getattr(_migration_module, 'ConversationFilesMigration')

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestConversationFileManagerInitialization:
    """Test database initialization functionality."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary database path for testing."""
        db_path = tmp_path / "test_conversation_files.db"
        return db_path

    @pytest.fixture
    def temp_storage_dir(self, tmp_path):
        """Create temporary storage directory for testing."""
        storage_dir = tmp_path / "test_storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir

    @pytest.fixture
    async def manager(self, temp_db_path, temp_storage_dir):
        """Create ConversationFileManager instance for testing."""
        manager = ConversationFileManager(
            storage_dir=temp_storage_dir,
            db_path=temp_db_path,
            redis_host="172.16.168.23",
            redis_port=6379
        )
        yield manager
        # Cleanup
        if temp_db_path.exists():
            temp_db_path.unlink()

    @pytest.mark.asyncio
    async def test_first_time_initialization(self, manager, temp_db_path):
        """
        Test Case 1: First-time database initialization.

        Verifies that:
        - Database file is created
        - All required tables are created
        - Schema version is recorded
        - No errors occur
        """
        logger.info("TEST 1: First-time initialization")

        # Verify database doesn't exist yet
        assert not temp_db_path.exists(), "Database should not exist before initialization"

        # Initialize database
        await manager.initialize()

        # Verify database was created
        assert temp_db_path.exists(), "Database file should be created"

        # Verify schema version was set
        version = await manager.get_schema_version()
        assert version is not None, "Schema version should be set"
        assert version != "unknown", "Schema version should not be unknown"
        logger.info(f"✅ Schema version set to: {version}")

        # Verify all required tables exist
        connection = sqlite3.connect(str(temp_db_path))
        cursor = connection.cursor()

        required_tables = [
            'conversation_files',
            'file_metadata',
            'session_file_associations',
            'file_access_log',
            'file_cleanup_queue',
            'schema_migrations'
        ]

        for table in required_tables:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            result = cursor.fetchone()
            assert result is not None, f"Table {table} should exist"
            logger.info(f"✅ Table '{table}' created successfully")

        connection.close()
        logger.info("✅ TEST 1 PASSED: First-time initialization successful")

    @pytest.mark.asyncio
    async def test_idempotent_initialization(self, manager, temp_db_path):
        """
        Test Case 2: Idempotent initialization (safe to call multiple times).

        Verifies that:
        - Calling initialize() multiple times is safe
        - No duplicate tables are created
        - No errors occur
        - Schema version remains consistent
        """
        logger.info("TEST 2: Idempotent initialization")

        # Initialize database first time
        await manager.initialize()
        first_version = await manager.get_schema_version()
        logger.info(f"First initialization - Schema version: {first_version}")

        # Get table count after first initialization
        connection = sqlite3.connect(str(temp_db_path))
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count_first = cursor.fetchone()[0]
        connection.close()

        # Initialize again (should be safe)
        await manager.initialize()
        second_version = await manager.get_schema_version()
        logger.info(f"Second initialization - Schema version: {second_version}")

        # Verify version is consistent
        assert first_version == second_version, "Schema version should remain consistent"

        # Verify table count hasn't changed (no duplicates)
        connection = sqlite3.connect(str(temp_db_path))
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count_second = cursor.fetchone()[0]
        connection.close()

        assert table_count_first == table_count_second, "Table count should not change"
        logger.info(f"✅ Table count consistent: {table_count_first}")

        # Third initialization for good measure
        await manager.initialize()
        third_version = await manager.get_schema_version()
        assert third_version == first_version, "Schema version should still be consistent"

        logger.info("✅ TEST 2 PASSED: Idempotent initialization verified")

    @pytest.mark.asyncio
    async def test_schema_version_tracking(self, manager, temp_db_path):
        """
        Test Case 3: Schema version tracking.

        Verifies that:
        - Schema version is recorded in database
        - Version is retrievable
        - Version format is correct
        - Migration table tracks version correctly
        """
        logger.info("TEST 3: Schema version tracking")

        # Initialize database
        await manager.initialize()

        # Get schema version
        version = await manager.get_schema_version()
        logger.info(f"Retrieved schema version: {version}")

        # Verify version is not unknown
        assert version != "unknown", "Schema version should be set"

        # Verify version is in correct format (e.g., "001")
        assert isinstance(version, str), "Version should be a string"
        assert len(version) > 0, "Version should not be empty"

        # Verify migration tracking table exists and has entry
        connection = sqlite3.connect(str(temp_db_path))
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM schema_migrations")
        migration_count = cursor.fetchone()[0]
        assert migration_count > 0, "Migration table should have at least one entry"
        logger.info(f"✅ Migration table has {migration_count} entries")

        # Verify the specific migration is recorded
        cursor.execute(
            "SELECT version, description, status FROM schema_migrations WHERE version=?",
            (version,)
        )
        migration_record = cursor.fetchone()
        assert migration_record is not None, "Migration record should exist"

        migration_version, description, status = migration_record
        assert migration_version == version, "Migration version should match"
        assert status == "completed", "Migration status should be completed"
        logger.info(f"✅ Migration record: {migration_version} - {description} ({status})")

        connection.close()
        logger.info("✅ TEST 3 PASSED: Schema version tracking verified")

    @pytest.mark.asyncio
    async def test_integrity_verification_passes(self, manager, temp_db_path):
        """
        Test Case 4: Schema integrity verification passes with complete schema.

        Verifies that:
        - Complete schema passes integrity check
        - All tables are validated
        - All views are validated
        - All indexes are validated
        - All triggers are validated
        """
        logger.info("TEST 4: Integrity verification with complete schema")

        # Initialize database (creates complete schema)
        await manager.initialize()

        # Use migration's validation method to verify schema integrity
        migration = ConversationFilesMigration(
            data_dir=temp_db_path.parent,
            schema_dir=Path("/home/kali/Desktop/AutoBot/database/schemas"),
            db_path=temp_db_path
        )

        # Connect and validate
        migration.connection = migration._connect_database()

        try:
            # Validate schema using migration's comprehensive validation
            is_valid = migration._validate_schema()
            assert is_valid, "Schema integrity validation should pass"
            logger.info("✅ Schema integrity verification passed")

            # Verify specific components
            cursor = migration.connection.cursor()

            # Check tables count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]
            assert table_count >= 6, f"Should have at least 6 tables, found {table_count}"
            logger.info(f"✅ Found {table_count} tables")

            # Check views count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='view'")
            view_count = cursor.fetchone()[0]
            assert view_count >= 3, f"Should have at least 3 views, found {view_count}"
            logger.info(f"✅ Found {view_count} views")

            # Check indexes count (excluding auto-generated ones)
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
            index_count = cursor.fetchone()[0]
            assert index_count >= 8, f"Should have at least 8 indexes, found {index_count}"
            logger.info(f"✅ Found {index_count} indexes")

            # Check triggers count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'")
            trigger_count = cursor.fetchone()[0]
            assert trigger_count >= 3, f"Should have at least 3 triggers, found {trigger_count}"
            logger.info(f"✅ Found {trigger_count} triggers")

            cursor.close()

        finally:
            migration.connection.close()

        logger.info("✅ TEST 4 PASSED: Complete schema integrity verified")

    @pytest.mark.asyncio
    async def test_integrity_verification_fails_missing_table(self, temp_db_path, temp_storage_dir):
        """
        Test Case 5: Schema integrity verification fails when tables are missing.

        Verifies that:
        - Missing tables are detected
        - Validation fails appropriately
        - Error handling is correct
        """
        logger.info("TEST 5: Integrity verification with missing tables")

        # Create database with incomplete schema (only some tables)
        connection = sqlite3.connect(str(temp_db_path))
        cursor = connection.cursor()

        # Create only schema_migrations and conversation_files tables (missing others)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'completed'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_files (
                file_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_hash TEXT NOT NULL,
                mime_type TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_deleted INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            INSERT INTO schema_migrations (version, description, status)
            VALUES ('001', 'Incomplete test schema', 'completed')
        """)

        connection.commit()
        connection.close()

        logger.info("Created incomplete database with only 2 tables")

        # Try to validate incomplete schema
        migration = ConversationFilesMigration(
            data_dir=temp_db_path.parent,
            schema_dir=Path("/home/kali/Desktop/AutoBot/database/schemas"),
            db_path=temp_db_path
        )

        migration.connection = migration._connect_database()

        try:
            # Validation should fail due to missing tables
            is_valid = migration._validate_schema()
            assert not is_valid, "Validation should fail with incomplete schema"
            logger.info("✅ Validation correctly failed for incomplete schema")

        finally:
            migration.connection.close()

        logger.info("✅ TEST 5 PASSED: Missing table detection verified")

    @pytest.mark.asyncio
    async def test_schema_migration_framework(self, manager, temp_db_path):
        """
        Test Case 6: Schema migration framework functionality.

        Verifies that:
        - Migration system tracks versions
        - Migration can be executed multiple times safely
        - Migration table structure is correct
        - Future migrations will be supported
        """
        logger.info("TEST 6: Schema migration framework")

        # Initialize database (runs migration 001)
        await manager.initialize()

        # Verify migration tracking table structure
        connection = sqlite3.connect(str(temp_db_path))
        cursor = connection.cursor()

        # Check schema_migrations table structure
        cursor.execute("PRAGMA table_info(schema_migrations)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        expected_columns = ['migration_id', 'version', 'description', 'applied_at', 'status']
        for expected_col in expected_columns:
            assert expected_col in column_names, f"Column '{expected_col}' should exist in schema_migrations"
        logger.info(f"✅ Migration table has all required columns: {column_names}")

        # Verify migration record
        cursor.execute("SELECT * FROM schema_migrations ORDER BY migration_id")
        migrations = cursor.fetchall()
        assert len(migrations) > 0, "Should have at least one migration record"

        for migration in migrations:
            migration_id, version, description, applied_at, status, *rest = migration
            logger.info(f"  Migration: {version} - {description} (status: {status})")
            assert status == "completed", f"Migration {version} should be completed"

        # Verify idempotent migration execution
        # Run initialize again - should not create duplicate migration records
        await manager.initialize()

        cursor.execute("SELECT COUNT(*) FROM schema_migrations")
        migration_count_after = cursor.fetchone()[0]
        assert migration_count_after == len(migrations), "Should not create duplicate migration records"
        logger.info(f"✅ Migration count remains {migration_count_after} (no duplicates)")

        connection.close()

        logger.info("✅ TEST 6 PASSED: Migration framework functionality verified")


# Test execution and coverage reporting
if __name__ == "__main__":
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--cov=src.conversation_file_manager",
        "--cov-report=term-missing",
        "--cov-report=html:tests/results/coverage_unit_init"
    ])
