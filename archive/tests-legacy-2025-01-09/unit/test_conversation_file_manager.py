#!/usr/bin/env python3
"""
Unit Tests for ConversationFileManager Database Initialization

Task 1.5: Comprehensive unit test coverage for database initialization system.

Test Coverage:
- Fresh database creation
- Schema completeness (5 tables + views + indexes + triggers)
- Idempotent initialization
- Schema version tracking
- Integrity verification
- Error handling
- Concurrent initialization safety
"""

import asyncio
import os
import pytest
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.conversation_file_manager import ConversationFileManager


class TestDatabaseInitialization:
    """Unit tests for database initialization."""

    @pytest.fixture
    async def temp_db_manager(self, tmp_path):
        """Create temporary ConversationFileManager for testing."""
        db_path = tmp_path / "test_conversation_files.db"
        storage_dir = tmp_path / "files"
        storage_dir.mkdir()

        manager = ConversationFileManager(
            storage_dir=storage_dir,
            db_path=db_path,
            redis_host="localhost",
            redis_port=6379
        )

        yield manager

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    async def initialized_db(self, temp_db_manager):
        """Pre-initialized database for testing."""
        await temp_db_manager.initialize()
        return temp_db_manager

    @pytest.mark.asyncio
    async def test_first_time_initialization(self, temp_db_manager):
        """Test fresh deployment creates database and schema."""
        # Database should not exist yet
        assert not temp_db_manager.db_path.exists()

        # Initialize
        await temp_db_manager.initialize()

        # Database should now exist
        assert temp_db_manager.db_path.exists()
        assert temp_db_manager.db_path.is_file()

    @pytest.mark.asyncio
    async def test_all_tables_created(self, temp_db_manager):
        """Test all 5 core tables + schema_migrations created."""
        await temp_db_manager.initialize()

        # Verify all tables exist
        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = {
            'conversation_files',
            'file_metadata',
            'session_file_associations',
            'file_access_log',
            'file_cleanup_queue',
            'schema_migrations'
        }

        assert expected_tables.issubset(set(tables)), f"Missing tables: {expected_tables - set(tables)}"

        conn.close()

    @pytest.mark.asyncio
    async def test_all_views_created(self, temp_db_manager):
        """Test all 3 views created."""
        await temp_db_manager.initialize()

        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
        views = [row[0] for row in cursor.fetchall()]

        expected_views = {
            'v_active_files',
            'v_session_file_summary',
            'v_pending_cleanups'
        }

        assert expected_views == set(views), f"Views mismatch. Expected: {expected_views}, Got: {set(views)}"

        conn.close()

    @pytest.mark.asyncio
    async def test_all_indexes_created(self, temp_db_manager):
        """Test all 8 performance indexes created."""
        await temp_db_manager.initialize()

        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()

        # Get user-created indexes (exclude auto-indexes)
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'
            ORDER BY name
        """)
        indexes = [row[0] for row in cursor.fetchall()]

        expected_indexes = {
            'idx_conversation_files_session',
            'idx_conversation_files_hash',
            'idx_conversation_files_uploaded_at',
            'idx_file_metadata_file_id',
            'idx_session_associations_session',
            'idx_session_associations_file',
            'idx_file_access_log_file',
            'idx_cleanup_queue_processed'
        }

        assert expected_indexes == set(indexes), f"Indexes mismatch. Expected: {expected_indexes}, Got: {set(indexes)}"

        conn.close()

    @pytest.mark.asyncio
    async def test_all_triggers_created(self, temp_db_manager):
        """Test all 3 triggers created."""
        await temp_db_manager.initialize()

        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")
        triggers = [row[0] for row in cursor.fetchall()]

        expected_triggers = {
            'trg_conversation_files_soft_delete',
            'trg_conversation_files_upload_log',
            'trg_session_association_cleanup_schedule'
        }

        assert expected_triggers == set(triggers), f"Triggers mismatch. Expected: {expected_triggers}, Got: {set(triggers)}"

        conn.close()

    @pytest.mark.asyncio
    async def test_foreign_keys_enabled(self, temp_db_manager):
        """Test foreign key constraints are enabled by _get_db_connection()."""
        await temp_db_manager.initialize()

        # Test that our _get_db_connection() method enables foreign keys
        conn = temp_db_manager._get_db_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]

        assert fk_enabled == 1, "Foreign keys should be enabled by _get_db_connection()"

        cursor.close()
        conn.close()

    @pytest.mark.asyncio
    async def test_idempotent_initialization(self, temp_db_manager):
        """Test subsequent initialize() calls skip initialization."""
        # First initialization
        await temp_db_manager.initialize()
        version1 = await temp_db_manager.get_schema_version()

        # Modify a table to detect if re-initialization happens
        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()
        cursor.execute("INSERT INTO schema_migrations (version, description) VALUES ('test', 'test entry')")
        conn.commit()
        conn.close()

        # Second initialization (should be safe/idempotent)
        await temp_db_manager.initialize()
        version2 = await temp_db_manager.get_schema_version()

        # Version should be the test entry we added (most recent)
        assert version2 == "test", "Idempotent initialization should not overwrite existing schema"

    @pytest.mark.asyncio
    async def test_schema_version_tracking(self, temp_db_manager):
        """Test schema version tracked correctly in schema_migrations."""
        await temp_db_manager.initialize()

        version = await temp_db_manager.get_schema_version()

        # Should have version "001" from migration
        assert version == "001", f"Expected version '001', got '{version}'"

    @pytest.mark.asyncio
    async def testget_schema_version_no_migrations(self, temp_db_manager):
        """Test get_schema_version returns 'unknown' for uninitialized DB."""
        # Create database but don't initialize
        conn = sqlite3.connect(str(temp_db_manager.db_path))
        conn.close()

        version = await temp_db_manager.get_schema_version()

        assert version == "unknown", "Should return 'unknown' when schema_migrations doesn't exist"

    @pytest.mark.asyncio
    async def test_initialization_creates_directories(self, tmp_path):
        """Test initialization creates storage directories if they don't exist."""
        # Create manager with non-existent directories
        storage_dir = tmp_path / "nested" / "storage" / "path"
        db_path = tmp_path / "nested" / "db" / "test.db"

        manager = ConversationFileManager(
            storage_dir=storage_dir,
            db_path=db_path,
            redis_host="localhost",
            redis_port=6379
        )

        # Directories should be created during init
        assert storage_dir.exists(), "Storage directory should be created during __init__"

        # Database directory should be created during initialize
        await manager.initialize()
        assert db_path.parent.exists(), "Database directory should be created during initialize"
        assert db_path.exists(), "Database file should be created"

    @pytest.mark.asyncio
    async def test_initialization_failure_handling(self, tmp_path):
        """Test initialization failure raises RuntimeError."""
        # Create manager with invalid schema path to force failure
        manager = ConversationFileManager(
            storage_dir=tmp_path / "storage",
            db_path=tmp_path / "test.db",
            redis_host="localhost",
            redis_port=6379
        )

        # Mock importlib to return a failing migration
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_migration_class = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.up.return_value = False  # Migration fails
            mock_migration_class.return_value = mock_instance
            mock_module.ConversationFilesMigration = mock_migration_class
            mock_import.return_value = mock_module

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="Database migration failed"):
                await manager.initialize()

    @pytest.mark.asyncio
    async def test_concurrent_initialization_safe(self, tmp_path):
        """Test multiple concurrent initialize() calls are safe."""
        db_path = tmp_path / "test_concurrent.db"
        storage_dir = tmp_path / "storage"

        # Create 3 managers pointing to same database
        managers = [
            ConversationFileManager(
                storage_dir=storage_dir,
                db_path=db_path,
                redis_host="localhost",
                redis_port=6379
            )
            for _ in range(3)
        ]

        # Initialize all concurrently
        results = await asyncio.gather(
            *[manager.initialize() for manager in managers],
            return_exceptions=True
        )

        # All should succeed or be idempotent (no exceptions raised)
        for result in results:
            assert not isinstance(result, Exception), f"Concurrent initialization failed: {result}"

        # Verify database is valid
        assert db_path.exists()

        # Verify schema is correct
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        conn.close()

        assert table_count >= 6, "Database should have all tables after concurrent initialization"


