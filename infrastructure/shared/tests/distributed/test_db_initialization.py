"""
Distributed Integration Tests for ConversationFileManager Database Initialization

Tests cross-VM database initialization scenarios for AutoBot's distributed architecture.

Environment Setup:
- Main Machine (VM0): 172.16.168.20 - Backend API + Desktop/Terminal VNC
- VM1 Frontend: 172.16.168.21:5173 - Web interface
- VM2 NPU Worker: 172.16.168.22:8081 - Hardware AI acceleration
- VM3 Redis: 172.16.168.23:6379 - Data layer
- VM4 AI Stack: 172.16.168.24:8080 - AI processing
- VM5 Browser: 172.16.168.25:3000 - Web automation

These tests validate:
- Fresh VM deployment creates database automatically
- Cross-VM file operations work correctly
- Concurrent initialization from multiple VMs is safe
- No race conditions or corruption in distributed environment

Test Coverage: Distributed multi-VM scenarios
"""

import asyncio
import logging
import sqlite3
import tempfile
import uuid
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


# Integration test marker
pytestmark = pytest.mark.integration


@pytest.fixture
def shared_db_path():
    """
    Create a shared database path simulating network storage accessible by all VMs.

    In production, this would be a network-mounted directory (NFS/CIFS).
    For testing, we use a temporary directory accessible by all test instances.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "conversation_files.db"
        storage_dir = Path(temp_dir) / "storage"
        storage_dir.mkdir()

        logger.info(f"Created shared storage at: {temp_dir}")

        yield {
            "db_path": db_path,
            "storage_dir": storage_dir,
            "temp_dir": Path(temp_dir),
        }

        logger.info("Cleaning up shared storage")


class TestFreshVMDeployment:
    """Test fresh VM deployment scenario."""

    @pytest.mark.asyncio
    async def test_fresh_vm0_deployment(self, shared_db_path):
        """
        Test Case 2.1: Fresh Main Machine (VM0) deployment creates schema automatically

        Scenario:
        1. AutoBot is deployed to fresh VM0 (main machine)
        2. Backend starts and initializes ConversationFileManager
        3. Database schema is created automatically
        4. Backend can handle file operations immediately

        Validates:
        - Database is created automatically during backend startup
        - No manual intervention required
        - All schema elements present
        - Backend is ready to accept file uploads
        """
        logger.info("=== Test 2.1: Fresh VM0 deployment ===")

        # Verify database doesn't exist initially (fresh deployment)
        assert not shared_db_path[
            "db_path"
        ].exists(), "Database should not exist on fresh deployment"
        logger.info("✓ Fresh deployment confirmed (no existing database)")

        # Create ConversationFileManager instance (simulating backend startup on VM0)
        manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )

        # Initialize database (this happens during backend startup)
        await manager.initialize()
        logger.info("✓ Database initialized during backend startup")

        # Verify database was created
        assert shared_db_path[
            "db_path"
        ].exists(), "Database should be created after initialization"

        # Verify schema is complete (Issue #618: use async sqlite helper)
        db_path_str = str(shared_db_path["db_path"])

        # Check all required tables exist
        expected_tables = {
            "conversation_files",
            "file_metadata",
            "session_file_associations",
            "file_access_log",
            "file_cleanup_queue",
            "schema_migrations",
        }

        rows = await async_sqlite_query(
            db_path_str, "SELECT name FROM sqlite_master WHERE type='table'"
        )
        actual_tables = {row[0] for row in rows}

        missing_tables = expected_tables - actual_tables
        assert not missing_tables, f"Missing tables: {missing_tables}"
        logger.info(f"✓ All {len(expected_tables)} tables created")

        # Verify schema version
        rows = await async_sqlite_query(
            db_path_str,
            "SELECT version FROM schema_migrations ORDER BY migration_id DESC LIMIT 1",
        )
        version = rows[0][0]
        assert version == "001", f"Schema version should be '001', got '{version}'"
        logger.info(f"✓ Schema version: {version}")

        # Test that backend can handle file operations immediately
        test_session_id = f"test_session_{uuid.uuid4()}"
        test_content = b"Test file content from VM0"

        try:
            result = await manager.add_file(
                session_id=test_session_id,
                file_content=test_content,
                original_filename="test_vm0.txt",
                mime_type="text/plain",
                uploaded_by="vm0_test",
            )

            assert result["file_id"] is not None, "File should be uploaded successfully"
            assert result["session_id"] == test_session_id
            logger.info(f"✓ File uploaded successfully: {result['file_id']}")

            # Verify file was stored
            file_path = Path(result["file_path"])
            assert file_path.exists(), "Physical file should exist"
            assert file_path.read_bytes() == test_content, "File content should match"
            logger.info("✓ Physical file verified")

        finally:
            # Cleanup test files
            await manager.delete_session_files(test_session_id, hard_delete=True)

        logger.info("=== Test 2.1: PASSED ===\n")


class TestNPUWorkerIntegration:
    """Test NPU Worker (VM2) file upload integration."""

    @pytest.mark.asyncio
    async def test_npu_worker_file_upload(self, shared_db_path):
        """
        Test Case 2.2: NPU Worker (VM2) file upload works correctly

        Scenario:
        1. NPU Worker receives processing request
        2. Processes data (e.g., image recognition, hardware AI acceleration)
        3. Uploads result file to shared storage
        4. Database records file metadata

        Validates:
        - NPU Worker can write to shared database
        - File is accessible from other VMs
        - Metadata is correctly recorded
        """
        logger.info("=== Test 2.2: NPU Worker file upload ===")

        # Initialize database first (simulating VM0 already started)
        vm0_manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )
        await vm0_manager.initialize()
        logger.info("✓ Database initialized by VM0")

        # Create NPU Worker manager instance (VM2)
        npu_manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )

        # NPU Worker doesn't need to initialize (database already exists)
        # It just starts using the existing database
        session_id = f"npu_session_{uuid.uuid4()}"

        # Simulate NPU processing result
        processed_result = b"NPU processed image data: [binary data would be here]"

        result = await npu_manager.add_file(
            session_id=session_id,
            file_content=processed_result,
            original_filename="npu_processed_image.bin",
            mime_type="application/octet-stream",
            uploaded_by="npu_worker_vm2",
            metadata={
                "source": "npu_worker",
                "vm_id": "172.16.168.22",
                "processing_time_ms": 150,
            },
        )

        assert result["file_id"] is not None
        logger.info(f"✓ NPU Worker uploaded file: {result['file_id']}")

        # Verify file can be retrieved by other VMs (e.g., VM0 backend)
        files = await vm0_manager.get_session_files(session_id)
        assert len(files) == 1, "Should have exactly 1 file"
        assert files[0]["uploaded_by"] == "npu_worker_vm2"
        assert files[0]["file_size"] == len(processed_result)
        logger.info("✓ File accessible from VM0 backend")

        # Verify metadata was recorded (Issue #618: use async sqlite helper)
        rows = await async_sqlite_query(
            str(shared_db_path["db_path"]),
            """
            SELECT metadata_key, metadata_value
            FROM file_metadata
            WHERE file_id = ?
            """,
            (result["file_id"],),
        )

        metadata = {row[0]: row[1] for row in rows}
        assert metadata["source"] == "npu_worker"
        assert metadata["vm_id"] == "172.16.168.22"
        logger.info("✓ Metadata correctly recorded")

        # Cleanup
        await npu_manager.delete_session_files(session_id, hard_delete=True)

        logger.info("=== Test 2.2: PASSED ===\n")


class TestBrowserScreenshotSave:
    """Test Browser (VM5) screenshot save integration."""

    @pytest.mark.asyncio
    async def test_browser_screenshot_save(self, shared_db_path):
        """
        Test Case 2.3: Browser (VM5) screenshot save works correctly

        Scenario:
        1. Browser VM captures screenshot during automation
        2. Saves screenshot to shared storage
        3. Associates screenshot with chat session
        4. Screenshot can be retrieved by frontend

        Validates:
        - Browser VM can write to shared database
        - Large files (images) are handled correctly
        - File deduplication works across VMs
        """
        logger.info("=== Test 2.3: Browser screenshot save ===")

        # Initialize database (VM0)
        vm0_manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )
        await vm0_manager.initialize()

        # Create Browser manager instance (VM5)
        browser_manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )

        session_id = f"browser_session_{uuid.uuid4()}"

        # Simulate screenshot capture (1KB fake PNG data)
        fake_screenshot = b"\x89PNG\r\n\x1a\n" + b"fake_png_data" * 100

        result = await browser_manager.add_file(
            session_id=session_id,
            file_content=fake_screenshot,
            original_filename="webpage_screenshot.png",
            mime_type="image/png",
            uploaded_by="browser_vm5",
            metadata={
                "source": "playwright_browser",
                "vm_id": "172.16.168.25",
                "url": "https://example.com",
                "viewport": "1920x1080",
            },
        )

        assert result["file_id"] is not None
        assert result["mime_type"] == "image/png"
        logger.info(f"✓ Browser saved screenshot: {result['file_id']}")

        # Test file deduplication: Upload same screenshot again (different session)
        session_id_2 = f"browser_session_{uuid.uuid4()}_duplicate"

        result_2 = await browser_manager.add_file(
            session_id=session_id_2,
            file_content=fake_screenshot,  # Same content
            original_filename="webpage_screenshot_copy.png",  # Different name
            mime_type="image/png",
            uploaded_by="browser_vm5",
        )

        # Should reference existing file (deduplication)
        assert result_2["deduplicated"] is True, "Should deduplicate identical files"
        assert result_2["file_hash"] == result["file_hash"], "Hash should match"
        logger.info("✓ File deduplication works across uploads")

        # Verify file can be retrieved from frontend (VM1)
        frontend_manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )

        files = await frontend_manager.get_session_files(session_id)
        assert len(files) == 1
        assert files[0]["mime_type"] == "image/png"
        logger.info("✓ Screenshot accessible from frontend")

        # Cleanup
        await browser_manager.delete_session_files(session_id, hard_delete=True)
        await browser_manager.delete_session_files(session_id_2, hard_delete=True)

        logger.info("=== Test 2.3: PASSED ===\n")


class TestFrontendFileUpload:
    """Test Frontend (VM1) file upload integration."""

    @pytest.mark.asyncio
    async def test_frontend_file_upload(self, shared_db_path):
        """
        Test Case 2.4: Frontend (VM1) file upload succeeds

        Scenario:
        1. User uploads file through frontend web interface
        2. Frontend sends file to backend (VM0)
        3. Backend stores file and records metadata
        4. File can be accessed in chat session

        Validates:
        - Frontend → Backend file upload works
        - Session association is correct
        - File is immediately accessible in chat
        """
        logger.info("=== Test 2.4: Frontend file upload ===")

        # Initialize database (VM0)
        backend_manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )
        await backend_manager.initialize()

        session_id = f"frontend_session_{uuid.uuid4()}"
        message_id = f"msg_{uuid.uuid4()}"

        # Simulate user uploading file through frontend
        user_file_content = b"User uploaded document content\nMultiple lines\nWith data"

        result = await backend_manager.add_file(
            session_id=session_id,
            file_content=user_file_content,
            original_filename="user_document.txt",
            mime_type="text/plain",
            uploaded_by="user_12345",
            message_id=message_id,
            metadata={
                "upload_source": "frontend_web",
                "vm_id": "172.16.168.21",
                "ip_address": "192.168.1.100",
            },
        )

        assert result["file_id"] is not None
        logger.info(f"✓ Frontend uploaded file: {result['file_id']}")

        # Verify session association (Issue #618: use async sqlite helper)
        rows = await async_sqlite_query(
            str(shared_db_path["db_path"]),
            """
            SELECT association_type, message_id
            FROM session_file_associations
            WHERE file_id = ? AND session_id = ?
            """,
            (result["file_id"], session_id),
        )

        assert len(rows) > 0, "Association should exist"
        association = rows[0]
        assert association[0] == "upload", "Association type should be 'upload'"
        assert association[1] == message_id, "Message ID should match"
        logger.info("✓ Session association correct")

        # Verify file is immediately accessible in chat session
        session_files = await backend_manager.get_session_files(session_id)
        assert len(session_files) == 1
        assert session_files[0]["message_id"] == message_id
        logger.info("✓ File immediately accessible in chat")

        # Cleanup
        await backend_manager.delete_session_files(session_id, hard_delete=True)

        logger.info("=== Test 2.4: PASSED ===\n")


class TestConcurrentVMInitialization:
    """Test concurrent initialization from multiple VMs."""

    @pytest.mark.asyncio
    async def test_concurrent_initialization_safe(self, shared_db_path):
        """
        Test Case 2.5: Concurrent initialization from multiple VMs is safe

        Scenario:
        1. All 6 VMs start simultaneously (system restart scenario)
        2. Each VM's ConversationFileManager initializes
        3. Only one VM successfully creates schema
        4. Other VMs safely skip initialization
        5. All VMs can operate normally

        This is CRITICAL for production deployments where:
        - VMs may restart independently
        - Network partitions may cause initialization retries
        - Race conditions could corrupt database

        Validates:
        - No database corruption during concurrent initialization
        - Schema version recorded only once
        - All VMs report correct schema version
        - File operations work from all VMs after initialization
        """
        logger.info("=== Test 2.5: Concurrent VM initialization safety ===")

        # Create manager instances for all 6 VMs
        vm_names = [
            "VM0_Main_172.16.168.20",
            "VM1_Frontend_172.16.168.21",
            "VM2_NPU_172.16.168.22",
            "VM3_Redis_172.16.168.23",
            "VM4_AIStack_172.16.168.24",
            "VM5_Browser_172.16.168.25",
        ]

        managers = {
            vm_name: ConversationFileManager(
                storage_dir=shared_db_path["storage_dir"],
                db_path=shared_db_path["db_path"],
                redis_host="localhost",
                redis_port=6379,
            )
            for vm_name in vm_names
        }

        logger.info(f"Created {len(managers)} VM manager instances")

        # Initialize all managers concurrently (simulating simultaneous VM startup)
        logger.info("Starting concurrent initialization from all 6 VMs...")

        initialization_tasks = [manager.initialize() for manager in managers.values()]

        # Wait for all initializations to complete
        results = await asyncio.gather(*initialization_tasks, return_exceptions=True)

        # Check for exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            logger.error(f"Exceptions during initialization: {exceptions}")
            raise AssertionError(
                f"Concurrent initialization had {len(exceptions)} failures: {exceptions}"
            )

        logger.info("✓ All 6 VMs initialized successfully without errors")

        # Verify database integrity (Issue #618: use async sqlite helper)
        db_path_str = str(shared_db_path["db_path"])

        # Critical check: Schema version should be recorded ONLY ONCE
        rows = await async_sqlite_query(
            db_path_str, "SELECT COUNT(*) FROM schema_migrations WHERE version = '001'"
        )
        migration_count = rows[0][0]
        assert (
            migration_count == 1
        ), f"Schema version should be recorded once, found {migration_count} records"
        logger.info("✓ Schema version recorded exactly once (no race condition)")

        # Verify all tables exist (no corruption)
        rows = await async_sqlite_query(
            db_path_str, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        )
        table_count = rows[0][0]
        assert table_count == 6, f"Should have 6 tables, found {table_count}"
        logger.info("✓ All tables exist (no corruption during concurrent init)")

        # Verify foreign keys are enabled
        rows = await async_sqlite_query(db_path_str, "PRAGMA foreign_keys")
        fk_enabled = rows[0][0]
        assert fk_enabled == 1, "Foreign keys should be enabled"
        logger.info("✓ Foreign keys enabled correctly")

        # Verify all VM managers can query schema version correctly
        for vm_name, manager in managers.items():
            version = await manager.get_schema_version()
            assert (
                version == "001"
            ), f"{vm_name} should report version '001', got '{version}'"

        logger.info("✓ All VMs report correct schema version")

        # Critical test: Verify all VMs can perform file operations
        test_session = f"concurrent_test_{uuid.uuid4()}"

        # Each VM uploads a file concurrently
        upload_tasks = [
            manager.add_file(
                session_id=test_session,
                file_content=f"Test from {vm_name}".encode(),
                original_filename=f"test_{vm_name}.txt",
                mime_type="text/plain",
                uploaded_by=vm_name,
            )
            for vm_name, manager in managers.items()
        ]

        upload_results = await asyncio.gather(*upload_tasks, return_exceptions=True)

        # Check upload results
        upload_exceptions = [r for r in upload_results if isinstance(r, Exception)]
        if upload_exceptions:
            logger.error(f"Upload exceptions: {upload_exceptions}")
            raise AssertionError(f"File uploads failed: {upload_exceptions}")

        logger.info(f"✓ All {len(managers)} VMs successfully uploaded files")

        # Verify all files are recorded correctly
        any_manager = list(managers.values())[0]
        session_files = await any_manager.get_session_files(test_session)
        assert len(session_files) == len(
            managers
        ), f"Should have {len(managers)} files, found {len(session_files)}"
        logger.info(f"✓ All {len(session_files)} files recorded correctly")

        # Cleanup
        await any_manager.delete_session_files(test_session, hard_delete=True)

        logger.info("=== Test 2.5: PASSED ===\n")


class TestDatabaseRecovery:
    """Test database recovery scenarios."""

    @pytest.mark.asyncio
    async def test_database_recovery_after_corruption(self, shared_db_path):
        """
        Test Case 2.6: Database recovery after corruption

        Scenario:
        1. Database is initialized normally
        2. Corruption occurs (table dropped, data lost, etc.)
        3. System detects corruption during health check
        4. System attempts recovery by re-initializing
        5. Database is restored to working state

        Validates:
        - Corruption detection works
        - Recovery mechanism functions
        - System can continue operating after recovery
        """
        logger.info("=== Test 2.6: Database recovery ===")

        # Initialize database normally
        manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )
        await manager.initialize()
        logger.info("✓ Database initialized normally")

        # Simulate corruption: Drop a critical table (Issue #618: use async sqlite helper)
        await async_sqlite_execute(
            str(shared_db_path["db_path"]), "DROP TABLE conversation_files"
        )
        logger.info("✓ Simulated corruption (dropped conversation_files table)")

        # Create new manager instance and attempt recovery
        recovery_manager = ConversationFileManager(
            storage_dir=shared_db_path["storage_dir"],
            db_path=shared_db_path["db_path"],
            redis_host="localhost",
            redis_port=6379,
        )

        # Recovery: Re-initialize (should recreate missing table)
        await recovery_manager.initialize()
        logger.info("✓ Recovery attempted via re-initialization")

        # Verify table was recreated (Issue #618: use async sqlite helper)
        db_path_str = str(shared_db_path["db_path"])

        rows = await async_sqlite_query(
            db_path_str,
            "SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_files'",
        )
        assert len(rows) > 0, "Table should be recreated"
        logger.info("✓ Corrupted table recreated")

        # Verify table structure is correct
        rows = await async_sqlite_query(
            db_path_str, "PRAGMA table_info(conversation_files)"
        )
        columns = {row[1] for row in rows}

        expected_columns = {
            "file_id",
            "session_id",
            "original_filename",
            "stored_filename",
            "file_path",
            "file_size",
            "file_hash",
            "mime_type",
            "uploaded_at",
            "uploaded_by",
            "is_deleted",
            "deleted_at",
        }

        assert expected_columns.issubset(
            columns
        ), f"Missing columns: {expected_columns - columns}"
        logger.info("✓ Table structure correct after recovery")

        # Verify system can operate normally after recovery
        test_session = f"recovery_test_{uuid.uuid4()}"
        result = await recovery_manager.add_file(
            session_id=test_session,
            file_content=b"Test after recovery",
            original_filename="recovery_test.txt",
            mime_type="text/plain",
        )

        assert result["file_id"] is not None
        logger.info("✓ System operational after recovery")

        # Cleanup
        await recovery_manager.delete_session_files(test_session, hard_delete=True)

        logger.info("=== Test 2.6: PASSED ===\n")


# ============================================================================
# TEST EXECUTION
# ============================================================================

if __name__ == "__main__":
    """Run distributed integration tests"""
    pytest.main(
        [
            __file__,
            "-v",  # Verbose output
            "-m",
            "integration",  # Run only integration tests
            "--tb=short",  # Short traceback format
            "--asyncio-mode=auto",  # Enable async support
            "--log-cli-level=INFO",  # Show INFO logs
        ]
    )
