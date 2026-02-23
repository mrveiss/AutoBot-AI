# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Replication Service

Orchestrates Redis replication with Ansible and provides data sync verification.
Issue #726 Phase 4: Redis replication orchestration
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from config import settings
from models.database import Node, Replication, ReplicationStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReplicationService:
    """Manages Redis replication with Ansible and sync verification."""

    def __init__(self):
        self.ansible_dir = Path(settings.ansible_dir)
        self._running_jobs: Dict[str, asyncio.Task] = {}

    async def _log_and_load_replication(
        self,
        db: AsyncSession,
        replication_id: str,
        source_node: Node,
        target_node: Node,
    ) -> Optional["Replication"]:
        """Log the replication attempt and load the DB record.

        Helper for setup_replication. Ref: #1088.
        """
        logger.info(
            "Setting up replication %s: %s -> %s",
            replication_id,
            source_node.ip_address,
            target_node.ip_address,
        )
        return await self._get_replication_record(db, replication_id)

    async def setup_replication(
        self,
        db: AsyncSession,
        replication_id: str,
        source_node: Node,
        target_node: Node,
        service_type: str = "redis",
    ) -> Tuple[bool, str]:
        """Set up replication from source to target using Ansible.

        Args:
            db: Database session
            replication_id: Replication ID to track
            source_node: Primary/master node
            target_node: Replica node
            service_type: Service type (currently only 'redis' supported)

        Returns:
            Tuple of (success, message)
        """
        if service_type != "redis":
            return False, f"Unsupported service type: {service_type}"

        replication = await self._log_and_load_replication(
            db, replication_id, source_node, target_node
        )
        if not replication:
            return False, "Replication record not found"

        try:
            redis_password = await self._get_redis_password(
                source_node.ip_address,
                source_node.ssh_user or "autobot",
                source_node.ssh_port or 22,
            )

            # Configure and verify replication
            result = await self._configure_and_verify_replication(
                db, replication, source_node, target_node, redis_password
            )
            if result is not None:
                return result

            # Finalize successful replication
            sync_info = await self._get_replication_info(
                target_node.ip_address,
                target_node.ssh_user or "autobot",
                target_node.ssh_port or 22,
                redis_password,
            )

            await self._finalize_replication_success(
                db, replication, replication_id, sync_info
            )

            return True, "Replication established successfully"

        except Exception as e:
            logger.error("Replication setup failed: %s", e)
            await self._mark_replication_failed(db, replication, str(e)[:500])
            return False, f"Replication setup error: {e}"

    async def _get_replication_record(
        self, db: AsyncSession, replication_id: str
    ) -> Optional[Replication]:
        """Fetch replication record and update to syncing status.

        Helper for setup_replication (Issue #665).

        Args:
            db: Database session
            replication_id: Replication ID to fetch

        Returns:
            Replication object or None if not found
        """
        result = await db.execute(
            select(Replication).where(Replication.replication_id == replication_id)
        )
        replication = result.scalar_one_or_none()
        if not replication:
            return None

        replication.status = ReplicationStatus.SYNCING.value
        replication.started_at = datetime.utcnow()
        await db.commit()
        return replication

    async def _mark_replication_failed(
        self, db: AsyncSession, replication: Replication, error_message: str
    ) -> None:
        """Set replication to failed status with error message.

        Helper for setup_replication (Issue #665).

        Args:
            db: Database session
            replication: Replication object to update
            error_message: Error message to store
        """
        replication.status = ReplicationStatus.FAILED.value
        replication.error = error_message
        await db.commit()

    async def _configure_and_verify_replication(
        self,
        db: AsyncSession,
        replication: Replication,
        source_node: Node,
        target_node: Node,
        redis_password: str,
    ) -> Optional[Tuple[bool, str]]:
        """Configure Ansible replication and verify sync.

        Helper for setup_replication (Issue #665).

        Args:
            db: Database session
            replication: Replication object
            source_node: Source node configuration
            target_node: Target node configuration
            redis_password: Redis password for authentication

        Returns:
            Error tuple if failed, None if successful (continue with finalization)
        """
        # Run Ansible playbook to configure replica
        success = await self._run_ansible_replication(
            target_node.ip_address,
            target_node.ssh_user or "autobot",
            target_node.ssh_port or 22,
            source_node.ip_address,
            redis_password,
        )

        if not success:
            await self._mark_replication_failed(
                db, replication, "Ansible playbook failed"
            )
            return False, "Failed to configure replication via Ansible"

        # Wait for replication to sync
        sync_success = await self._wait_for_sync(
            target_node.ip_address,
            target_node.ssh_user or "autobot",
            target_node.ssh_port or 22,
            redis_password,
        )

        if not sync_success:
            await self._mark_replication_failed(
                db, replication, "Replication sync failed or timed out"
            )
            return False, "Replication sync failed"

        return None

    async def _finalize_replication_success(
        self,
        db: AsyncSession,
        replication: Replication,
        replication_id: str,
        sync_info: Dict,
    ) -> None:
        """Update replication to active status and start monitoring.

        Helper for setup_replication (Issue #665).

        Args:
            db: Database session
            replication: Replication object to update
            replication_id: Replication ID for monitoring
            sync_info: Sync info dict from Redis
        """
        replication.status = ReplicationStatus.ACTIVE.value
        replication.sync_position = sync_info.get("master_repl_offset", "")
        replication.lag_bytes = sync_info.get("lag_bytes", 0)
        await db.commit()

        self._start_lag_monitor(replication_id)
        logger.info("Replication %s is now active", replication_id)

    async def verify_sync(
        self,
        source_ip: str,
        target_ip: str,
        ssh_user: str = "autobot",
        ssh_port: int = 22,
        redis_password: str = "",
    ) -> Dict:
        """Verify data sync between source and target using keyspace analysis.

        Returns detailed comparison of keys, memory, and replication lag.
        """
        logger.info("Verifying sync between %s and %s", source_ip, target_ip)

        result = {
            "synced": False,
            "source": {},
            "target": {},
            "comparison": {},
            "lag": {},
            "checks": [],
        }

        try:
            # Get keyspace info from both nodes
            source_keyspace = await self._get_keyspace_info(
                source_ip, ssh_user, ssh_port, redis_password
            )
            target_keyspace = await self._get_keyspace_info(
                target_ip, ssh_user, ssh_port, redis_password
            )

            result["source"] = source_keyspace
            result["target"] = target_keyspace

            # Compare key counts
            source_keys = source_keyspace.get("total_keys", 0)
            target_keys = target_keyspace.get("total_keys", 0)
            key_diff = abs(source_keys - target_keys)

            result["comparison"]["source_keys"] = source_keys
            result["comparison"]["target_keys"] = target_keys
            result["comparison"]["key_difference"] = key_diff
            result["comparison"]["keys_match"] = key_diff == 0

            # Add key count check using helper
            self._add_key_count_check(result["checks"], source_keys, target_keys)

            # Get replication lag info and add replication checks
            repl_info = await self._get_replication_info(
                target_ip, ssh_user, ssh_port, redis_password
            )
            self._add_replication_checks(result["checks"], result["lag"], repl_info)

            # Determine overall sync status
            failed_checks = [c for c in result["checks"] if c["status"] == "failed"]
            result["synced"] = len(failed_checks) == 0

        except Exception as e:
            logger.error("Sync verification failed: %s", e)
            result["checks"].append(
                self._build_check("verification", "failed", str(e)[:200])
            )

        return result

    async def promote_replica(
        self,
        db: AsyncSession,
        replication_id: str,
    ) -> Tuple[bool, str]:
        """Promote a replica to primary (break replication)."""
        result = await db.execute(
            select(Replication).where(Replication.replication_id == replication_id)
        )
        replication = result.scalar_one_or_none()
        if not replication:
            return False, "Replication not found"

        if replication.status != ReplicationStatus.ACTIVE.value:
            return False, f"Cannot promote replication in status: {replication.status}"

        # Get target node
        node_result = await db.execute(
            select(Node).where(Node.node_id == replication.target_node_id)
        )
        target_node = node_result.scalar_one_or_none()
        if not target_node:
            return False, "Target node not found"

        try:
            # Run Ansible to promote replica to primary
            success = await self._run_ansible_promotion(
                target_node.ip_address,
                target_node.ssh_user or "autobot",
                target_node.ssh_port or 22,
            )

            if not success:
                return False, "Failed to promote replica via Ansible"

            # Stop lag monitor
            self._stop_lag_monitor(replication_id)

            # Update replication status
            replication.status = ReplicationStatus.STOPPED.value
            replication.completed_at = datetime.utcnow()
            await db.commit()

            logger.info("Replica promoted: %s", replication_id)
            return True, "Replica promoted to primary successfully"

        except Exception as e:
            logger.error("Promotion failed: %s", e)
            return False, f"Promotion error: {e}"

    async def stop_replication(
        self,
        db: AsyncSession,
        replication_id: str,
    ) -> Tuple[bool, str]:
        """Stop replication without promotion (just break the link)."""
        result = await db.execute(
            select(Replication).where(Replication.replication_id == replication_id)
        )
        replication = result.scalar_one_or_none()
        if not replication:
            return False, "Replication not found"

        # Stop lag monitor
        self._stop_lag_monitor(replication_id)

        # Update status
        replication.status = ReplicationStatus.STOPPED.value
        replication.completed_at = datetime.utcnow()
        await db.commit()

        logger.info("Replication stopped: %s", replication_id)
        return True, "Replication stopped"

    async def update_lag_info(
        self,
        db: AsyncSession,
        replication_id: str,
    ) -> Optional[Dict]:
        """Update lag info for a replication."""
        result = await db.execute(
            select(Replication).where(Replication.replication_id == replication_id)
        )
        replication = result.scalar_one_or_none()
        if not replication:
            return None

        # Get target node
        node_result = await db.execute(
            select(Node).where(Node.node_id == replication.target_node_id)
        )
        target_node = node_result.scalar_one_or_none()
        if not target_node:
            return None

        # Get Redis password
        source_result = await db.execute(
            select(Node).where(Node.node_id == replication.source_node_id)
        )
        source_node = source_result.scalar_one_or_none()

        redis_password = ""
        if source_node:
            redis_password = await self._get_redis_password(
                source_node.ip_address,
                source_node.ssh_user or "autobot",
                source_node.ssh_port or 22,
            )

        try:
            repl_info = await self._get_replication_info(
                target_node.ip_address,
                target_node.ssh_user or "autobot",
                target_node.ssh_port or 22,
                redis_password,
            )

            replication.lag_bytes = repl_info.get("lag_bytes", 0)
            replication.sync_position = str(repl_info.get("master_repl_offset", ""))

            # Check if replication is still active
            if repl_info.get("master_link_status") != "up":
                replication.status = ReplicationStatus.FAILED.value
                replication.error = (
                    f"Master link down: {repl_info.get('master_link_status')}"
                )

            await db.commit()
            return repl_info

        except Exception as e:
            logger.error("Failed to update lag info: %s", e)
            return None

    # =========================================================================
    # Helper Methods for verify_sync
    # =========================================================================

    def _build_check(self, name: str, status: str, message: str) -> Dict:
        """Build a standardized check result dict.

        Helper for verify_sync (Issue #665).

        Args:
            name: Check name identifier
            status: Check status ('passed', 'warning', 'failed')
            message: Human-readable message

        Returns:
            Dict with name, status, and message keys
        """
        return {"name": name, "status": status, "message": message}

    def _add_key_count_check(
        self, checks: list, source_keys: int, target_keys: int
    ) -> None:
        """Add key count comparison check to checks list.

        Helper for verify_sync (Issue #665).

        Args:
            checks: List to append check result to
            source_keys: Number of keys on source
            target_keys: Number of keys on target
        """
        key_diff = abs(source_keys - target_keys)

        if key_diff == 0:
            checks.append(
                self._build_check(
                    "key_count", "passed", f"Key counts match: {source_keys}"
                )
            )
        elif key_diff <= 10:
            checks.append(
                self._build_check(
                    "key_count", "warning", f"Minor key difference: {key_diff} keys"
                )
            )
        else:
            checks.append(
                self._build_check(
                    "key_count",
                    "failed",
                    f"Significant key difference: {key_diff} keys",
                )
            )

    def _add_replication_checks(
        self, checks: list, result_lag: Dict, repl_info: Dict
    ) -> None:
        """Add replication link and lag checks to checks list.

        Helper for verify_sync (Issue #665).

        Args:
            checks: List to append check results to
            result_lag: Dict to populate with lag info
            repl_info: Replication info from Redis
        """
        if repl_info.get("role") != "slave":
            role = repl_info.get("role", "unknown")
            checks.append(
                self._build_check(
                    "role_check", "warning", f"Target role is '{role}', not 'slave'"
                )
            )
            return

        lag_bytes = repl_info.get("lag_bytes", 0)
        link_status = repl_info.get("master_link_status", "unknown")

        result_lag["bytes"] = lag_bytes
        result_lag["link_status"] = link_status

        # Check replication link status
        if link_status == "up":
            checks.append(
                self._build_check(
                    "replication_link", "passed", "Replication link is up"
                )
            )
        else:
            checks.append(
                self._build_check(
                    "replication_link",
                    "failed",
                    f"Replication link status: {link_status}",
                )
            )

        # Check replication lag
        if lag_bytes == 0:
            checks.append(
                self._build_check("replication_lag", "passed", "No replication lag")
            )
        elif lag_bytes < 1024:
            checks.append(
                self._build_check(
                    "replication_lag", "warning", f"Minor lag: {lag_bytes} bytes"
                )
            )
        else:
            checks.append(
                self._build_check(
                    "replication_lag", "failed", f"Significant lag: {lag_bytes} bytes"
                )
            )

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _get_redis_password(self, host: str, ssh_user: str, ssh_port: int) -> str:
        """Get Redis password from config file."""
        cmd = [
            "/usr/bin/ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "-p",
            str(ssh_port),
            f"{ssh_user}@{host}",
            "grep -E '^requirepass' /etc/redis/redis.conf 2>/dev/null | awk '{print $2}'",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15)
            if process.returncode == 0:
                return stdout.decode().strip()
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)
        return ""

    async def _run_ansible_replication(
        self,
        target_ip: str,
        ssh_user: str,
        ssh_port: int,
        master_ip: str,
        redis_password: str,
    ) -> bool:
        """Run Ansible playbook to configure Redis replication."""
        # Create ad-hoc playbook for replication
        playbook_content = f"""---
- name: Configure Redis Replication
  hosts: all
  become: true
  gather_facts: false
  roles:
    - role: redis-replication
      vars:
        redis_replication_mode: replica
        redis_master_host: "{master_ip}"
        redis_master_port: 6379
        redis_master_auth: "{redis_password}"
        redis_password: "{redis_password}"
"""

        # Write temporary playbook
        playbook_path = self.ansible_dir / "temp_replication.yml"
        playbook_path.write_text(playbook_content, encoding="utf-8")

        try:
            cmd = [
                "ansible-playbook",
                str(playbook_path),
                "-i",
                f"{target_ip},",
                "-e",
                f"ansible_user={ssh_user}",
                "-e",
                f"ansible_port={ssh_port}",
                "-e",
                "ansible_ssh_common_args='-o StrictHostKeyChecking=no'",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0:
                logger.error(
                    "Ansible replication failed: %s",
                    stdout.decode("utf-8", errors="replace"),
                )
                return False

            return True

        finally:
            # Clean up temp playbook
            if playbook_path.exists():
                playbook_path.unlink()

    async def _run_ansible_promotion(
        self,
        target_ip: str,
        ssh_user: str,
        ssh_port: int,
    ) -> bool:
        """Run Ansible to promote replica to primary."""
        playbook_content = """---
- name: Promote Redis Replica to Primary
  hosts: all
  become: true
  gather_facts: false
  roles:
    - role: redis-replication
      vars:
        redis_replication_mode: primary
"""

        playbook_path = self.ansible_dir / "temp_promotion.yml"
        playbook_path.write_text(playbook_content, encoding="utf-8")

        try:
            cmd = [
                "ansible-playbook",
                str(playbook_path),
                "-i",
                f"{target_ip},",
                "-e",
                f"ansible_user={ssh_user}",
                "-e",
                f"ansible_port={ssh_port}",
                "-e",
                "ansible_ssh_common_args='-o StrictHostKeyChecking=no'",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode != 0:
                logger.error(
                    "Ansible promotion failed: %s",
                    stdout.decode("utf-8", errors="replace"),
                )
                return False

            return True

        finally:
            if playbook_path.exists():
                playbook_path.unlink()

    async def _wait_for_sync(
        self,
        target_ip: str,
        ssh_user: str,
        ssh_port: int,
        redis_password: str,
        timeout: int = 60,
    ) -> bool:
        """Wait for replica to sync with master."""
        start_time = datetime.utcnow()

        while (datetime.utcnow() - start_time).seconds < timeout:
            repl_info = await self._get_replication_info(
                target_ip, ssh_user, ssh_port, redis_password
            )

            if repl_info.get("master_link_status") == "up":
                # Check if sync is in progress
                sync_in_progress = repl_info.get("master_sync_in_progress", "0")
                if sync_in_progress == "0":
                    return True

            await asyncio.sleep(2)

        return False

    async def _get_replication_info(
        self,
        host: str,
        ssh_user: str,
        ssh_port: int,
        redis_password: str,
    ) -> Dict:
        """Get replication info from Redis."""
        auth_prefix = ""
        if redis_password:
            auth_prefix = f"REDISCLI_AUTH='{redis_password}'"

        cmd = [
            "/usr/bin/ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-p",
            str(ssh_port),
            f"{ssh_user}@{host}",
            f"{auth_prefix} redis-cli INFO replication",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15)

            if process.returncode != 0:
                return {}

            output = stdout.decode()
            info = {}

            for line in output.split("\n"):
                if ":" in line:
                    key, value = line.strip().split(":", 1)
                    info[key] = value

            # Calculate lag if possible
            if "master_repl_offset" in info and "slave_repl_offset" in info:
                try:
                    master_offset = int(info["master_repl_offset"])
                    slave_offset = int(info.get("slave_repl_offset", master_offset))
                    info["lag_bytes"] = master_offset - slave_offset
                except ValueError:
                    info["lag_bytes"] = 0

            return info

        except Exception as e:
            logger.error("Failed to get replication info: %s", e)
            return {}

    def _build_keyspace_ssh_cmd(
        self,
        host: str,
        ssh_user: str,
        ssh_port: int,
        auth_prefix: str,
    ) -> list:
        """Build SSH command list for keyspace/dbsize/memory queries.

        Helper for _get_keyspace_info. Ref: #1088.

        Args:
            host: Redis host IP
            ssh_user: SSH username
            ssh_port: SSH port number
            auth_prefix: REDISCLI_AUTH env var prefix (may be empty)

        Returns:
            List of command arguments for asyncio.create_subprocess_exec
        """
        return [
            "/usr/bin/ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-p",
            str(ssh_port),
            f"{ssh_user}@{host}",
            (
                f"{auth_prefix} redis-cli INFO keyspace && "
                f"{auth_prefix} redis-cli DBSIZE && "
                f"{auth_prefix} redis-cli INFO memory"
            ),
        ]

    def _parse_keyspace_output(self, output: str) -> Dict:
        """Parse combined keyspace/dbsize/memory output into an info dict.

        Helper for _get_keyspace_info. Ref: #1088.

        Args:
            output: Raw decoded stdout from the SSH command

        Returns:
            Dict with 'databases', 'total_keys', and optional memory keys
        """
        info: Dict = {"databases": {}, "total_keys": 0}

        for line in output.split("\n"):
            line = line.strip()
            # Parse db info (e.g., db0:keys=123,expires=10,avg_ttl=1000)
            if line.startswith("db") and ":" in line:
                db_name, db_info = line.split(":", 1)
                db_stats = {}
                for part in db_info.split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        db_stats[k] = int(v) if v.isdigit() else v
                info["databases"][db_name] = db_stats
                info["total_keys"] += db_stats.get("keys", 0)

            # Parse DBSIZE output
            if "keys" in line.lower() and line and line[0].isdigit():
                try:
                    info["total_keys"] = int(line.split()[0])
                except (ValueError, IndexError):
                    pass

            # Parse memory info
            if ":" in line:
                key, value = line.split(":", 1)
                if key == "used_memory":
                    info["used_memory"] = value
                elif key == "used_memory_human":
                    info["used_memory_human"] = value

        return info

    async def _get_keyspace_info(
        self,
        host: str,
        ssh_user: str,
        ssh_port: int,
        redis_password: str,
    ) -> Dict:
        """Get keyspace info from Redis."""
        auth_prefix = ""
        if redis_password:
            auth_prefix = f"REDISCLI_AUTH='{redis_password}'"

        cmd = self._build_keyspace_ssh_cmd(host, ssh_user, ssh_port, auth_prefix)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15)

            if process.returncode != 0:
                return {}

            return self._parse_keyspace_output(stdout.decode())

        except Exception as e:
            logger.error("Failed to get keyspace info: %s", e)
            return {}

    def _start_lag_monitor(self, replication_id: str) -> None:
        """Start background lag monitoring task."""
        if replication_id in self._running_jobs:
            return

        task = asyncio.create_task(self._lag_monitor_loop(replication_id))
        self._running_jobs[replication_id] = task

    def _stop_lag_monitor(self, replication_id: str) -> None:
        """Stop lag monitoring task."""
        if replication_id in self._running_jobs:
            self._running_jobs[replication_id].cancel()
            del self._running_jobs[replication_id]

    async def _lag_monitor_loop(self, replication_id: str) -> None:
        """Background loop to monitor replication lag."""
        from services.database import db_service

        logger.info("Starting lag monitor for %s", replication_id)

        try:
            while True:
                await asyncio.sleep(30)  # Check every 30 seconds

                async with db_service.session() as db:
                    result = await db.execute(
                        select(Replication).where(
                            Replication.replication_id == replication_id
                        )
                    )
                    replication = result.scalar_one_or_none()

                    if (
                        not replication
                        or replication.status != ReplicationStatus.ACTIVE.value
                    ):
                        logger.info("Lag monitor stopping for %s", replication_id)
                        break

                    await self.update_lag_info(db, replication_id)

        except asyncio.CancelledError:
            logger.info("Lag monitor cancelled for %s", replication_id)
        except Exception as e:
            logger.error("Lag monitor error for %s: %s", replication_id, e)
        finally:
            if replication_id in self._running_jobs:
                del self._running_jobs[replication_id]


# Singleton instance
replication_service = ReplicationService()