class TestSchemaValidation:
    """Tests for schema integrity verification."""

    @pytest.fixture
    async def temp_db_manager(self, tmp_path):
        """Create temporary ConversationFileManager for testing."""
        db_path = tmp_path / "test_conversation_files.db"
        storage_dir = tmp_path / "files"
        storage_dir.mkdir()

        manager = ConversationFileManager(
            storage_dir=storage_dir,
            db_path=db_path,
            redis_host="localhost",
            redis_port=6379
        )

        yield manager

    @pytest.mark.asyncio
    async def test_integrity_verification_complete_schema(self, temp_db_manager):
        """Test integrity verification passes with complete schema."""
        await temp_db_manager.initialize()

        # Verify schema is complete (initialize includes validation)
        version = await temp_db_manager.get_schema_version()
        assert version == "001", "Schema should be initialized successfully"

    @pytest.mark.asyncio
    async def test_detect_missing_table(self, temp_db_manager):
        """Test missing table detection during validation."""
        await temp_db_manager.initialize()

        # Drop one table to simulate incomplete schema
        conn = sqlite3.connect(str(temp_db_manager.db_path))
        conn.execute("DROP TABLE file_metadata")
        conn.close()

        # Re-initializing should detect the missing table and recreate it
        await temp_db_manager.initialize()

        # Verify table was recreated
        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_metadata'")
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "Missing table should be recreated during re-initialization"


