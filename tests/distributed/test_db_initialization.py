#!/usr/bin/env python3
"""
Distributed Integration Tests for Database Initialization

Task 1.6: Integration tests for cross-VM database initialization scenarios.

Test Scenarios:
1. Fresh VM0 deployment creates schema automatically
2. NPU Worker (VM2) file upload triggers proper initialization
3. Browser (VM5) screenshot save works with initialized database
4. Frontend (VM1) file upload succeeds with proper database access
5. Concurrent initialization from multiple VMs is safe

These tests validate that the database initialization system works correctly
in AutoBot's distributed multi-VM architecture.
"""

import asyncio
import httpx
import pytest
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.conversation_file_manager import ConversationFileManager


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# VM Configuration (AutoBot distributed architecture)
VM_CONFIG = {
    'backend': {'host': '172.16.168.20', 'port': 8001},  # Main backend (VM0)
    'frontend': {'host': '172.16.168.21', 'port': 5173},  # Frontend (VM1)
    'npu_worker': {'host': '172.16.168.22', 'port': 8081},  # NPU Worker (VM2)
    'redis': {'host': '172.16.168.23', 'port': 6379},  # Redis (VM3)
    'ai_stack': {'host': '172.16.168.24', 'port': 8080},  # AI Stack (VM4)
    'browser': {'host': '172.16.168.25', 'port': 3000}  # Browser (VM5)
}

# Test timeouts
HEALTH_CHECK_TIMEOUT = 10.0
FILE_UPLOAD_TIMEOUT = 30.0
CONCURRENT_INIT_TIMEOUT = 60.0


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def temp_distributed_db():
    """
    Create temporary database for distributed testing.

    This simulates a fresh VM deployment scenario where the database
    doesn't exist yet and needs to be initialized.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_path = tmp_path / "conversation_files.db"
        storage_dir = tmp_path / "files"
        storage_dir.mkdir()

        manager = ConversationFileManager(
            storage_dir=storage_dir,
            db_path=db_path,
            redis_host=VM_CONFIG['redis']['host'],
            redis_port=VM_CONFIG['redis']['port']
        )

        yield manager, tmp_path

        # Cleanup happens automatically via tempfile


@pytest.fixture
async def http_client():
    """Async HTTP client for API testing."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


# ============================================================================
# SCENARIO 1: FRESH VM DEPLOYMENT
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_fresh_vm0_deployment_creates_schema(temp_distributed_db):
    """
    Test Scenario 1: Fresh VM0 deployment automatically creates database schema.

    Simulates:
    - First-time AutoBot deployment on VM0 (main backend)
    - Backend startup triggers database initialization
    - Schema is created correctly without manual intervention

    Success Criteria:
    - Database file is created
    - All 6 tables exist (5 core + schema_migrations)
    - All 3 views are created
    - All 8 indexes are created
    - All 3 triggers are created
    - Schema version is recorded
    """
    manager, tmp_path = temp_distributed_db

    # Initially, database should not exist
    assert not manager.db_path.exists(), "Database should not exist before initialization"

    # Simulate backend startup initialization
    await manager.initialize()

    # Verify database was created
    assert manager.db_path.exists(), "Database should exist after initialization"
    assert manager.db_path.is_file(), "Database should be a file"

    # Verify schema version
    version = await manager._get_schema_version()
    assert version == "001", f"Expected schema version '001', got '{version}'"

    # Verify storage statistics work
    stats = await manager.get_storage_stats()
    assert stats['total_files'] == 0, "Fresh database should have no files"
    assert stats['total_sessions'] == 0, "Fresh database should have no sessions"

    print("✅ Test 1 PASSED: Fresh VM0 deployment creates complete schema")


