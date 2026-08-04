# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Backup Service

Handles backup execution, verification, and restore operations
for stateful services (Redis, PostgreSQL, etc).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Backup, BackupStatus, Node

logger = logging.getLogger(__name__)

# Backup storage directory.
#
# #13307: the `hasattr` fallback was dead code — `settings` has always defined
# `backup_dir` — so the /var/lib/slm/backups written here never applied and the
# real destination was config.py's `~/slm-backups`. Two files naming different
# defaults, with the unreachable one being the correct answer. `settings` is now
# the single source and already resolves to /var/lib/slm/backups.
BACKUP_STORAGE_DIR = Path(settings.backup_dir)


class BackupService:
    """Manages backup operations for stateful services."""

    def __init__(self):
        # #13307: best-effort, never fatal. `backup_service` is instantiated at
        # module import, and the destination moved from the service account's
        # home directory (always writable) to /var/lib/slm/backups (owned by
        # root until the slm_manager role creates it). An unguarded mkdir here
        # raises PermissionError and makes `import services.backup` fail
        # outright — taking the whole API down on any host where ansible has
        # not run yet, and in CI. The directory is the role's responsibility;
        # this is only a convenience for dev, and a failed backup reports the
        # real reason at the point it actually matters.
        self._ensure_storage_dir()

    @staticmethod
    def _ensure_storage_dir() -> bool:
        """Create the backup directory if we can. Returns whether it is usable."""
        try:
            BACKUP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            return True
        except OSError as exc:
            logger.warning(
                "Backup storage directory %s is not usable (%s). The slm_manager "
                "ansible role creates it with the right ownership; backups will "
                "fail until it exists.",
                BACKUP_STORAGE_DIR,
                exc,
            )
            return False

    async def _mark_backup_in_progress(self, db: AsyncSession, backup_id: str) -> "Backup" | None:
        """Mark backup as in_progress and return record. Helper for execute_redis_backup. Ref: #1088."""
        result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
        backup = result.scalar_one_or_none()
        if backup:
            backup.status = BackupStatus.IN_PROGRESS.value
            backup.started_at = datetime.now(timezone.utc)
            await db.commit()
        return backup

    async def execute_redis_backup(
        self,
        db: AsyncSession,
        backup_id: str,
        node: Node,
    ) -> Tuple[bool, str]:
        """Execute a Redis backup with BGSAVE and checksum verification. Ref: #1088."""
        host = node.ip_address
        ssh_user = node.ssh_user or "autobot"
        ssh_port = node.ssh_port or 22

        backup = await self._mark_backup_in_progress(db, backup_id)
        if not backup:
            return False, "Backup not found"

        try:
            # Step 1: Discover Redis configuration (data dir, auth)
            redis_auth_prefix, rdb_path = await self._discover_redis_config(host, ssh_user, ssh_port)

            # Step 2: Trigger BGSAVE
            logger.info("Starting Redis BGSAVE on %s", host)
            bgsave_cmd = self._build_ssh_command(host, ssh_user, ssh_port, f"{redis_auth_prefix} redis-cli BGSAVE")
            success, output = await self._run_command(bgsave_cmd, timeout=30)
            if not success:
                return await self._fail_backup(db, backup, f"BGSAVE failed: {output}")

            # Step 3: Wait for BGSAVE to complete
            logger.info("Waiting for BGSAVE to complete...")
            await self._wait_for_bgsave(host, ssh_user, ssh_port, redis_auth_prefix)

            # Step 4: Get RDB file size and checksum
            size_bytes, checksum = await self._get_remote_file_info(host, ssh_user, ssh_port, rdb_path)

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
            return await self._fail_backup(db, backup, "Backup operation failed")

    async def execute_postgres_backup(
        self,
        db: AsyncSession,
        backup_id: str,
        node: Node,
    ) -> Tuple[bool, str]:
        """Execute a full PostgreSQL cluster dump (#13307).

        Until this existed the Backups page created something called a backup
        that contained only Redis. PostgreSQL holds users, LLC work items and
        chat/session data — a restore would not bring any of it back, and you
        would find that out during recovery.

        The dump command mirrors ``roles/postgresql/templates/autobot-pg-backup.sh.j2``
        exactly: ``su - postgres -c "pg_dumpall --clean --if-exists" | gzip``.
        Same mechanism, so there is one way this cluster is dumped and no
        password is ever embedded — postgres authenticates over the local socket
        as its own user.
        """
        host = node.ip_address
        ssh_user = node.ssh_user or "autobot"
        ssh_port = node.ssh_port or 22

        backup = await self._mark_backup_in_progress(db, backup_id)
        if not backup:
            return False, "Backup not found"

        remote_path = f"/tmp/slm-pg-{backup_id}.sql.gz"

        try:
            # Dump to a .partial first and rename, so an interrupted run never
            # leaves a half-written dump that the copy step could pick up —
            # same guarantee the scheduled script gives.
            logger.info("Starting pg_dumpall on %s", host)
            dump_cmd = self._build_ssh_command(
                host,
                ssh_user,
                ssh_port,
                f'sudo su - postgres -c "pg_dumpall --clean --if-exists" | gzip > {remote_path}.partial '
                f"&& mv {remote_path}.partial {remote_path}",
            )
            success, output = await self._run_command(dump_cmd, timeout=1800)
            if not success:
                return await self._fail_backup(db, backup, f"pg_dumpall failed: {output}")

            size_bytes, checksum = await self._get_remote_file_info(host, ssh_user, ssh_port, remote_path)
            if size_bytes == 0:
                return await self._fail_backup(db, backup, "pg_dumpall produced an empty dump")

            copy_success, backup_path, copy_error = await self._copy_backup_to_storage(
                host, ssh_user, ssh_port, remote_path, backup_id, suffix=".sql.gz"
            )

            return await self._complete_backup(
                db,
                backup,
                copy_success,
                backup_path,
                size_bytes,
                checksum,
                host,
                copy_error,
                remote_path=remote_path,
            )

        except asyncio.TimeoutError:
            return await self._fail_backup(db, backup, "Backup timed out")
        except Exception as e:
            logger.exception("Postgres backup error: %s", e)
            return await self._fail_backup(db, backup, "Backup operation failed")
        finally:
            # The staged dump is a full copy of the cluster sitting in /tmp on
            # the node. Leaving it there on every backup would fill the disk and
            # expose the data outside the backup store.
            await self._remove_remote_file(host, ssh_user, ssh_port, remote_path)

    async def _remove_remote_file(self, host: str, ssh_user: str, ssh_port: int, path: str) -> None:
        """Best-effort cleanup of a staged file on a node (#13307)."""
        try:
            cmd = self._build_ssh_command(host, ssh_user, ssh_port, f"rm -f {path} {path}.partial")
            await self._run_command(cmd, timeout=30)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not remove staged file %s on %s: %s", path, host, exc)

    async def _stop_redis_for_restore(self, host: str, ssh_user: str, ssh_port: int) -> None:
        """Stop Redis service on the target node.

        Helper for execute_restore (Issue #665).
        """
        logger.info("Stopping Redis on %s for restore", host)
        stop_cmd = self._build_ssh_command(host, ssh_user, ssh_port, "sudo systemctl stop redis-server")
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
            "StrictHostKeyChecking=accept-new",
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
            "sudo mv /tmp/restore.rdb /var/lib/redis/dump.rdb && " "sudo chown redis:redis /var/lib/redis/dump.rdb",
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
        verify_cmd = self._build_ssh_command(host, ssh_user, ssh_port, f"test -f {backup_path} && echo 'exists'")
        success, output = await self._run_command(verify_cmd, timeout=10)
        if not success or "exists" not in output:
            return False, "Backup file not found on target"

        return True, ""

    async def _start_and_verify_redis(self, host: str, ssh_user: str, ssh_port: int) -> Tuple[bool, str]:
        """Start Redis service and verify it's healthy.

        Helper for execute_restore (Issue #665).

        Returns (success, status_output).
        """
        # Start Redis
        logger.info("Starting Redis on %s after restore", host)
        start_cmd = self._build_ssh_command(host, ssh_user, ssh_port, "sudo systemctl start redis-server")
        success, output = await self._run_command(start_cmd, timeout=30)
        if not success:
            return False, f"Failed to start Redis: {output}"

        # Wait for Redis to be ready and verify data
        await asyncio.sleep(3)  # Give Redis time to load data

        verify_cmd = self._build_ssh_command(host, ssh_user, ssh_port, "redis-cli PING && redis-cli DBSIZE")
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
                success, error = await self._copy_local_backup_to_target(backup, host, ssh_user, ssh_port)
                if not success:
                    return False, error
            else:
                success, error = await self._verify_remote_backup_exists(backup_path, host, ssh_user, ssh_port)
                if not success:
                    return False, error

            # Step 3: Start Redis and verify
            success, verify_output = await self._start_and_verify_redis(host, ssh_user, ssh_port)
            if not success:
                return False, verify_output

            logger.info("Restore completed successfully to %s", host)
            return True, f"Restore completed. Redis status: {verify_output}"

        except Exception as e:
            logger.exception("Restore error: %s", e)
            return False, "Restore operation failed"

    async def verify_backup_integrity(
        self,
        backup_id: str,
    ) -> Dict:
        """Verify a backup's integrity by checking its checksum.

        Returns verification result with details.
        """
        from services.database import db_service

        async with db_service.session() as db:
            result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
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
        start_time = datetime.now(timezone.utc)
        initial_lastsave = None

        while (datetime.now(timezone.utc) - start_time).seconds < max_wait:
            cmd = self._build_ssh_command(host, ssh_user, ssh_port, f"{redis_auth_prefix} redis-cli LASTSAVE")
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

    async def _fail_backup(self, db: AsyncSession, backup: Backup, error: str) -> Tuple[bool, str]:
        """Mark backup as failed and return error."""
        backup.status = BackupStatus.FAILED.value
        backup.error = error[:500]
        backup.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.error("Backup %s failed: %s", backup.backup_id, error)
        return False, error

    def _build_ssh_command(self, host: str, user: str, port: int, command: str) -> list:
        """Build SSH command list."""
        return [
            "/usr/bin/ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
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
            logger.error("SSH command execution error: %s", e)
            return False, "Command execution failed"

    async def _calculate_checksum(self, path: Path) -> str | None:
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

    async def _discover_redis_config(self, host: str, ssh_user: str, ssh_port: int) -> Tuple[str, str]:
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
            redis_auth_prefix = "REDISCLI_AUTH=$(grep -E '^requirepass' /etc/redis/redis.conf " "| awk '{print $2}')"

        # Get Redis data directory and filename
        config_cmd = self._build_ssh_command(
            host,
            ssh_user,
            ssh_port,
            f"{redis_auth_prefix} redis-cli CONFIG GET dir && " f"{redis_auth_prefix} redis-cli CONFIG GET dbfilename",
        )
        success, config_output = await self._run_command(config_cmd, timeout=15)

        redis_dir = "/var/lib/redis"
        redis_dbfilename = "dump.rdb"
        if success:
            lines = [ln.strip() for ln in config_output.strip().split("\n") if ln.strip()]
            for i, line in enumerate(lines):
                if line == "dir" and i + 1 < len(lines):
                    redis_dir = lines[i + 1]
                elif line == "dbfilename" and i + 1 < len(lines):
                    redis_dbfilename = lines[i + 1]

        rdb_path = f"{redis_dir}/{redis_dbfilename}"
        logger.info("Redis RDB path discovered: %s", rdb_path)
        return redis_auth_prefix, rdb_path

    async def _get_remote_file_info(
        self, host: str, ssh_user: str, ssh_port: int, rdb_path: str
    ) -> Tuple[int, str | None]:
        """Get a remote file's size and checksum.

        Helper for execute_redis_backup (Issue #665); also used by the Postgres
        path (#13307), which is why it is no longer named for RDB files.

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
        suffix: str = ".rdb",
    ) -> Tuple[bool, Path, str]:
        """Copy a backup file from the remote host to local storage via SCP.

        Helper for execute_redis_backup (Issue #665). ``suffix`` exists because
        the Postgres path stores ``.sql.gz`` (#13307) — the extension used to be
        hardcoded to ``.rdb``, which would have labelled every Postgres dump as
        a Redis one.

        Returns (success, backup_path, error_output).
        """
        if not self._ensure_storage_dir():
            return (
                False,
                BACKUP_STORAGE_DIR / backup_id,
                f"Backup storage directory {BACKUP_STORAGE_DIR} is not writable",
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{backup_id}_{timestamp}{suffix}"
        backup_path = BACKUP_STORAGE_DIR / backup_filename

        scp_cmd = [
            "/usr/bin/scp",
            "-o",
            "StrictHostKeyChecking=accept-new",
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
        remote_checksum: str | None,
        host: str,
        copy_error: str = "",
        remote_path: str = "/var/lib/redis/dump.rdb",
    ) -> Tuple[bool, str]:
        """Update backup record with results and complete the backup.

        Helper for execute_redis_backup (Issue #665).

        Returns (success, message).
        """
        if not copy_success:
            # Backup exists on remote but copy failed - still record it
            backup.status = BackupStatus.COMPLETED.value
            # #13307: was hardcoded to the Redis data path, so a Postgres backup
            # whose copy failed would have pointed at Redis's live dump.rdb.
            backup.backup_path = remote_path
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
            backup.size_bytes = backup_path.stat().st_size if backup_path.exists() else size_bytes
            backup.checksum = local_checksum or remote_checksum
            backup.extra_data = {
                "location": "local",
                "remote_checksum": remote_checksum,
                "local_checksum": local_checksum,
            }

        backup.completed_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "Backup %s completed: %s bytes, checksum=%s",
            backup.backup_id,
            backup.size_bytes,
            backup.checksum,
        )
        return True, "Backup completed successfully"

    # ------------------------------------------------------------------
    # Deletion and retention (#13307)
    #
    # Before this there was no delete route at all — `@router.delete` count in
    # api/stateful.py was 0 — so nothing in the system could reclaim space, and
    # the destination was a home directory on the root filesystem. Retention was
    # not a missing convenience; it was unimplementable.
    # ------------------------------------------------------------------

    async def delete_backup(self, db: AsyncSession, backup_id: str) -> Tuple[bool, str]:
        """Delete a backup record and the file it points at.

        The record is removed even when the file is already gone: a row pointing
        at a missing file is exactly what a half-finished cleanup leaves behind,
        and refusing to delete it would make the state unrecoverable through the
        API — which is the situation #13307 is about.
        """
        result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
        backup = result.scalar_one_or_none()
        if not backup:
            return False, "Backup not found"

        if backup.status == BackupStatus.IN_PROGRESS.value:
            return False, "Backup is in progress"

        self._unlink_backup_file(backup)

        await db.delete(backup)
        await db.commit()
        logger.info("Backup %s deleted", backup_id)
        return True, "Backup deleted"

    def _unlink_backup_file(self, backup: Backup) -> None:
        """Remove a backup's local file, if it has one inside our storage dir.

        Scoped to BACKUP_STORAGE_DIR on purpose. `_complete_backup` records the
        REMOTE path when the copy to SLM storage failed — for Redis that is the
        live ``/var/lib/redis/dump.rdb`` on the target node, and deleting it
        would destroy the data the backup exists to protect.
        """
        path_str = backup.backup_path
        if not path_str:
            return

        path = Path(path_str)
        try:
            path.relative_to(BACKUP_STORAGE_DIR)
        except ValueError:
            logger.info(
                "Backup %s points outside %s (%s) — record removed, file left alone",
                backup.backup_id,
                BACKUP_STORAGE_DIR,
                path_str,
            )
            return

        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove backup file %s: %s", path, exc)

    async def apply_retention(
        self,
        db: AsyncSession,
        node_id: str,
        service_type: str,
        keep_count: int | None = None,
        max_age_days: int | None = None,
    ) -> list[str]:
        """Prune old backups for one (node, service_type), newest kept.

        Returns the backup_ids removed. Both dimensions are independent and
        either can be disabled with 0; a backup is pruned if *either* rule
        selects it.

        Only ``completed`` backups are counted toward ``keep_count``. Counting
        failed ones would let a run of failures evict the last good backup,
        which is the one moment it matters.
        """
        keep_count = settings.backup_retention_count if keep_count is None else keep_count
        max_age_days = settings.backup_retention_days if max_age_days is None else max_age_days

        result = await db.execute(
            select(Backup)
            .where(
                Backup.node_id == node_id,
                Backup.service_type == service_type,
                Backup.status == BackupStatus.COMPLETED.value,
            )
            .order_by(Backup.created_at.desc())
        )
        completed = list(result.scalars().all())

        doomed = {b.backup_id: b for b in completed[keep_count:]} if keep_count > 0 else {}

        if max_age_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            for backup in completed:
                created = backup.created_at
                if created is None:
                    continue
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if created < cutoff:
                    doomed[backup.backup_id] = backup

        for backup in doomed.values():
            self._unlink_backup_file(backup)
            await db.delete(backup)

        if doomed:
            await db.commit()
            logger.info(
                "Retention pruned %d backup(s) for node=%s service=%s (keep=%d, max_age_days=%d)",
                len(doomed),
                node_id,
                service_type,
                keep_count,
                max_age_days,
            )
        return sorted(doomed)


# Global service instance
backup_service = BackupService()
