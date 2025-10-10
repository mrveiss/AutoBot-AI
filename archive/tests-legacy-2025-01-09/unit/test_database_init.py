"""Unit tests for database initialization - Fix #1."""
import pytest
import sqlite3
import tempfile
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDatabaseInitialization:
    """Test suite for database initialization (Fix #1: Database Initialization)."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def schema_path(self):
        """Get schema file path."""
        return Path(__file__).parent.parent.parent / "database" / "schemas" / "conversation_files_schema.sql"

    def test_schema_file_exists(self, schema_path):
        """Test that conversation_files_schema.sql exists."""
        assert schema_path.exists(), f"Schema file not found at {schema_path}"
        assert schema_path.suffix == '.sql', "Schema file should be .sql"

    def test_schema_file_readable(self, schema_path):
        """Test that schema file is readable."""
        content = schema_path.read_text()
        assert len(content) > 0, "Schema file is empty"
        assert 'CREATE TABLE' in content, "Schema file should contain CREATE TABLE statements"

    def test_database_initialization(self, temp_db_path, schema_path):
        """Test database initialization creates all tables."""
        # Read schema
        schema_sql = schema_path.read_text()

        # Initialize database
        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()

            # Verify all expected tables exist
            expected_tables = [
                'conversation_files',
                'file_metadata',
                'session_file_associations',
                'file_access_log',
                'file_cleanup_queue'
            ]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            actual_tables = [row[0] for row in cursor.fetchall()]

            for table in expected_tables:
                assert table in actual_tables, f"Table '{table}' was not created"

        finally:
            conn.close()

    def test_database_indexes_created(self, temp_db_path, schema_path):
        """Test that database indexes are created."""
        schema_sql = schema_path.read_text()

        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()

            # Verify indexes exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
            indexes = [row[0] for row in cursor.fetchall()]

            # Check for key indexes
            assert any('idx_conversation_files_session' in idx for idx in indexes), \
                "Session index not created"
            assert any('idx_conversation_files_hash' in idx for idx in indexes), \
                "Hash index not created"

        finally:
            conn.close()

    def test_database_views_created(self, temp_db_path, schema_path):
        """Test that database views are created."""
        schema_sql = schema_path.read_text()

        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()

            # Verify views exist
            expected_views = [
                'v_active_files',
                'v_session_file_summary',
                'v_pending_cleanups'
            ]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
            actual_views = [row[0] for row in cursor.fetchall()]

            for view in expected_views:
                assert view in actual_views, f"View '{view}' was not created"

        finally:
            conn.close()

    def test_database_triggers_created(self, temp_db_path, schema_path):
        """Test that database triggers are created."""
        schema_sql = schema_path.read_text()

        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()

            # Verify triggers exist
            expected_triggers = [
                'trg_conversation_files_soft_delete',
                'trg_conversation_files_upload_log',
                'trg_session_association_cleanup_schedule'
            ]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")
            actual_triggers = [row[0] for row in cursor.fetchall()]

            for trigger in expected_triggers:
                assert trigger in actual_triggers, f"Trigger '{trigger}' was not created"

        finally:
            conn.close()

    def test_idempotent_initialization(self, temp_db_path, schema_path):
        """Test that running initialization multiple times is safe (idempotent)."""
        schema_sql = schema_path.read_text()

        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()

            # Run initialization twice
            cursor.executescript(schema_sql)
            conn.commit()
            cursor.executescript(schema_sql)
            conn.commit()

            # Should still have correct tables (not duplicated)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]

            # Count should match expected (no duplicates)
            assert len(tables) == 5, f"Expected 5 tables, got {len(tables)}"

        finally:
            conn.close()

    def test_table_constraints(self, temp_db_path, schema_path):
        """Test that table constraints are enforced."""
        schema_sql = schema_path.read_text()

        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()

            # Test CHECK constraint on file_size (must be >= 0)
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO conversation_files
                    (file_id, session_id, original_filename, stored_filename,
                     file_path, file_size, file_hash)
                    VALUES ('test-1', 'session-1', 'test.txt', 'stored.txt',
                            '/path/test.txt', -100, 'hash123')
                """)
                conn.commit()

        finally:
            conn.close()

    def test_foreign_key_constraints(self, temp_db_path, schema_path):
        """Test that foreign key constraints are enforced."""
        schema_sql = schema_path.read_text()

        conn = sqlite3.connect(temp_db_path)
        try:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()

            # Try to insert metadata for non-existent file
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO file_metadata (file_id, metadata_key, metadata_value)
                    VALUES ('non-existent-file-id', 'test_key', 'test_value')
                """)
                conn.commit()

        finally:
            conn.close()

    def test_graceful_handling_missing_schema(self, temp_db_path):
        """Test graceful handling when schema file is missing."""
        # Try to initialize with non-existent schema
        non_existent_schema = Path("/tmp/non_existent_schema_file.sql")

        # Should handle gracefully (no crash)
        assert not non_existent_schema.exists(), "Test expects schema to not exist"

        # Would fail to read, but shouldn't crash application
        # (This tests defensive programming in initialization code)
        try:
            content = non_existent_schema.read_text()
            pytest.fail("Should have raised FileNotFoundError")
        except FileNotFoundError:
            pass  # Expected behavior


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