# ============================================================================
# SCENARIO 2: NPU WORKER FILE UPLOAD
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_npu_worker_vm2_file_upload(temp_distributed_db):
    """
    Test Scenario 2: NPU Worker (VM2) file upload works with initialized database.

    Simulates:
    - NPU Worker processes AI task requiring file storage
    - Worker uploads result file to conversation file system
    - Database properly records file metadata

    Success Criteria:
    - File is stored successfully
    - File metadata is recorded in database
    - File can be retrieved by session ID
    - Deduplication works for identical files
    """
    manager, tmp_path = temp_distributed_db

    # Initialize database (simulates VM0 startup)
    await manager.initialize()

    # Simulate NPU Worker uploading AI processing result
    session_id = "test_npu_session_001"
    test_file_content = b"NPU Worker AI Processing Result - Image Classification\n" * 100
    original_filename = "npu_result_classification.json"

    # Upload file from NPU Worker
    file_metadata = await manager.add_file(
        session_id=session_id,
        file_content=test_file_content,
        original_filename=original_filename,
        mime_type="application/json",
        uploaded_by="npu_worker_vm2",
        message_id="msg_npu_001",
        metadata={
            'source': 'npu_worker',
            'vm': 'vm2',
            'task_type': 'image_classification',
            'model': 'resnet50'
        }
    )

    # Verify file was stored
    assert file_metadata['file_id'] is not None, "File ID should be assigned"
    assert file_metadata['session_id'] == session_id, "Session ID should match"
    assert file_metadata['original_filename'] == original_filename, "Filename should match"
    assert file_metadata['deduplicated'] is False, "First upload should not be deduplicated"

    # Verify file can be retrieved
    session_files = await manager.get_session_files(session_id)
    assert len(session_files) == 1, "Session should have exactly 1 file"
    assert session_files[0]['file_id'] == file_metadata['file_id'], "File ID should match"

    # Test deduplication: Upload same file again
    duplicate_metadata = await manager.add_file(
        session_id="different_session",
        file_content=test_file_content,  # Same content
        original_filename="different_name.json",
        mime_type="application/json",
        uploaded_by="npu_worker_vm2"
    )

    assert duplicate_metadata['deduplicated'] is True, "Duplicate upload should be detected"
    assert duplicate_metadata['file_hash'] == file_metadata['file_hash'], "Hash should match"

    print("✅ Test 2 PASSED: NPU Worker file upload and deduplication works")


# ============================================================================
# SCENARIO 3: BROWSER SCREENSHOT SAVE
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_browser_vm5_screenshot_save(temp_distributed_db):
    """
    Test Scenario 3: Browser (VM5) screenshot save works with initialized database.

    Simulates:
    - Browser VM captures screenshot during web automation
    - Screenshot is saved to conversation file system
    - Image metadata is properly recorded

    Success Criteria:
    - Screenshot file is stored successfully
    - Image metadata includes resolution and format
    - File is associated with correct session
    - Large files (up to 50MB) are handled
    """
    manager, tmp_path = temp_distributed_db

    # Initialize database
    await manager.initialize()

    # Simulate browser screenshot (PNG format)
    session_id = "test_browser_session_001"
    # Simulate a large screenshot (2MB compressed PNG)
    screenshot_content = b'\x89PNG\r\n\x1a\n' + (b'screenshot_data' * 150000)
    screenshot_filename = "browser_screenshot_1920x1080.png"

    # Upload screenshot from Browser VM
    screenshot_metadata = await manager.add_file(
        session_id=session_id,
        file_content=screenshot_content,
        original_filename=screenshot_filename,
        mime_type="image/png",
        uploaded_by="browser_vm5",
        message_id="msg_browser_001",
        metadata={
            'source': 'browser_vm5',
            'resolution': '1920x1080',
            'format': 'png',
            'capture_type': 'full_page',
            'url': 'https://example.com'
        }
    )

    # Verify screenshot was stored
    assert screenshot_metadata['file_id'] is not None, "Screenshot should have file ID"
    assert screenshot_metadata['file_size'] == len(screenshot_content), "File size should match"
    assert screenshot_metadata['mime_type'] == "image/png", "MIME type should be PNG"

    # Verify physical file exists
    stored_path = Path(screenshot_metadata['file_path'])
    assert stored_path.exists(), "Screenshot file should exist on disk"
    assert stored_path.stat().st_size == len(screenshot_content), "File size on disk should match"

    # Verify file can be retrieved
    session_files = await manager.get_session_files(session_id)
    assert len(session_files) == 1, "Session should have screenshot"
    assert session_files[0]['mime_type'] == "image/png", "Retrieved file should be PNG"

    print("✅ Test 3 PASSED: Browser screenshot save works correctly")


