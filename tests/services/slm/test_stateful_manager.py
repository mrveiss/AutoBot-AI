# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM Stateful Service Manager.
"""

import os
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.infrastructure import NodeState
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.stateful_manager import (
    BackupContext,
    BackupState,
    RedisHandler,
    ReplicatedSwapStrategy,
    ReplicationContext,
    ReplicationState,
    StatefulServiceManager,
    get_stateful_manager,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def db_service(temp_db):
    """Create database service."""
    return SLMDatabaseService(db_path=temp_db)


@pytest.fixture
def mock_ssh():
    """Create mock SSH executor."""
    ssh = MagicMock()
    ssh.execute = MagicMock(return_value="OK")
    return ssh


@pytest.fixture
def primary_node(db_service):
    """Create primary node for testing."""
    node = db_service.create_node(
        name="redis-primary",
        ip_address="192.168.1.100",
        ssh_user="autobot",
        current_role="redis",
    )
    db_service.update_node_state(
        node_id=node.id,
        new_state=NodeState.ONLINE,
        trigger="test",
        validate_transition=False,
    )
    return db_service.get_node(node.id)


@pytest.fixture
def replica_node(db_service):
    """Create replica node for testing."""
    node = db_service.create_node(
        name="redis-replica",
        ip_address="192.168.1.101",
        ssh_user="autobot",
    )
    db_service.update_node_state(
        node_id=node.id,
        new_state=NodeState.ONLINE,
        trigger="test",
        validate_transition=False,
    )
    return db_service.get_node(node.id)


class TestReplicationContext:
    """Test ReplicationContext dataclass."""

    def test_default_state(self):
        """Test default state is pending."""
        ctx = ReplicationContext(
            replication_id="rep-123",
            primary_node_id="node-1",
            replica_node_id="node-2",
            service_type="redis",
        )

        assert ctx.state == ReplicationState.PENDING
        assert ctx.sync_progress == 0.0
        assert ctx.started_at is None
        assert ctx.error is None


class TestBackupContext:
    """Test BackupContext dataclass."""

    def test_default_state(self):
        """Test default state is pending."""
        ctx = BackupContext(
            backup_id="bak-123",
            node_id="node-1",
            service_type="redis",
            backup_path="/tmp/backup.rdb",
        )

        assert ctx.state == BackupState.PENDING
        assert ctx.size_bytes == 0
        assert ctx.checksum is None


class TestRedisHandler:
    """Test Redis stateful service handler."""

    @pytest.fixture
    def handler(self, db_service, mock_ssh):
        """Create Redis handler."""
        return RedisHandler(db=db_service, ssh=mock_ssh)

    def test_service_type(self, handler):
        """Test service type property."""
        assert handler.service_type == "redis"

    @pytest.mark.asyncio
    async def test_setup_replication_success(
        self, handler, primary_node, replica_node
    ):
        """Test successful replication setup."""
        handler.ssh.execute = MagicMock(return_value="OK")

        context = await handler.setup_replication(primary_node, replica_node)

        assert context.state == ReplicationState.SYNCING
        assert context.primary_node_id == primary_node.id
        assert context.replica_node_id == replica_node.id
        assert context.started_at is not None
        assert context.details["primary_ip"] == primary_node.ip_address

    @pytest.mark.asyncio
    async def test_setup_replication_failure(
        self, handler, primary_node, replica_node
    ):
        """Test replication setup failure."""
        handler.ssh.execute = MagicMock(return_value="ERR connection refused")

        context = await handler.setup_replication(primary_node, replica_node)

        assert context.state == ReplicationState.FAILED
        assert "Failed to set up replication" in context.error

    @pytest.mark.asyncio
    async def test_check_sync_status_synced(self, handler, db_service):
        """Test sync status when synced."""
        # Create nodes
        primary = db_service.create_node(
            name="primary",
            ip_address="192.168.1.1",
            ssh_user="autobot",
        )
        replica = db_service.create_node(
            name="replica",
            ip_address="192.168.1.2",
            ssh_user="autobot",
        )

        context = ReplicationContext(
            replication_id="rep-123",
            primary_node_id=primary.id,
            replica_node_id=replica.id,
            service_type="redis",
            state=ReplicationState.SYNCING,
        )

        # Mock synced state
        handler.ssh.execute = MagicMock(
            return_value="""
            role:slave
            master_link_status:up
            master_sync_in_progress:0
            master_repl_offset:1000
            slave_repl_offset:1000
            """
        )

        is_synced, progress = await handler.check_sync_status(context)

        assert is_synced is True
        assert progress == 1.0
        assert context.state == ReplicationState.SYNCED

    @pytest.mark.asyncio
    async def test_check_sync_status_in_progress(self, handler, db_service):
        """Test sync status when still syncing."""
        replica = db_service.create_node(
            name="replica",
            ip_address="192.168.1.2",
            ssh_user="autobot",
        )

        context = ReplicationContext(
            replication_id="rep-123",
            primary_node_id="primary-id",
            replica_node_id=replica.id,
            service_type="redis",
            state=ReplicationState.SYNCING,
        )

        # Mock in-progress state
        handler.ssh.execute = MagicMock(
            return_value="""
            role:slave
            master_link_status:up
            master_sync_in_progress:1
            master_sync_total_bytes:1000000
            master_sync_left_bytes:500000
            """
        )

        is_synced, progress = await handler.check_sync_status(context)

        assert is_synced is False
        assert progress == 0.5

    @pytest.mark.asyncio
    async def test_promote_replica_success(self, handler, db_service):
        """Test successful replica promotion."""
        replica = db_service.create_node(
            name="replica",
            ip_address="192.168.1.2",
            ssh_user="autobot",
        )

        context = ReplicationContext(
            replication_id="rep-123",
            primary_node_id="primary-id",
            replica_node_id=replica.id,
            service_type="redis",
            state=ReplicationState.SYNCED,
        )

        # Mock successful promotion
        call_count = [0]

        def mock_execute(host, user, command):
            call_count[0] += 1
            if "REPLICAOF NO ONE" in command:
                return "OK"
            if "INFO replication" in command:
                return "role:master"
            return ""

        handler.ssh.execute = mock_execute

        result = await handler.promote_replica(context)

        assert result is True
        assert context.state == ReplicationState.PROMOTED
        assert context.completed_at is not None

    @pytest.mark.asyncio
    async def test_promote_replica_failure(self, handler, db_service):
        """Test replica promotion failure."""
        replica = db_service.create_node(
            name="replica",
            ip_address="192.168.1.2",
            ssh_user="autobot",
        )

        context = ReplicationContext(
            replication_id="rep-123",
            primary_node_id="primary-id",
            replica_node_id=replica.id,
            service_type="redis",
            state=ReplicationState.SYNCED,
        )

        handler.ssh.execute = MagicMock(return_value="ERR not supported")

        result = await handler.promote_replica(context)

        assert result is False
        assert context.state == ReplicationState.FAILED

    @pytest.mark.asyncio
    async def test_create_backup_success(self, handler, primary_node):
        """Test successful backup creation."""
        backup_path = "/tmp/test_backup.rdb"

        # Mock successful backup
        def mock_execute(host, user, command):
            if "BGSAVE" in command:
                return "Background saving started"
            if "INFO persistence" in command:
                return "rdb_bgsave_in_progress:0"
            if "CONFIG GET dir" in command:
                return "dir\n/var/lib/redis"
            if "stat" in command:
                return "1024\nmd5hash123  /tmp/test_backup.rdb"
            return ""

        handler.ssh.execute = mock_execute

        context = await handler.create_backup(primary_node, backup_path)

        assert context.state == BackupState.COMPLETED
        assert context.backup_path == backup_path
        assert context.size_bytes == 1024
        assert context.checksum == "md5hash123"

    @pytest.mark.asyncio
    async def test_create_backup_failure(self, handler, primary_node):
        """Test backup creation failure."""
        backup_path = "/tmp/test_backup.rdb"

        handler.ssh.execute = MagicMock(return_value="ERR BGSAVE failed")

        context = await handler.create_backup(primary_node, backup_path)

        assert context.state == BackupState.FAILED
        assert "BGSAVE failed" in context.error

    @pytest.mark.asyncio
    async def test_restore_backup_success(self, handler, primary_node):
        """Test successful backup restoration."""
        context = BackupContext(
            backup_id="bak-123",
            node_id=primary_node.id,
            service_type="redis",
            backup_path="/tmp/test_backup.rdb",
            checksum="md5hash123",
        )

        # Mock successful restore
        def mock_execute(host, user, command):
            if "md5sum" in command:
                return "md5hash123  /tmp/test_backup.rdb"
            if "PING" in command:
                return "PONG"
            if "CONFIG GET dir" in command:
                return "dir\n/var/lib/redis"
            return ""

        handler.ssh.execute = mock_execute

        result = await handler.restore_backup(primary_node, context)

        assert result is True
        assert context.state == BackupState.RESTORED

    @pytest.mark.asyncio
    async def test_restore_backup_checksum_mismatch(self, handler, primary_node):
        """Test backup restore with checksum mismatch."""
        context = BackupContext(
            backup_id="bak-123",
            node_id=primary_node.id,
            service_type="redis",
            backup_path="/tmp/test_backup.rdb",
            checksum="expected_hash",
        )

        handler.ssh.execute = MagicMock(
            return_value="different_hash  /tmp/test_backup.rdb"
        )

        result = await handler.restore_backup(primary_node, context)

        assert result is False
        assert context.state == BackupState.FAILED
        assert "checksum mismatch" in context.error

    @pytest.mark.asyncio
    async def test_verify_data_integrity_success(self, handler, primary_node):
        """Test successful data integrity verification."""

        def mock_execute(host, user, command):
            if "INFO keyspace" in command:
                return "db0:keys=100,expires=10"
            if "INFO memory" in command:
                return """
                used_memory:1000000
                used_memory_human:1M
                maxmemory:0
                """
            if "INFO persistence" in command:
                return """
                rdb_last_save_time:1234567890
                rdb_last_bgsave_status:ok
                aof_enabled:0
                """
            return ""

        handler.ssh.execute = mock_execute

        is_healthy, result = await handler.verify_data_integrity(primary_node)

        assert is_healthy is True
        assert "db0" in result["keyspace"]
        assert result["memory"]["used_memory"] == "1000000"
        assert result["persistence"]["rdb_last_bgsave_status"] == "ok"
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_verify_data_integrity_errors(self, handler, primary_node):
        """Test data integrity verification with errors."""

        def mock_execute(host, user, command):
            if "INFO persistence" in command:
                return "rdb_last_bgsave_status:err"
            return ""

        handler.ssh.execute = mock_execute

        is_healthy, result = await handler.verify_data_integrity(primary_node)

        assert is_healthy is False
        assert "Last RDB save failed" in result["errors"]


class TestReplicatedSwapStrategy:
    """Test replicated swap update strategy."""

    @pytest.fixture
    def strategy(self, db_service, mock_ssh):
        """Create strategy."""
        return ReplicatedSwapStrategy(db=db_service, ssh=mock_ssh)

    def test_get_handler(self, strategy):
        """Test getting handler by service type."""
        handler = strategy.get_handler("redis")
        assert handler is not None
        assert handler.service_type == "redis"

        unknown = strategy.get_handler("unknown")
        assert unknown is None

    @pytest.mark.asyncio
    async def test_execute_replicated_update_no_handler(self, strategy):
        """Test update with unknown service type."""
        success, message = await strategy.execute_replicated_update(
            primary_node_id="node-1",
            standby_node_id="node-2",
            service_type="unknown",
        )

        assert success is False
        assert "No handler" in message

    @pytest.mark.asyncio
    async def test_execute_replicated_update_node_not_found(self, strategy):
        """Test update with missing nodes."""
        success, message = await strategy.execute_replicated_update(
            primary_node_id="nonexistent",
            standby_node_id="also-nonexistent",
            service_type="redis",
        )

        assert success is False
        assert "not found" in message


class TestStatefulServiceManager:
    """Test StatefulServiceManager."""

    @pytest.fixture
    def manager(self, db_service, mock_ssh):
        """Create manager."""
        return StatefulServiceManager(
            db=db_service,
            ssh=mock_ssh,
            backup_dir="/tmp/backups",
        )

    def test_get_handler(self, manager):
        """Test getting handler."""
        handler = manager.get_handler("redis")
        assert handler is not None

    @pytest.mark.asyncio
    async def test_start_replication_unknown_service(self, manager):
        """Test starting replication for unknown service."""
        ctx = await manager.start_replication(
            primary_node_id="node-1",
            replica_node_id="node-2",
            service_type="unknown",
        )

        assert ctx.state == ReplicationState.FAILED
        assert "No handler" in ctx.error

    @pytest.mark.asyncio
    async def test_start_replication_node_not_found(self, manager):
        """Test starting replication with missing nodes."""
        ctx = await manager.start_replication(
            primary_node_id="nonexistent",
            replica_node_id="also-nonexistent",
            service_type="redis",
        )

        assert ctx.state == ReplicationState.FAILED
        assert "not found" in ctx.error

    @pytest.mark.asyncio
    async def test_start_replication_success(
        self, manager, primary_node, replica_node
    ):
        """Test successful replication start."""
        manager.ssh.execute = MagicMock(return_value="OK")

        ctx = await manager.start_replication(
            primary_node_id=primary_node.id,
            replica_node_id=replica_node.id,
            service_type="redis",
        )

        assert ctx.state == ReplicationState.SYNCING
        assert ctx.replication_id in [r.replication_id for r in manager.active_replications]

    @pytest.mark.asyncio
    async def test_create_backup_success(self, manager, primary_node):
        """Test successful backup creation."""

        def mock_execute(host, user, command):
            if "BGSAVE" in command:
                return "Background saving started"
            if "INFO persistence" in command:
                return "rdb_bgsave_in_progress:0"
            if "CONFIG GET dir" in command:
                return "dir\n/var/lib/redis"
            if "stat" in command:
                return "2048\nhash456  /tmp/backups/test.rdb"
            return ""

        manager.ssh.execute = mock_execute

        ctx = await manager.create_backup(
            node_id=primary_node.id,
            service_type="redis",
            backup_name="test_backup",
        )

        assert ctx.state == BackupState.COMPLETED
        assert "test_backup" in ctx.backup_path
        assert ctx.backup_id in [b.backup_id for b in manager.active_backups]

    @pytest.mark.asyncio
    async def test_verify_data_success(self, manager, primary_node):
        """Test data verification."""

        def mock_execute(host, user, command):
            if "INFO keyspace" in command:
                return "db0:keys=50"
            if "INFO memory" in command:
                return "used_memory:500000\nused_memory_human:500K"
            if "INFO persistence" in command:
                return "rdb_last_bgsave_status:ok"
            return ""

        manager.ssh.execute = mock_execute

        is_healthy, result = await manager.verify_data(
            node_id=primary_node.id,
            service_type="redis",
        )

        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_verify_data_unknown_service(self, manager, primary_node):
        """Test data verification with unknown service."""
        is_healthy, result = await manager.verify_data(
            node_id=primary_node.id,
            service_type="unknown",
        )

        assert is_healthy is False
        assert "No handler" in result["error"]


class TestGetStatefulManager:
    """Test singleton factory."""

    def test_returns_singleton(self):
        """Test singleton pattern."""
        import backend.services.slm.stateful_manager as module

        # Reset singleton
        module._stateful_manager = None

        manager1 = get_stateful_manager()
        manager2 = get_stateful_manager()

        assert manager1 is manager2

        # Cleanup
        module._stateful_manager = None
