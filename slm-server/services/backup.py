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
            # Step 0: Discover Redis configuration (data dir, auth)
            # Use REDISCLI_AUTH env var to avoid shell escaping issues with special chars
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
                # Use env var to pass password safely (avoids shell escaping issues)
                redis_auth_prefix = f"REDISCLI_AUTH=$(grep -E '^requirepass' /etc/redis/redis.conf | awk '{{print $2}}')"

            # Get Redis data directory and filename using env var for auth
            config_cmd = self._build_ssh_command(
                host,
                ssh_user,
                ssh_port,
                f"{redis_auth_prefix} redis-cli CONFIG GET dir && {redis_auth_prefix} redis-cli CONFIG GET dbfilename",
            )
            success, config_output = await self._run_command(config_cmd, timeout=15)

            # Parse Redis config output (format: "dir\n/path\ndbfilename\nfilename")
            redis_dir = "/var/lib/redis"  # default fallback
            redis_dbfilename = "dump.rdb"  # default fallback
            if success:
                lines = [
                    l.strip() for l in config_output.strip().split("\n") if l.strip()
                ]
                for i, line in enumerate(lines):
                    if line == "dir" and i + 1 < len(lines):
                        redis_dir = lines[i + 1]
                    elif line == "dbfilename" and i + 1 < len(lines):
                        redis_dbfilename = lines[i + 1]

            rdb_path = f"{redis_dir}/{redis_dbfilename}"
            logger.info("Redis RDB path discovered: %s", rdb_path)

            # Step 1: Trigger BGSAVE
            logger.info("Starting Redis BGSAVE on %s", host)
            bgsave_cmd = self._build_ssh_command(
                host, ssh_user, ssh_port, f"{redis_auth_prefix} redis-cli BGSAVE"
            )
            success, output = await self._run_command(bgsave_cmd, timeout=30)
            if not success:
                return await self._fail_backup(db, backup, f"BGSAVE failed: {output}")

            # Step 2: Wait for BGSAVE to complete
            logger.info("Waiting for BGSAVE to complete...")
            await self._wait_for_bgsave(host, ssh_user, ssh_port, redis_auth_prefix)

            # Step 3: Get RDB file size
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

            # Step 4: Calculate checksum
            checksum_cmd = self._build_ssh_command(
                host,
                ssh_user,
                ssh_port,
                f"sha256sum {rdb_path} 2>/dev/null | cut -d' ' -f1",
            )
            success, checksum = await self._run_command(checksum_cmd, timeout=60)
            checksum = checksum.strip() if success else None

            # Step 5: Copy backup to SLM storage
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

            if not success:
                # Backup exists on remote but copy failed - still record it
                backup.status = BackupStatus.COMPLETED.value
                backup.backup_path = "/var/lib/redis/dump.rdb"
                backup.size_bytes = size_bytes
                backup.checksum = checksum
                backup.extra_data = {
                    "location": "remote",
                    "host": host,
                    "copy_error": scp_output,
                }
            else:
                # Verify local checksum matches
                local_checksum = await self._calculate_checksum(backup_path)
                if checksum and local_checksum != checksum:
                    logger.warning(
                        "Checksum mismatch: remote=%s, local=%s",
                        checksum,
                        local_checksum,
                    )
                    backup.extra_data = {"checksum_warning": "mismatch detected"}

                backup.status = BackupStatus.COMPLETED.value
                backup.backup_path = str(backup_path)
                backup.size_bytes = (
                    backup_path.stat().st_size if backup_path.exists() else size_bytes
                )
                backup.checksum = local_checksum or checksum
                backup.extra_data = {
                    "location": "local",
                    "remote_checksum": checksum,
                    "local_checksum": local_checksum,
                }

            backup.completed_at = datetime.utcnow()
            await db.commit()

            logger.info(
                "Backup %s completed: %s bytes, checksum=%s",
                backup_id,
                backup.size_bytes,
                backup.checksum,
            )
            return True, "Backup completed successfully"

        except asyncio.TimeoutError:
            return await self._fail_backup(db, backup, "Backup timed out")
        except Exception as e:
            logger.exception("Backup error: %s", e)
            return await self._fail_backup(db, backup, str(e))

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
            logger.info("Stopping Redis on %s for restore", host)
            stop_cmd = self._build_ssh_command(
                host, ssh_user, ssh_port, "sudo systemctl stop redis-server"
            )
            await self._run_command(stop_cmd, timeout=30)

            # Step 2: Copy backup file to target
            backup_path = backup.backup_path
            if backup.extra_data and backup.extra_data.get("location") == "local":
                # Copy from SLM storage
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
            else:
                # Backup is on the same node, just verify it exists
                verify_cmd = self._build_ssh_command(
                    host, ssh_user, ssh_port, f"test -f {backup_path} && echo 'exists'"
                )
                success, output = await self._run_command(verify_cmd, timeout=10)
                if not success or "exists" not in output:
                    return False, "Backup file not found on target"

            # Step 3: Start Redis
            logger.info("Starting Redis on %s after restore", host)
            start_cmd = self._build_ssh_command(
                host, ssh_user, ssh_port, "sudo systemctl start redis-server"
            )
            success, output = await self._run_command(start_cmd, timeout=30)
            if not success:
                return False, f"Failed to start Redis: {output}"

            # Step 4: Wait for Redis to be ready and verify data
            await asyncio.sleep(3)  # Give Redis time to load data

            verify_cmd = self._build_ssh_command(
                host, ssh_user, ssh_port, "redis-cli PING && redis-cli DBSIZE"
            )
            success, verify_output = await self._run_command(verify_cmd, timeout=15)
            if not success or "PONG" not in verify_output:
                return False, f"Redis not healthy after restore: {verify_output}"

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


# Global service instance
backup_service = BackupService()