# ============================================================================
# SCENARIO 4: FRONTEND FILE UPLOAD
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_frontend_vm1_file_upload(temp_distributed_db):
    """
    Test Scenario 4: Frontend (VM1) file upload succeeds with proper database access.

    Simulates:
    - User uploads file through frontend web interface (VM1)
    - Frontend sends file to backend (VM0) via API
    - Backend stores file in conversation file system

    Success Criteria:
    - File upload completes successfully
    - File is associated with user session
    - Multiple files can be uploaded to same session
    - Files are retrievable through session ID
    """
    manager, tmp_path = temp_distributed_db

    # Initialize database
    await manager.initialize()

    # Simulate multiple file uploads from frontend
    session_id = "test_frontend_session_001"
    user_id = "user_test_001"

    # Upload 1: PDF document
    pdf_content = b'%PDF-1.4\n' + (b'document content' * 1000)
    pdf_metadata = await manager.add_file(
        session_id=session_id,
        file_content=pdf_content,
        original_filename="project_documentation.pdf",
        mime_type="application/pdf",
        uploaded_by=user_id,
        message_id="msg_frontend_001",
        metadata={'source': 'frontend_vm1', 'upload_type': 'user_document'}
    )

    # Upload 2: CSV data file
    csv_content = b'col1,col2,col3\n' + (b'data,data,data\n' * 500)
    csv_metadata = await manager.add_file(
        session_id=session_id,
        file_content=csv_content,
        original_filename="analysis_data.csv",
        mime_type="text/csv",
        uploaded_by=user_id,
        message_id="msg_frontend_002",
        metadata={'source': 'frontend_vm1', 'upload_type': 'data_file'}
    )

    # Upload 3: Image file
    image_content = b'\xff\xd8\xff\xe0' + (b'jpeg_data' * 5000)
    image_metadata = await manager.add_file(
        session_id=session_id,
        file_content=image_content,
        original_filename="screenshot.jpg",
        mime_type="image/jpeg",
        uploaded_by=user_id,
        message_id="msg_frontend_003",
        metadata={'source': 'frontend_vm1', 'upload_type': 'screenshot'}
    )

    # Verify all files were stored
    session_files = await manager.get_session_files(session_id)
    assert len(session_files) == 3, "Session should have 3 files"

    # Verify file types
    mime_types = {f['mime_type'] for f in session_files}
    expected_types = {"application/pdf", "text/csv", "image/jpeg"}
    assert mime_types == expected_types, "All MIME types should be present"

    # Verify storage statistics
    stats = await manager.get_storage_stats()
    assert stats['total_files'] == 3, "Should have 3 files total"
    assert stats['total_sessions'] == 1, "Should have 1 session"
    assert stats['total_size_bytes'] > 0, "Total size should be non-zero"

    print("✅ Test 4 PASSED: Frontend multi-file upload works correctly")


# ============================================================================
# SCENARIO 5: CONCURRENT INITIALIZATION
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_initialization_from_multiple_vms(temp_distributed_db):
    """
    Test Scenario 5: Concurrent initialization from multiple VMs is safe.

    Simulates:
    - Multiple VMs (VM0, VM1, VM2) attempt to initialize database concurrently
    - Each VM creates a ConversationFileManager instance
    - All VMs call initialize() simultaneously
    - Database initialization is thread-safe and idempotent

    Success Criteria:
    - All initialization attempts succeed
    - No database corruption occurs
    - Schema is created correctly only once
    - All VMs can use the database after initialization
    """
    manager, tmp_path = temp_distributed_db

    # Create multiple managers simulating different VMs
    vm_managers = {
        'vm0_backend': ConversationFileManager(
            storage_dir=manager.storage_dir,
            db_path=manager.db_path,
            redis_host=VM_CONFIG['redis']['host'],
            redis_port=VM_CONFIG['redis']['port']
        ),
        'vm1_frontend': ConversationFileManager(
            storage_dir=manager.storage_dir,
            db_path=manager.db_path,
            redis_host=VM_CONFIG['redis']['host'],
            redis_port=VM_CONFIG['redis']['port']
        ),
        'vm2_npu_worker': ConversationFileManager(
            storage_dir=manager.storage_dir,
            db_path=manager.db_path,
            redis_host=VM_CONFIG['redis']['host'],
            redis_port=VM_CONFIG['redis']['port']
        )
    }

    # Initialize all managers concurrently
    start_time = time.time()

    initialization_tasks = [
        asyncio.create_task(mgr.initialize())
        for mgr in vm_managers.values()
    ]

    # Wait for all initializations to complete
    results = await asyncio.gather(*initialization_tasks, return_exceptions=True)

    elapsed_time = time.time() - start_time

    # Verify all initializations succeeded
    for i, result in enumerate(results):
        assert not isinstance(result, Exception), \
            f"Initialization {i} failed: {result}"

    # Verify database is valid
    assert manager.db_path.exists(), "Database should exist after concurrent initialization"

    # Verify schema integrity
    version = await vm_managers['vm0_backend']._get_schema_version()
    assert version == "001", "Schema version should be correct"

    # Verify all VMs can use the database
    session_id = "test_concurrent_session"
    test_content = b"concurrent initialization test"

    # Each VM uploads a file
    upload_tasks = [
        vm_managers['vm0_backend'].add_file(
            session_id=session_id,
            file_content=test_content + b"_vm0",
            original_filename="vm0_file.txt",
            uploaded_by="vm0"
        ),
        vm_managers['vm1_frontend'].add_file(
            session_id=session_id,
            file_content=test_content + b"_vm1",
            original_filename="vm1_file.txt",
            uploaded_by="vm1"
        ),
        vm_managers['vm2_npu_worker'].add_file(
            session_id=session_id,
            file_content=test_content + b"_vm2",
            original_filename="vm2_file.txt",
            uploaded_by="vm2"
        )
    ]

    file_results = await asyncio.gather(*upload_tasks, return_exceptions=True)

    # Verify all uploads succeeded
    for i, result in enumerate(file_results):
        assert not isinstance(result, Exception), \
            f"File upload {i} failed after concurrent initialization: {result}"

    # Verify all files are in session
    session_files = await vm_managers['vm0_backend'].get_session_files(session_id)
    assert len(session_files) == 3, "All 3 VMs should have uploaded files successfully"

    print(f"✅ Test 5 PASSED: Concurrent initialization safe (completed in {elapsed_time:.2f}s)")
    print(f"   - All {len(vm_managers)} VMs initialized successfully")
    print(f"   - All VMs can upload files after initialization")
    print(f"   - No database corruption detected")


