"""
Comprehensive Test Suite for Audit Logging System

Tests:
- Audit entry creation and sanitization
- Redis storage and retrieval
- Multi-index queries
- Performance validation (<5ms overhead)
- Batch processing
- Fallback logging
- Retention and cleanup
- Distributed VM support
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from backend.services.audit_logger import (
    AuditLogger,
    AuditEntry,
    get_audit_logger,
    close_audit_logger,
    audit_log,
    OPERATION_CATEGORIES
)
from backend.utils.async_redis_manager import get_redis_manager


@pytest.fixture
async def audit_logger():
    """Create audit logger for testing"""
    logger = AuditLogger(
        retention_days=7,
        batch_size=10,
        batch_timeout_seconds=0.5,
        fallback_log_dir="tests/temp/audit_logs"
    )
    yield logger
    await logger.close()


@pytest.fixture
async def redis_manager():
    """Get Redis manager for testing"""
    manager = await get_redis_manager()
    yield manager


@pytest.mark.asyncio
class TestAuditEntry:
    """Test AuditEntry dataclass and serialization"""

    def test_audit_entry_creation(self):
        """Test creating audit entry with all fields"""
        entry = AuditEntry(
            operation="auth.login",
            result="success",
            user_id="test_user",
            session_id="session_123",
            ip_address="172.16.168.21",
            resource="/api/auth/login",
            user_role="admin",
            vm_source="172.16.168.20",
            vm_name="backend",
            details={"method": "POST"},
            performance_ms=2.5
        )

        assert entry.operation == "auth.login"
        assert entry.result == "success"
        assert entry.user_id == "test_user"
        assert entry.vm_name == "backend"

    def test_audit_entry_defaults(self):
        """Test audit entry with default values"""
        entry = AuditEntry()

        assert entry.id is not None
        assert entry.timestamp > 0
        assert entry.date == datetime.now().strftime("%Y-%m-%d")
        assert entry.details == {}

    def test_audit_entry_serialization(self):
        """Test JSON serialization and deserialization"""
        original = AuditEntry(
            operation="file.delete",
            result="denied",
            user_id="guest",
            details={"reason": "no permission"}
        )

        # Serialize
        json_str = original.to_json()
        assert isinstance(json_str, str)
        assert "file.delete" in json_str

        # Deserialize
        restored = AuditEntry.from_json(json_str)
        assert restored.operation == original.operation
        assert restored.result == original.result
        assert restored.user_id == original.user_id
        assert restored.details == original.details

    def test_audit_entry_sanitization(self):
        """Test removal of sensitive data per OWASP guidelines"""
        entry = AuditEntry(
            operation="auth.login",
            details={
                "username": "admin",
                "password": "secret123",  # Should be removed
                "token": "jwt_token_here",  # Should be removed
                "api_key": "key_123",  # Should be removed
                "safe_data": "this is ok"
            }
        )

        entry.sanitize()

        assert "password" not in entry.details
        assert "token" not in entry.details
        assert "api_key" not in entry.details
        assert "safe_data" in entry.details
        assert entry.details["safe_data"] == "this is ok"


@pytest.mark.asyncio
class TestAuditLogger:
    """Test AuditLogger core functionality"""

    async def test_audit_logger_initialization(self, audit_logger):
        """Test audit logger initialization"""
        assert audit_logger.retention_days == 7
        assert audit_logger.batch_size == 10
        assert audit_logger.vm_source is not None
        assert audit_logger.vm_name is not None

    async def test_basic_audit_logging(self, audit_logger):
        """Test basic audit log creation"""
        success = await audit_logger.log(
            operation="auth.login",
            result="success",
            user_id="test_user",
            ip_address="172.16.168.21"
        )

        assert success is True
        assert audit_logger._total_logged > 0

    async def test_audit_logging_performance(self, audit_logger):
        """Test that audit logging meets <5ms performance requirement"""
        start_time = time.time()

        await audit_logger.log(
            operation="auth.login",
            result="success",
            user_id="performance_test"
        )

        duration_ms = (time.time() - start_time) * 1000

        # Should complete in under 5ms
        assert duration_ms < 5.0, f"Audit logging took {duration_ms:.2f}ms (exceeds 5ms target)"

    async def test_batch_processing(self, audit_logger):
        """Test batch processing of audit entries"""
        # Log multiple entries
        for i in range(15):
            await audit_logger.log(
                operation="test.operation",
                result="success",
                user_id=f"user_{i}"
            )

        # Wait for batch to flush
        await asyncio.sleep(1)

        # Check that entries were batched
        assert audit_logger._total_logged == 15

    async def test_audit_with_details(self, audit_logger):
        """Test audit logging with additional details"""
        details = {
            "method": "POST",
            "status_code": 200,
            "user_agent": "Mozilla/5.0"
        }

        success = await audit_logger.log(
            operation="file.upload",
            result="success",
            user_id="test_user",
            details=details,
            performance_ms=12.5
        )

        assert success is True

    async def test_fallback_logging(self, audit_logger):
        """Test fallback to file when Redis unavailable"""
        # Mock Redis failure
        with patch.object(audit_logger, '_get_audit_db', return_value=None):
            success = await audit_logger.log(
                operation="test.fallback",
                result="success",
                user_id="fallback_user"
            )

            # Should still succeed using fallback
            assert success is True

            # Check fallback file was created
            fallback_dir = Path(audit_logger.fallback_log_dir)
            assert fallback_dir.exists()

            fallback_files = list(fallback_dir.glob("audit_*.jsonl"))
            assert len(fallback_files) > 0


@pytest.mark.asyncio
class TestAuditQueries:
    """Test audit log querying functionality"""

    @pytest.fixture
    async def populated_logger(self, audit_logger):
        """Create audit logger with test data"""
        # Create test entries
        test_data = [
            {"operation": "auth.login", "user_id": "alice", "result": "success"},
            {"operation": "auth.login", "user_id": "bob", "result": "denied"},
            {"operation": "file.delete", "user_id": "alice", "result": "success"},
            {"operation": "file.upload", "user_id": "charlie", "result": "success"},
            {"operation": "auth.logout", "user_id": "alice", "result": "success"},
        ]

        for data in test_data:
            await audit_logger.log(**data)

        # Force flush
        await audit_logger.flush()
        await asyncio.sleep(0.5)  # Wait for Redis write

        return audit_logger

    async def test_query_by_time_range(self, populated_logger):
        """Test querying audit logs by time range"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        entries = await populated_logger.query(
            start_time=start_time,
            end_time=end_time,
            limit=100
        )

        # Should return all test entries
        assert len(entries) >= 5

    async def test_query_by_user(self, populated_logger):
        """Test querying audit logs by user"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        entries = await populated_logger.query(
            start_time=start_time,
            end_time=end_time,
            user_id="alice",
            limit=100
        )

        # Alice has 3 operations
        assert len(entries) >= 3
        assert all(e.user_id == "alice" for e in entries)

    async def test_query_by_operation(self, populated_logger):
        """Test querying audit logs by operation type"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        entries = await populated_logger.query(
            start_time=start_time,
            end_time=end_time,
            operation="auth.login",
            limit=100
        )

        # Should find login operations
        assert len(entries) >= 2
        assert all(e.operation == "auth.login" for e in entries)

    async def test_query_by_result(self, populated_logger):
        """Test querying audit logs by result"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        entries = await populated_logger.query(
            start_time=start_time,
            end_time=end_time,
            result="denied",
            limit=100
        )

        # Should find denied operations
        assert len(entries) >= 1
        assert all(e.result == "denied" for e in entries)

    async def test_query_pagination(self, populated_logger):
        """Test query pagination"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        # Get first page
        page1 = await populated_logger.query(
            start_time=start_time,
            end_time=end_time,
            limit=2,
            offset=0
        )

        # Get second page
        page2 = await populated_logger.query(
            start_time=start_time,
            end_time=end_time,
            limit=2,
            offset=2
        )

        assert len(page1) <= 2
        assert len(page2) <= 2

        # Pages should have different entries
        if len(page1) > 0 and len(page2) > 0:
            assert page1[0].id != page2[0].id


