# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Stateful Service Manager

Provides specialized handling for stateful services:
- Redis replication-based updates (zero-downtime)
- Backup/restore for maintenance windows
- Data sync verification
"""

import asyncio
import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.models.infrastructure import NodeState, SLMNode
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.remediator import SSHExecutor

logger = logging.getLogger(__name__)


class ReplicationState(str, Enum):
    """State of a replication operation."""

    PENDING = "pending"
    SYNCING = "syncing"
    SYNCED = "synced"
    PROMOTING = "promoting"
    PROMOTED = "promoted"
    FAILED = "failed"


class BackupState(str, Enum):
    """State of a backup operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTORING = "restoring"
    RESTORED = "restored"


@dataclass
class ReplicationContext:
    """Context for a replication operation."""

    replication_id: str
    primary_node_id: str
    replica_node_id: str
    service_type: str  # 'redis', 'ai-stack', etc.
    state: ReplicationState = ReplicationState.PENDING
    sync_progress: float = 0.0  # 0.0 to 1.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    details: Dict = field(default_factory=dict)


@dataclass
class BackupContext:
    """Context for a backup operation."""

    backup_id: str
    node_id: str
    service_type: str
    backup_path: str
    state: BackupState = BackupState.PENDING
    size_bytes: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    checksum: Optional[str] = None


class StatefulServiceHandler(ABC):
    """Base class for stateful service handlers."""

    def __init__(self, db: SLMDatabaseService, ssh: SSHExecutor):
        """Initialize handler."""
        self.db = db
        self.ssh = ssh

    @property
    @abstractmethod
    def service_type(self) -> str:
        """Service type this handler manages."""

    @abstractmethod
    async def setup_replication(
        self, primary: SLMNode, replica: SLMNode
    ) -> ReplicationContext:
        """Set up replication from primary to replica."""

    @abstractmethod
    async def check_sync_status(
        self, context: ReplicationContext
    ) -> Tuple[bool, float]:
        """Check if replica is synced. Returns (is_synced, progress)."""

    @abstractmethod
    async def promote_replica(self, context: ReplicationContext) -> bool:
        """Promote replica to primary."""

    @abstractmethod
    async def create_backup(
        self, node: SLMNode, backup_path: str
    ) -> BackupContext:
        """Create backup of service data."""

    @abstractmethod
    async def restore_backup(
        self, node: SLMNode, context: BackupContext
    ) -> bool:
        """Restore backup to node."""

    @abstractmethod
    async def verify_data_integrity(self, node: SLMNode) -> Tuple[bool, Dict]:
        """Verify data integrity on node."""