class TestVersionTracking:
    """Tests for migration version tracking."""

    @pytest.fixture
    async def temp_db_manager(self, tmp_path):
        """Create temporary ConversationFileManager for testing."""
        db_path = tmp_path / "test_conversation_files.db"
        storage_dir = tmp_path / "files"
        storage_dir.mkdir()

        manager = ConversationFileManager(
            storage_dir=storage_dir,
            db_path=db_path,
            redis_host="localhost",
            redis_port=6379
        )

        yield manager

    @pytest.mark.asyncio
    async def test_version_recorded_after_initialization(self, temp_db_manager):
        """Test version is recorded in schema_migrations after initialization."""
        await temp_db_manager.initialize()

        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT version, description FROM schema_migrations ORDER BY applied_at DESC LIMIT 1")
        result = cursor.fetchone()

        conn.close()

        assert result is not None, "Migration version should be recorded"
        assert result[0] == "001", "Version should be '001'"
        assert "conversation_files" in result[1].lower(), "Description should mention conversation_files"

    @pytest.mark.asyncio
    async def test_multiple_initializations_single_version_entry(self, temp_db_manager):
        """Test multiple initializations don't create duplicate version entries."""
        # First initialization
        await temp_db_manager.initialize()

        # Count version entries
        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='001'")
        count1 = cursor.fetchone()[0]
        conn.close()

        # Second initialization
        await temp_db_manager.initialize()

        # Count again
        conn = sqlite3.connect(str(temp_db_manager.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='001'")
        count2 = cursor.fetchone()[0]
        conn.close()

        # Should have same count (idempotent - migration system uses UNIQUE constraint)
        assert count1 == count2, "Multiple initializations should not create duplicate version entries"


class TestErrorHandling:
    """Tests for error handling during initialization."""

    @pytest.mark.asyncio
    async def test_initialization_with_invalid_schema_path(self, tmp_path):
        """Test initialization fails gracefully with invalid schema path."""
        manager = ConversationFileManager(
            storage_dir=tmp_path / "storage",
            db_path=tmp_path / "test.db",
            redis_host="localhost",
            redis_port=6379
        )

        # Mock importlib to return a migration that raises FileNotFoundError
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_migration_class = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.up.side_effect = FileNotFoundError("Schema file not found")
            mock_migration_class.return_value = mock_instance
            mock_module.ConversationFilesMigration = mock_migration_class
            mock_import.return_value = mock_module

            # Should raise RuntimeError with helpful message
            with pytest.raises(RuntimeError, match="Database initialization failed"):
                await manager.initialize()

    @pytest.mark.asyncio
    async def test_initialization_with_database_corruption(self, tmp_path):
        """Test initialization handles database corruption."""
        db_path = tmp_path / "corrupt.db"

        # Create corrupt database file
        with open(db_path, 'wb') as f:
            f.write(b'corrupt data not a valid sqlite database')

        manager = ConversationFileManager(
            storage_dir=tmp_path / "storage",
            db_path=db_path,
            redis_host="localhost",
            redis_port=6379
        )

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Database initialization failed"):
            await manager.initialize()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--asyncio-mode=auto"])