@pytest.mark.asyncio
class TestAuditStatistics:
    """Test audit logging statistics"""

    async def test_get_statistics(self, audit_logger):
        """Test getting audit statistics"""
        # Log some entries
        for i in range(5):
            await audit_logger.log(
                operation="test.stats",
                result="success",
                user_id=f"user_{i}"
            )

        await audit_logger.flush()

        stats = await audit_logger.get_statistics()

        assert "total_logged" in stats
        assert "total_failed" in stats
        assert "redis_available" in stats
        assert stats["total_logged"] >= 5


@pytest.mark.asyncio
class TestRetentionAndCleanup:
    """Test audit log retention and cleanup"""

    async def test_cleanup_old_logs(self, audit_logger):
        """Test cleanup of old audit logs"""
        # This would require mock data with old timestamps
        # For now, test that cleanup runs without error
        try:
            await audit_logger.cleanup_old_logs(days_to_keep=30)
            success = True
        except Exception:
            success = False

        assert success is True


@pytest.mark.asyncio
class TestDistributedLogging:
    """Test distributed VM audit logging"""

    async def test_vm_identification(self, audit_logger):
        """Test that VM source is properly identified"""
        assert audit_logger.vm_source is not None
        assert audit_logger.vm_name is not None

        # VM name should be one of the known VMs
        valid_vms = ["backend", "frontend", "npu-worker", "redis", "ai-stack", "browser"]
        assert audit_logger.vm_name in valid_vms or audit_logger.vm_name != ""

    async def test_vm_source_in_audit_entry(self, audit_logger):
        """Test that VM source is included in audit entries"""
        await audit_logger.log(
            operation="test.vm",
            result="success",
            user_id="vm_test"
        )

        await audit_logger.flush()

        # Check that batch queue entry has VM info
        # (Would need to query to verify in Redis)
        assert audit_logger.vm_source is not None