class RedisHandler(StatefulServiceHandler):
    """
    Handler for Redis Stack stateful operations.

    Supports:
    - Redis replication (SLAVEOF/REPLICAOF)
    - RDB snapshot backups
    - Data integrity verification
    """

    @property
    def service_type(self) -> str:
        return "redis"

    async def setup_replication(
        self, primary: SLMNode, replica: SLMNode
    ) -> ReplicationContext:
        """
        Set up Redis replication.

        Uses REPLICAOF command to establish replica.
        """
        from uuid import uuid4

        context = ReplicationContext(
            replication_id=str(uuid4()),
            primary_node_id=primary.id,
            replica_node_id=replica.id,
            service_type=self.service_type,
            started_at=datetime.utcnow(),
        )

        try:
            # Get primary IP for replication
            primary_ip = primary.ip_address
            redis_port = 6379

            # Connect replica to primary
            cmd = f"redis-cli REPLICAOF {primary_ip} {redis_port}"
            result = await self._execute_on_node(replica, cmd)

            if "OK" not in result:
                context.state = ReplicationState.FAILED
                context.error = f"Failed to set up replication: {result}"
                context.completed_at = datetime.utcnow()
                return context

            context.state = ReplicationState.SYNCING
            context.details["primary_ip"] = primary_ip
            context.details["redis_port"] = redis_port

            logger.info(
                "Started Redis replication: %s -> %s",
                replica.name,
                primary.name,
            )

        except Exception as e:
            context.state = ReplicationState.FAILED
            context.error = str(e)
            context.completed_at = datetime.utcnow()
            logger.error("Failed to set up Redis replication: %s", e)

        return context

    async def check_sync_status(
        self, context: ReplicationContext
    ) -> Tuple[bool, float]:
        """
        Check Redis replication sync status.

        Uses INFO replication to check master_link_status and
        master_sync_in_progress.
        """
        replica = self.db.get_node(context.replica_node_id)
        if not replica:
            return False, 0.0

        try:
            cmd = "redis-cli INFO replication"
            result = await self._execute_on_node(replica, cmd)

            # Parse replication info
            info = self._parse_redis_info(result)

            # Check if connected and synced
            master_link = info.get("master_link_status", "down")
            sync_in_progress = info.get("master_sync_in_progress", "1")

            if master_link == "up" and sync_in_progress == "0":
                # Check replication offset
                master_offset = int(info.get("master_repl_offset", "0"))
                replica_offset = int(info.get("slave_repl_offset", "0"))

                if master_offset > 0:
                    progress = min(1.0, replica_offset / master_offset)
                else:
                    progress = 1.0

                is_synced = abs(master_offset - replica_offset) < 100  # Allow small lag

                context.sync_progress = progress
                if is_synced:
                    context.state = ReplicationState.SYNCED

                return is_synced, progress

            # Still syncing
            if "master_sync_left_bytes" in info:
                total = int(info.get("master_sync_total_bytes", "1"))
                left = int(info.get("master_sync_left_bytes", "0"))
                progress = 1.0 - (left / max(total, 1))
                context.sync_progress = progress
                return False, progress

            return False, 0.0

        except Exception as e:
            logger.error("Failed to check Redis sync status: %s", e)
            return False, 0.0

    async def promote_replica(self, context: ReplicationContext) -> bool:
        """
        Promote Redis replica to primary.

        Uses REPLICAOF NO ONE to stop replication and become primary.
        """
        replica = self.db.get_node(context.replica_node_id)
        if not replica:
            context.state = ReplicationState.FAILED
            context.error = "Replica node not found"
            return False

        try:
            context.state = ReplicationState.PROMOTING

            # Stop replication - become primary
            cmd = "redis-cli REPLICAOF NO ONE"
            result = await self._execute_on_node(replica, cmd)

            if "OK" not in result:
                context.state = ReplicationState.FAILED
                context.error = f"Failed to promote: {result}"
                return False

            # Verify it's now a master
            info_cmd = "redis-cli INFO replication"
            info_result = await self._execute_on_node(replica, info_cmd)
            info = self._parse_redis_info(info_result)

            if info.get("role") != "master":
                context.state = ReplicationState.FAILED
                context.error = f"Promotion failed, role is: {info.get('role')}"
                return False

            context.state = ReplicationState.PROMOTED
            context.completed_at = datetime.utcnow()

            logger.info("Promoted Redis replica %s to primary", replica.name)
            return True

        except Exception as e:
            context.state = ReplicationState.FAILED
            context.error = str(e)
            logger.error("Failed to promote Redis replica: %s", e)
            return False

    async def create_backup(
        self, node: SLMNode, backup_path: str
    ) -> BackupContext:
        """
        Create Redis RDB backup.

        Uses BGSAVE and copies the dump.rdb file.
        """
        from uuid import uuid4

        context = BackupContext(
            backup_id=str(uuid4()),
            node_id=node.id,
            service_type=self.service_type,
            backup_path=backup_path,
            started_at=datetime.utcnow(),
        )

        try:
            context.state = BackupState.IN_PROGRESS

            # Trigger BGSAVE
            bgsave_cmd = "redis-cli BGSAVE"
            result = await self._execute_on_node(node, bgsave_cmd)

            if "Background saving started" not in result and "OK" not in result:
                # Check if already in progress
                if "background save already in progress" not in result.lower():
                    context.state = BackupState.FAILED
                    context.error = f"BGSAVE failed: {result}"
                    return context

            # Wait for BGSAVE to complete
            await self._wait_for_bgsave(node)

            # Get Redis data directory
            dir_cmd = "redis-cli CONFIG GET dir"
            dir_result = await self._execute_on_node(node, dir_cmd)
            redis_dir = self._parse_config_value(dir_result)

            if not redis_dir:
                redis_dir = "/var/lib/redis"

            # Copy dump.rdb to backup path
            dump_path = f"{redis_dir}/dump.rdb"
            copy_cmd = f"cp {dump_path} {backup_path}"
            await self._execute_on_node(node, copy_cmd)

            # Get backup size and checksum
            stat_cmd = f"stat -c %s {backup_path} && md5sum {backup_path}"
            stat_result = await self._execute_on_node(node, stat_cmd)
            lines = stat_result.strip().split("\n")

            if len(lines) >= 2:
                context.size_bytes = int(lines[0])
                context.checksum = lines[1].split()[0]

            context.state = BackupState.COMPLETED
            context.completed_at = datetime.utcnow()

            logger.info(
                "Created Redis backup: %s (%d bytes)",
                backup_path,
                context.size_bytes,
            )

        except Exception as e:
            context.state = BackupState.FAILED
            context.error = str(e)
            context.completed_at = datetime.utcnow()
            logger.error("Failed to create Redis backup: %s", e)

        return context

    async def restore_backup(
        self, node: SLMNode, context: BackupContext
    ) -> bool:
        """
        Restore Redis from RDB backup.

        Stops Redis, replaces dump.rdb, restarts Redis.
        """
        try:
            context.state = BackupState.RESTORING

            # Verify backup exists and checksum matches
            if context.checksum:
                verify_cmd = f"md5sum {context.backup_path}"
                verify_result = await self._execute_on_node(node, verify_cmd)
                current_checksum = verify_result.strip().split()[0]

                if current_checksum != context.checksum:
                    context.state = BackupState.FAILED
                    context.error = "Backup checksum mismatch"
                    return False

            # Stop Redis
            stop_cmd = "systemctl stop redis-stack-server"
            await self._execute_on_node(node, stop_cmd)

            # Get Redis data directory
            dir_cmd = "redis-cli CONFIG GET dir 2>/dev/null || echo '/var/lib/redis'"
            dir_result = await self._execute_on_node(node, dir_cmd)
            redis_dir = self._parse_config_value(dir_result)

            if not redis_dir:
                redis_dir = "/var/lib/redis"

            # Replace dump.rdb
            restore_cmd = f"cp {context.backup_path} {redis_dir}/dump.rdb"
            await self._execute_on_node(node, restore_cmd)

            # Set permissions
            perm_cmd = f"chown redis:redis {redis_dir}/dump.rdb"
            await self._execute_on_node(node, perm_cmd)

            # Start Redis
            start_cmd = "systemctl start redis-stack-server"
            await self._execute_on_node(node, start_cmd)

            # Wait for Redis to be ready
            await asyncio.sleep(2)

            # Verify Redis is up
            ping_cmd = "redis-cli PING"
            ping_result = await self._execute_on_node(node, ping_cmd)

            if "PONG" not in ping_result:
                context.state = BackupState.FAILED
                context.error = "Redis failed to start after restore"
                return False

            context.state = BackupState.RESTORED

            logger.info("Restored Redis backup on %s", node.name)
            return True

        except Exception as e:
            context.state = BackupState.FAILED
            context.error = str(e)
            logger.error("Failed to restore Redis backup: %s", e)
            return False

    async def verify_data_integrity(self, node: SLMNode) -> Tuple[bool, Dict]:
        """
        Verify Redis data integrity.

        Checks:
        - Key count
        - Memory usage
        - RDB status
        """
        result = {
            "keyspace": {},
            "memory": {},
            "persistence": {},
            "errors": [],
        }

        try:
            # Get keyspace info
            info_cmd = "redis-cli INFO keyspace"
            keyspace_result = await self._execute_on_node(node, info_cmd)
            result["keyspace"] = self._parse_redis_info(keyspace_result)

            # Get memory info
            mem_cmd = "redis-cli INFO memory"
            mem_result = await self._execute_on_node(node, mem_cmd)
            mem_info = self._parse_redis_info(mem_result)
            result["memory"] = {
                "used_memory": mem_info.get("used_memory", "0"),
                "used_memory_human": mem_info.get("used_memory_human", "0B"),
                "maxmemory": mem_info.get("maxmemory", "0"),
            }

            # Get persistence info
            persist_cmd = "redis-cli INFO persistence"
            persist_result = await self._execute_on_node(node, persist_cmd)
            persist_info = self._parse_redis_info(persist_result)
            result["persistence"] = {
                "rdb_last_save_time": persist_info.get("rdb_last_save_time", "0"),
                "rdb_last_bgsave_status": persist_info.get(
                    "rdb_last_bgsave_status", "unknown"
                ),
                "aof_enabled": persist_info.get("aof_enabled", "0"),
            }

            # Check for errors
            if persist_info.get("rdb_last_bgsave_status") != "ok":
                result["errors"].append("Last RDB save failed")

            is_healthy = len(result["errors"]) == 0
            return is_healthy, result

        except Exception as e:
            result["errors"].append(str(e))
            logger.error("Failed to verify Redis data integrity: %s", e)
            return False, result

    async def _execute_on_node(self, node: SLMNode, command: str) -> str:
        """Execute command on node via SSH."""
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.ssh.execute(
                host=node.ip_address,
                user=node.ssh_user,
                command=command,
            ),
        )

    async def _wait_for_bgsave(self, node: SLMNode, timeout: int = 120):
        """Wait for BGSAVE to complete."""
        start = datetime.utcnow()
        while True:
            elapsed = (datetime.utcnow() - start).total_seconds()
            if elapsed > timeout:
                raise TimeoutError("BGSAVE timeout")

            cmd = "redis-cli LASTSAVE"
            result = await self._execute_on_node(node, cmd)

            # Check if in progress
            info_cmd = "redis-cli INFO persistence"
            info_result = await self._execute_on_node(node, info_cmd)
            info = self._parse_redis_info(info_result)

            if info.get("rdb_bgsave_in_progress", "0") == "0":
                break

            await asyncio.sleep(1)

    def _parse_redis_info(self, info_str: str) -> Dict[str, str]:
        """Parse Redis INFO command output."""
        result = {}
        for line in info_str.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        return result

    def _parse_config_value(self, config_str: str) -> Optional[str]:
        """Parse Redis CONFIG GET output."""
        lines = config_str.strip().split("\n")
        if len(lines) >= 2:
            return lines[1].strip()
        return None