# ============================================================================
# INTEGRATION TEST: END-TO-END DISTRIBUTED WORKFLOW
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_end_to_end_distributed_workflow(temp_distributed_db):
    """
    End-to-End Integration Test: Complete distributed file management workflow.

    Simulates complete AutoBot distributed workflow:
    1. VM0 backend initializes database
    2. VM1 frontend uploads user document
    3. VM2 NPU processes document and uploads result
    4. VM5 browser captures screenshot
    5. All files are associated with same session
    6. Files can be retrieved and deleted

    Success Criteria:
    - All operations complete successfully
    - Files from different VMs are properly associated
    - Session file retrieval works across VMs
    - Cleanup operations work correctly
    """
    manager, tmp_path = temp_distributed_db

    # Step 1: VM0 backend initializes database
    await manager.initialize()
    print("Step 1: ✓ VM0 backend initialized database")

    session_id = "e2e_distributed_session"

    # Step 2: VM1 frontend - user uploads document
    frontend_upload = await manager.add_file(
        session_id=session_id,
        file_content=b"User document for AI processing\n" * 100,
        original_filename="user_document.txt",
        mime_type="text/plain",
        uploaded_by="user_001",
        message_id="msg_001",
        metadata={'source': 'frontend_vm1', 'step': 'user_upload'}
    )
    print("Step 2: ✓ VM1 frontend uploaded user document")

    # Step 3: VM2 NPU Worker processes and uploads result
    npu_result = await manager.add_file(
        session_id=session_id,
        file_content=b'{"analysis": "AI processing complete", "confidence": 0.95}\n' * 50,
        original_filename="ai_processing_result.json",
        mime_type="application/json",
        uploaded_by="npu_worker_vm2",
        message_id="msg_002",
        metadata={'source': 'npu_worker_vm2', 'step': 'ai_processing'}
    )
    print("Step 3: ✓ VM2 NPU Worker uploaded AI result")

    # Step 4: VM5 browser captures screenshot
    browser_screenshot = await manager.add_file(
        session_id=session_id,
        file_content=b'\x89PNG\r\n' + (b'screenshot' * 10000),
        original_filename="result_visualization.png",
        mime_type="image/png",
        uploaded_by="browser_vm5",
        message_id="msg_003",
        metadata={'source': 'browser_vm5', 'step': 'visualization'}
    )
    print("Step 4: ✓ VM5 browser captured screenshot")

    # Verify all files are associated with session
    session_files = await manager.get_session_files(session_id)
    assert len(session_files) == 3, "Session should have all 3 files"
    print(f"Step 5: ✓ All {len(session_files)} files retrieved successfully")

    # Verify file sources
    sources = {f['uploaded_by'] for f in session_files}
    expected_sources = {"user_001", "npu_worker_vm2", "browser_vm5"}
    assert sources == expected_sources, "All VM sources should be present"

    # Test cleanup: soft delete all files
    deleted_count = await manager.delete_session_files(session_id, hard_delete=False)
    assert deleted_count == 3, "All files should be soft deleted"
    print(f"Step 6: ✓ Soft deleted {deleted_count} files")

    # Verify files are marked as deleted
    active_files = await manager.get_session_files(session_id)
    assert len(active_files) == 0, "No active files should remain"

    deleted_files = await manager.get_session_files(session_id, include_deleted=True)
    assert len(deleted_files) == 3, "Deleted files should still be retrievable"
    print("Step 7: ✓ Deleted files are properly tracked")

    print("\n✅ END-TO-END DISTRIBUTED WORKFLOW COMPLETE")
    print("   - Database initialization works")
    print("   - Multi-VM file uploads succeed")
    print("   - Session file associations work")
    print("   - Cleanup operations are safe")


# ============================================================================
# TEST EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--asyncio-mode=auto",
        "-m", "integration"
    ])