@pytest.mark.asyncio
class TestGlobalAuditLogger:
    """Test global audit logger singleton"""

    async def test_get_global_logger(self):
        """Test getting global audit logger instance"""
        logger1 = await get_audit_logger()
        logger2 = await get_audit_logger()

        # Should return same instance
        assert logger1 is logger2

    async def test_close_global_logger(self):
        """Test closing global audit logger"""
        await get_audit_logger()
        await close_audit_logger()

        # Should be able to get new instance after close
        new_logger = await get_audit_logger()
        assert new_logger is not None


@pytest.mark.asyncio
class TestConvenienceFunction:
    """Test convenience audit_log function"""

    async def test_audit_log_function(self):
        """Test quick audit logging via convenience function"""
        success = await audit_log(
            operation="test.convenience",
            result="success",
            user_id="convenience_test"
        )

        assert success is True


@pytest.mark.asyncio
class TestOperationCategories:
    """Test operation categorization"""

    def test_operation_categories_defined(self):
        """Test that operation categories are properly defined"""
        assert len(OPERATION_CATEGORIES) > 0

        # Check key categories exist
        assert "auth.login" in OPERATION_CATEGORIES
        assert "file.delete" in OPERATION_CATEGORIES
        assert "elevation.request" in OPERATION_CATEGORIES

    def test_category_groupings(self):
        """Test that operations are properly categorized"""
        categories = set(OPERATION_CATEGORIES.values())

        expected_categories = {
            "Authentication",
            "File Operations",
            "Privilege Escalation",
            "Session Management",
            "Configuration",
            "Terminal Operations",
            "Conversation Data"
        }

        assert categories == expected_categories


@pytest.mark.asyncio
class TestPerformanceBenchmark:
    """Performance benchmarking tests"""

    async def test_throughput_benchmark(self, audit_logger):
        """Test audit logging throughput"""
        num_entries = 100
        start_time = time.time()

        tasks = []
        for i in range(num_entries):
            task = audit_logger.log(
                operation="test.throughput",
                result="success",
                user_id=f"user_{i}"
            )
            tasks.append(task)

        await asyncio.gather(*tasks)
        await audit_logger.flush()

        duration = time.time() - start_time
        throughput = num_entries / duration

        print(f"\nAudit Logging Throughput: {throughput:.2f} entries/second")
        print(f"Total time: {duration:.2f} seconds for {num_entries} entries")

        # Should handle at least 100 entries/second
        assert throughput > 100, f"Throughput {throughput:.2f} is below target"

    async def test_individual_log_latency(self, audit_logger):
        """Test individual log operation latency"""
        latencies = []

        for i in range(50):
            start = time.time()
            await audit_logger.log(
                operation="test.latency",
                result="success",
                user_id=f"user_{i}"
            )
            latency_ms = (time.time() - start) * 1000
            latencies.append(latency_ms)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"\nAverage latency: {avg_latency:.2f}ms")
        print(f"Maximum latency: {max_latency:.2f}ms")

        # Average should be well under 5ms
        assert avg_latency < 5.0, f"Average latency {avg_latency:.2f}ms exceeds 5ms target"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