class ReplicatedSwapStrategy:
    """
    Strategy for zero-downtime updates using replication.

    Process:
    1. Set up replica on standby node
    2. Wait for sync
    3. Promote replica
    4. Update original
    5. Switchback if needed
    """

    def __init__(self, db: SLMDatabaseService, ssh: SSHExecutor):
        """Initialize strategy."""
        self.db = db
        self.ssh = ssh
        self.handlers: Dict[str, StatefulServiceHandler] = {
            "redis": RedisHandler(db, ssh),
        }

    def get_handler(self, service_type: str) -> Optional[StatefulServiceHandler]:
        """Get handler for service type."""
        return self.handlers.get(service_type)

    async def execute_replicated_update(
        self,
        primary_node_id: str,
        standby_node_id: str,
        service_type: str,
        update_callback: Optional[callable] = None,
    ) -> Tuple[bool, str]:
        """
        Execute zero-downtime update using replication.

        Args:
            primary_node_id: Current primary node ID
            standby_node_id: Standby node to use as temporary primary
            service_type: Type of service (redis, etc.)
            update_callback: Callback to perform the actual update

        Returns:
            Tuple of (success, message)
        """
        handler = self.get_handler(service_type)
        if not handler:
            return False, f"No handler for service type: {service_type}"

        primary = self.db.get_node(primary_node_id)
        standby = self.db.get_node(standby_node_id)

        if not primary or not standby:
            return False, "Primary or standby node not found"

        logger.info(
            "Starting replicated update: %s -> %s (%s)",
            primary.name,
            standby.name,
            service_type,
        )

        # Phase 1: Set up replication
        repl_ctx = await handler.setup_replication(primary, standby)
        if repl_ctx.state == ReplicationState.FAILED:
            return False, f"Replication setup failed: {repl_ctx.error}"

        # Phase 2: Wait for sync
        sync_timeout = 600  # 10 minutes
        sync_start = datetime.utcnow()

        while True:
            is_synced, progress = await handler.check_sync_status(repl_ctx)

            if is_synced:
                logger.info("Replication sync complete")
                break

            elapsed = (datetime.utcnow() - sync_start).total_seconds()
            if elapsed > sync_timeout:
                return False, "Sync timeout"

            logger.info("Sync progress: %.1f%%", progress * 100)
            await asyncio.sleep(5)

        # Phase 3: Promote standby
        promote_success = await handler.promote_replica(repl_ctx)
        if not promote_success:
            return False, f"Promotion failed: {repl_ctx.error}"

        # Phase 4: Update original (via callback)
        if update_callback:
            try:
                await update_callback(primary)
            except Exception as e:
                logger.error("Update callback failed: %s", e)
                # Standby remains primary - manual intervention needed
                return False, f"Update failed, standby is now primary: {e}"

        # Phase 5: Verify data integrity on both nodes
        primary_ok, _ = await handler.verify_data_integrity(primary)
        standby_ok, _ = await handler.verify_data_integrity(standby)

        if not primary_ok or not standby_ok:
            logger.warning(
                "Data integrity check failed: primary=%s, standby=%s",
                primary_ok,
                standby_ok,
            )

        return True, "Replicated update completed successfully"


