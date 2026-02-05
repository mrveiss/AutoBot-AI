# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Backup Service

Handles backup execution, verification, and restore operations
for stateful services (Redis, PostgreSQL, etc).
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Backup, BackupStatus, Node

logger = logging.getLogger(__name__)

# Backup storage directory
BACKUP_STORAGE_DIR = Path(
    settings.backup_dir if hasattr(settings, "backup_dir") else "/var/lib/slm/backups"
)


class BackupService:
    """Manages backup operations for stateful services."""

    def __init__(self):
        # Ensure backup directory exists
        BACKUP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    async def execute_redis_backup(
        self,
        db: AsyncSession,
        backup_id: str,
        node: Node,
    ) -> Tuple[bool, str]:
        """Execute a Redis backup with BGSAVE and checksum verification.

        Returns (success, message).
        """
        host = node.ip_address
        ssh_user = node.ssh_user or "autobot"
        ssh_port = node.ssh_port or 22

        # Update backup status to in_progress
        result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
        backup = result.scalar_one_or_none()
        if not backup:
            return False, "Backup not found"

        backup.status = BackupStatus.IN_PROGRESS.value
        backup.started_at = datetime.utcnow()
        await db.commit()

        try:
            # Step 1: Discover Redis configuration (data dir, auth)
            redis_auth_prefix, rdb_path = await self._discover_redis_config(
                host, ssh_user, ssh_port
            )

            # Step 2: Trigger BGSAVE
            logger.info("Starting Redis BGSAVE on %s", host)
            bgsave_cmd = self._build_ssh_command(
                host, ssh_user, ssh_port, f"{redis_auth_prefix} redis-cli BGSAVE"
            )
            success, output = await self._run_command(bgsave_cmd, timeout=30)
            if not success:
                return await self._fail_backup(db, backup, f"BGSAVE failed: {output}")

            # Step 3: Wait for BGSAVE to complete
            logger.info("Waiting for BGSAVE to complete...")
            await self._wait_for_bgsave(host, ssh_user, ssh_port, redis_auth_prefix)

            # Step 4: Get RDB file size and checksum
            size_bytes, checksum = await self._get_rdb_file_info(
                host, ssh_user, ssh_port, rdb_path
            )

            # Step 5: Copy backup to SLM storage
            copy_success, backup_path, copy_error = await self._copy_backup_to_storage(
                host, ssh_user, ssh_port, rdb_path, backup_id
            )

            # Step 6: Complete backup and update record
            return await self._complete_backup(
                db,
                backup,
                copy_success,
                backup_path,
                size_bytes,
                checksum,
                host,
                copy_error,
            )

        except asyncio.TimeoutError:
            return await self._fail_backup(db, backup, "Backup timed out")
        except Exception as e:
            logger.exception("Backup error: %s", e)
            return await self._fail_backup(db, backup, str(e))

    async def _stop_redis_for_restore(
        self, host: str, ssh_user: str, ssh_port: int
    ) -> None:
        """Stop Redis service on the target node.

        Helper for execute_restore (Issue #665).
        """
        logger.info("Stopping Redis on %s for restore", host)
        stop_cmd = self._build_ssh_command(
            host, ssh_user, ssh_port, "sudo systemctl stop redis-server"
        )
        await self._run_command(stop_cmd, timeout=30)

    async def _copy_local_backup_to_target(
        self, backup: Backup, host: str, ssh_user: str, ssh_port: int
    ) -> Tuple[bool, str]:
        """Copy local backup file to target node and move to Redis directory.

        Helper for execute_restore (Issue #665).

        Returns (success, error_message).
        """
        backup_path = backup.backup_path

        # Copy from SLM storage to temporary location
        scp_cmd = [
            "/usr/bin/scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-P",
            str(ssh_port),
            backup_path,
            f"{ssh_user}@{host}:/tmp/restore.rdb",
        ]
        success, _ = await self._run_command(scp_cmd, timeout=300)
        if not success:
            return False, "Failed to copy backup to target"

        # Move file to Redis data directory
        mv_cmd = self._build_ssh_command(
            host,
            ssh_user,
            ssh_port,
            "sudo mv /tmp/restore.rdb /var/lib/redis/dump.rdb && "
            "sudo chown redis:redis /var/lib/redis/dump.rdb",
        )
        success, output = await self._run_command(mv_cmd, timeout=30)
        if not success:
            return False, f"Failed to move backup file: {output}"

        return True, ""

    async def _verify_remote_backup_exists(
        self, backup_path: str, host: str, ssh_user: str, ssh_port: int
    ) -> Tuple[bool, str]:
        """Verify that a remote backup file exists on the target node.

        Helper for execute_restore (Issue #665).

        Returns (success, error_message).
        """
        verify_cmd = self._build_ssh_command(
            host, ssh_user, ssh_port, f"test -f {backup_path} && echo 'exists'"
        )
        success, output = await self._run_command(verify_cmd, timeout=10)
        if not success or "exists" not in output:
            return False, "Backup file not found on target"

        return True, ""

    async def _start_and_verify_redis(
        self, host: str, ssh_user: str, ssh_port: int
    ) -> Tuple[bool, str]:
        """Start Redis service and verify it's healthy.

        Helper for execute_restore (Issue #665).

        Returns (success, status_output).
        """
        # Start Redis
        logger.info("Starting Redis on %s after restore", host)
        start_cmd = self._build_ssh_command(
            host, ssh_user, ssh_port, "sudo systemctl start redis-server"
        )
        success, output = await self._run_command(start_cmd, timeout=30)
        if not success:
            return False, f"Failed to start Redis: {output}"

        # Wait for Redis to be ready and verify data
        await asyncio.sleep(3)  # Give Redis time to load data

        verify_cmd = self._build_ssh_command(
            host, ssh_user, ssh_port, "redis-cli PING && redis-cli DBSIZE"
        )
        success, verify_output = await self._run_command(verify_cmd, timeout=15)
        if not success or "PONG" not in verify_output:
            return False, f"Redis not healthy after restore: {verify_output}"

        return True, verify_output

    async def execute_restore(
        self,
        db: AsyncSession,
        backup_id: str,
        target_node: Node,
    ) -> Tuple[bool, str]:
        """Restore a Redis backup to a target node.

        Returns (success, message).
        """
        result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
        backup = result.scalar_one_or_none()
        if not backup:
            return False, "Backup not found"

        if backup.status != BackupStatus.COMPLETED.value:
            return False, f"Cannot restore backup in status: {backup.status}"

        host = target_node.ip_address
        ssh_user = target_node.ssh_user or "autobot"
        ssh_port = target_node.ssh_port or 22

        try:
            # Step 1: Stop Redis
            await self._stop_redis_for_restore(host, ssh_user, ssh_port)

            # Step 2: Copy backup file to target
            backup_path = backup.backup_path
            if backup.extra_data and backup.extra_data.get("location") == "local":
                success, error = await self._copy_local_backup_to_target(
                    backup, host, ssh_user, ssh_port
                )
                if not success:
                    return False, error
            else:
                success, error = await self._verify_remote_backup_exists(
                    backup_path, host, ssh_user, ssh_port
                )
                if not success:
                    return False, error

            # Step 3: Start Redis and verify
            success, verify_output = await self._start_and_verify_redis(
                host, ssh_user, ssh_port
            )
            if not success:
                return False, verify_output

            logger.info("Restore completed successfully to %s", host)
            return True, f"Restore completed. Redis status: {verify_output}"

        except Exception as e:
            logger.exception("Restore error: %s", e)
            return False, str(e)

    async def verify_backup_integrity(
        self,
        backup_id: str,
    ) -> Dict:
        """Verify a backup's integrity by checking its checksum.

        Returns verification result with details.
        """
        from services.database import db_service

        async with db_service.session() as db:
            result = await db.execute(
                select(Backup).where(Backup.backup_id == backup_id)
            )
            backup = result.scalar_one_or_none()
            if not backup:
                return {"valid": False, "error": "Backup not found"}

            if not backup.backup_path or not Path(backup.backup_path).exists():
                return {"valid": False, "error": "Backup file not found"}

            # Calculate current checksum
            current_checksum = await self._calculate_checksum(Path(backup.backup_path))

            # Compare with stored checksum
            if backup.checksum and current_checksum == backup.checksum:
                return {
                    "valid": True,
                    "backup_id": backup_id,
                    "checksum": current_checksum,
                    "size_bytes": backup.size_bytes,
                    "message": "Backup integrity verified",
                }
            elif backup.checksum:
                return {
                    "valid": False,
                    "backup_id": backup_id,
                    "expected_checksum": backup.checksum,
                    "actual_checksum": current_checksum,
                    "error": "Checksum mismatch - backup may be corrupted",
                }
            else:
                return {
                    "valid": True,
                    "backup_id": backup_id,
                    "checksum": current_checksum,
                    "warning": "No stored checksum to verify against",
                }

    async def _wait_for_bgsave(
        self,
        host: str,
        ssh_user: str,
        ssh_port: int,
        redis_auth_prefix: str = "",
        max_wait: int = 120,
    ) -> bool:
        """Wait for BGSAVE to complete by monitoring LASTSAVE."""
        start_time = datetime.utcnow()
        initial_lastsave = None

        while (datetime.utcnow() - start_time).seconds < max_wait:
            cmd = self._build_ssh_command(
                host, ssh_user, ssh_port, f"{redis_auth_prefix} redis-cli LASTSAVE"
            )
            success, output = await self._run_command(cmd, timeout=10)

            if success:
                try:
                    lastsave = int(output.strip())
                    if initial_lastsave is None:
                        initial_lastsave = lastsave
                    elif lastsave > initial_lastsave:
                        logger.info("BGSAVE completed (LASTSAVE: %d)", lastsave)
                        return True
                except (ValueError, TypeError):
                    pass

            await asyncio.sleep(2)

        return False

    async def _fail_backup(
        self, db: AsyncSession, backup: Backup, error: str
    ) -> Tuple[bool, str]:
        """Mark backup as failed and return error."""
        backup.status = BackupStatus.FAILED.value
        backup.error = error[:500]
        backup.completed_at = datetime.utcnow()
        await db.commit()
        logger.error("Backup %s failed: %s", backup.backup_id, error)
        return False, error

    def _build_ssh_command(self, host: str, user: str, port: int, command: str) -> list:
        """Build SSH command list."""
        return [
            "/usr/bin/ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "BatchMode=yes",
            "-p",
            str(port),
            f"{user}@{host}",
            command,
        ]

    async def _run_command(self, cmd: list, timeout: int = 60) -> Tuple[bool, str]:
        """Run a command and return (success, output)."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
            return process.returncode == 0, output
        except asyncio.TimeoutError:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    async def _calculate_checksum(self, path: Path) -> Optional[str]:
        """Calculate SHA256 checksum of a file."""
        if not path.exists():
            return None

        try:
            sha256 = hashlib.sha256()
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.warning("Checksum calculation failed: %s", e)
            return None

    async def _discover_redis_config(
        self, host: str, ssh_user: str, ssh_port: int
    ) -> Tuple[str, str]:
        """Discover Redis authentication prefix and RDB file path.

        Helper for execute_redis_backup (Issue #665).

        Returns (redis_auth_prefix, rdb_path).
        """
        # Check for Redis authentication
        redis_auth_prefix = ""
        auth_cmd = self._build_ssh_command(
            host,
            ssh_user,
            ssh_port,
            "grep -E '^requirepass' /etc/redis/redis.conf 2>/dev/null | awk '{print $2}'",
        )
        success, auth_output = await self._run_command(auth_cmd, timeout=10)
        redis_password = auth_output.strip() if success else ""
        if redis_password:
            redis_auth_prefix = (
                "REDISCLI_AUTH=$(grep -E '^requirepass' /etc/redis/redis.conf "
                "| awk '{print $2}')"
            )

        # Get Redis data directory and filename
        config_cmd = self._build_ssh_command(
            host,
            ssh_user,
            ssh_port,
            f"{redis_auth_prefix} redis-cli CONFIG GET dir && "
            f"{redis_auth_prefix} redis-cli CONFIG GET dbfilename",
        )
        success, config_output = await self._run_command(config_cmd, timeout=15)

        redis_dir = "/var/lib/redis"
        redis_dbfilename = "dump.rdb"
        if success:
            lines = [
                ln.strip() for ln in config_output.strip().split("\n") if ln.strip()
            ]
            for i, line in enumerate(lines):
                if line == "dir" and i + 1 < len(lines):
                    redis_dir = lines[i + 1]
                elif line == "dbfilename" and i + 1 < len(lines):
                    redis_dbfilename = lines[i + 1]

        rdb_path = f"{redis_dir}/{redis_dbfilename}"
        logger.info("Redis RDB path discovered: %s", rdb_path)
        return redis_auth_prefix, rdb_path

    async def _get_rdb_file_info(
        self, host: str, ssh_user: str, ssh_port: int, rdb_path: str
    ) -> Tuple[int, Optional[str]]:
        """Get RDB file size and checksum from remote host.

        Helper for execute_redis_backup (Issue #665).

        Returns (size_bytes, checksum).
        """
        # Get file size
        size_cmd = self._build_ssh_command(
            host,
            ssh_user,
            ssh_port,
            f"stat -c '%s' {rdb_path} 2>/dev/null || echo '0'",
        )
        success, size_output = await self._run_command(size_cmd, timeout=15)
        size_bytes = 0
        if success:
            size_str = size_output.strip().split("\n")[-1]
            if size_str.isdigit():
                size_bytes = int(size_str)

        # Calculate remote checksum
        checksum_cmd = self._build_ssh_command(
            host,
            ssh_user,
            ssh_port,
            f"sha256sum {rdb_path} 2>/dev/null | cut -d' ' -f1",
        )
        success, checksum = await self._run_command(checksum_cmd, timeout=60)
        checksum = checksum.strip() if success else None

        return size_bytes, checksum

    async def _copy_backup_to_storage(
        self,
        host: str,
        ssh_user: str,
        ssh_port: int,
        rdb_path: str,
        backup_id: str,
    ) -> Tuple[bool, Path, str]:
        """Copy RDB backup file from remote host to local storage via SCP.

        Helper for execute_redis_backup (Issue #665).

        Returns (success, backup_path, error_output).
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{backup_id}_{timestamp}.rdb"
        backup_path = BACKUP_STORAGE_DIR / backup_filename

        scp_cmd = [
            "/usr/bin/scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=30",
            "-P",
            str(ssh_port),
            f"{ssh_user}@{host}:{rdb_path}",
            str(backup_path),
        ]
        success, scp_output = await self._run_command(scp_cmd, timeout=300)
        return success, backup_path, scp_output

    async def _complete_backup(
        self,
        db: AsyncSession,
        backup: Backup,
        copy_success: bool,
        backup_path: Path,
        size_bytes: int,
        remote_checksum: Optional[str],
        host: str,
        copy_error: str = "",
    ) -> Tuple[bool, str]:
        """Update backup record with results and complete the backup.

        Helper for execute_redis_backup (Issue #665).

        Returns (success, message).
        """
        if not copy_success:
            # Backup exists on remote but copy failed - still record it
            backup.status = BackupStatus.COMPLETED.value
            backup.backup_path = "/var/lib/redis/dump.rdb"
            backup.size_bytes = size_bytes
            backup.checksum = remote_checksum
            backup.extra_data = {
                "location": "remote",
                "host": host,
                "copy_error": copy_error,
            }
        else:
            # Verify local checksum matches
            local_checksum = await self._calculate_checksum(backup_path)
            if remote_checksum and local_checksum != remote_checksum:
                logger.warning(
                    "Checksum mismatch: remote=%s, local=%s",
                    remote_checksum,
                    local_checksum,
                )
                backup.extra_data = {"checksum_warning": "mismatch detected"}

            backup.status = BackupStatus.COMPLETED.value
            backup.backup_path = str(backup_path)
            backup.size_bytes = (
                backup_path.stat().st_size if backup_path.exists() else size_bytes
            )
            backup.checksum = local_checksum or remote_checksum
            backup.extra_data = {
                "location": "local",
                "remote_checksum": remote_checksum,
                "local_checksum": local_checksum,
            }

        backup.completed_at = datetime.utcnow()
        await db.commit()

        logger.info(
            "Backup %s completed: %s bytes, checksum=%s",
            backup.backup_id,
            backup.size_bytes,
            backup.checksum,
        )
        return True, "Backup completed successfully"


# Global service instance
backup_service = BackupService()