class StatefulServiceManager:
    """
    Manager for stateful service operations.

    Provides unified interface for:
    - Replication-based updates
    - Backup/restore
    - Data verification
    """

    def __init__(
        self,
        db: Optional[SLMDatabaseService] = None,
        ssh: Optional[SSHExecutor] = None,
        backup_dir: str = "/opt/autobot-admin/backups",
    ):
        """Initialize manager."""
        self.db = db or SLMDatabaseService()
        self.ssh = ssh or SSHExecutor()
        self.backup_dir = backup_dir
        self.handlers: Dict[str, StatefulServiceHandler] = {
            "redis": RedisHandler(self.db, self.ssh),
        }
        self._active_replications: Dict[str, ReplicationContext] = {}
        self._active_backups: Dict[str, BackupContext] = {}

    def get_handler(self, service_type: str) -> Optional[StatefulServiceHandler]:
        """Get handler for service type."""
        return self.handlers.get(service_type)

    async def start_replication(
        self,
        primary_node_id: str,
        replica_node_id: str,
        service_type: str,
    ) -> ReplicationContext:
        """Start replication from primary to replica."""
        handler = self.get_handler(service_type)
        if not handler:
            ctx = ReplicationContext(
                replication_id="error",
                primary_node_id=primary_node_id,
                replica_node_id=replica_node_id,
                service_type=service_type,
                state=ReplicationState.FAILED,
                error=f"No handler for service type: {service_type}",
            )
            return ctx

        primary = self.db.get_node(primary_node_id)
        replica = self.db.get_node(replica_node_id)

        if not primary or not replica:
            ctx = ReplicationContext(
                replication_id="error",
                primary_node_id=primary_node_id,
                replica_node_id=replica_node_id,
                service_type=service_type,
                state=ReplicationState.FAILED,
                error="Primary or replica node not found",
            )
            return ctx

        context = await handler.setup_replication(primary, replica)
        self._active_replications[context.replication_id] = context
        return context

    async def check_replication_sync(
        self, replication_id: str
    ) -> Tuple[bool, float]:
        """Check if replication is synced."""
        context = self._active_replications.get(replication_id)
        if not context:
            return False, 0.0

        handler = self.get_handler(context.service_type)
        if not handler:
            return False, 0.0

        return await handler.check_sync_status(context)

    async def promote_replica(self, replication_id: str) -> bool:
        """Promote replica to primary."""
        context = self._active_replications.get(replication_id)
        if not context:
            return False

        handler = self.get_handler(context.service_type)
        if not handler:
            return False

        return await handler.promote_replica(context)

    async def create_backup(
        self,
        node_id: str,
        service_type: str,
        backup_name: Optional[str] = None,
    ) -> BackupContext:
        """Create backup for a service on a node."""
        handler = self.get_handler(service_type)
        if not handler:
            return BackupContext(
                backup_id="error",
                node_id=node_id,
                service_type=service_type,
                backup_path="",
                state=BackupState.FAILED,
                error=f"No handler for service type: {service_type}",
            )

        node = self.db.get_node(node_id)
        if not node:
            return BackupContext(
                backup_id="error",
                node_id=node_id,
                service_type=service_type,
                backup_path="",
                state=BackupState.FAILED,
                error="Node not found",
            )

        # Generate backup path
        if not backup_name:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{service_type}_{node.name}_{timestamp}"

        backup_path = f"{self.backup_dir}/{backup_name}.rdb"

        context = await handler.create_backup(node, backup_path)
        self._active_backups[context.backup_id] = context
        return context

    async def restore_backup(self, backup_id: str) -> bool:
        """Restore a backup to its original node."""
        context = self._active_backups.get(backup_id)
        if not context:
            return False

        handler = self.get_handler(context.service_type)
        if not handler:
            return False

        node = self.db.get_node(context.node_id)
        if not node:
            return False

        return await handler.restore_backup(node, context)

    async def verify_data(
        self, node_id: str, service_type: str
    ) -> Tuple[bool, Dict]:
        """Verify data integrity on a node."""
        handler = self.get_handler(service_type)
        if not handler:
            return False, {"error": f"No handler for service type: {service_type}"}

        node = self.db.get_node(node_id)
        if not node:
            return False, {"error": "Node not found"}

        return await handler.verify_data_integrity(node)

    def get_replication(self, replication_id: str) -> Optional[ReplicationContext]:
        """Get replication context by ID."""
        return self._active_replications.get(replication_id)

    def get_backup(self, backup_id: str) -> Optional[BackupContext]:
        """Get backup context by ID."""
        return self._active_backups.get(backup_id)

    @property
    def active_replications(self) -> List[ReplicationContext]:
        """Get all active replications."""
        return list(self._active_replications.values())

    @property
    def active_backups(self) -> List[BackupContext]:
        """Get all active/completed backups."""
        return list(self._active_backups.values())


# Singleton instance
_stateful_manager: Optional[StatefulServiceManager] = None


def get_stateful_manager() -> StatefulServiceManager:
    """Get or create the singleton stateful service manager."""
    global _stateful_manager
    if _stateful_manager is None:
        _stateful_manager = StatefulServiceManager()
    return _stateful_manager
