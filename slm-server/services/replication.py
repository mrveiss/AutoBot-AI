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
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Node, Replication, ReplicationStatus

logger = logging.getLogger(__name__)


class ReplicationService:
    """Manages Redis replication with Ansible and sync verification."""

    def __init__(self):
        self.ansible_dir = Path(settings.ansible_dir)
        self._running_jobs: Dict[str, asyncio.Task] = {}

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

        logger.info(
            "Setting up replication %s: %s -> %s",
            replication_id,
            source_node.ip_address,
            target_node.ip_address,
        )

        # Get replication record
        result = await db.execute(
            select(Replication).where(Replication.replication_id == replication_id)
        )
        replication = result.scalar_one_or_none()
        if not replication:
            return False, "Replication record not found"

        # Update status to syncing
        replication.status = ReplicationStatus.SYNCING.value
        replication.started_at = datetime.utcnow()
        await db.commit()

        try:
            # Get Redis password from source (if configured)
            redis_password = await self._get_redis_password(
                source_node.ip_address,
                source_node.ssh_user or "autobot",
                source_node.ssh_port or 22,
            )

            # Run Ansible playbook to configure replica
            success = await self._run_ansible_replication(
                target_node.ip_address,
                target_node.ssh_user or "autobot",
                target_node.ssh_port or 22,
                source_node.ip_address,
                redis_password,
            )

            if not success:
                replication.status = ReplicationStatus.FAILED.value
                replication.error = "Ansible playbook failed"
                await db.commit()
                return False, "Failed to configure replication via Ansible"

            # Wait for replication to sync
            sync_success = await self._wait_for_sync(
                target_node.ip_address,
                target_node.ssh_user or "autobot",
                target_node.ssh_port or 22,
                redis_password,
            )

            if not sync_success:
                replication.status = ReplicationStatus.FAILED.value
                replication.error = "Replication sync failed or timed out"
                await db.commit()
                return False, "Replication sync failed"

            # Get initial sync info
            sync_info = await self._get_replication_info(
                target_node.ip_address,
                target_node.ssh_user or "autobot",
                target_node.ssh_port or 22,
                redis_password,
            )

            replication.status = ReplicationStatus.ACTIVE.value
            replication.sync_position = sync_info.get("master_repl_offset", "")
            replication.lag_bytes = sync_info.get("lag_bytes", 0)
            await db.commit()

            # Start background monitoring
            self._start_lag_monitor(replication_id)

            logger.info("Replication %s is now active", replication_id)
            return True, "Replication established successfully"

        except Exception as e:
            logger.error("Replication setup failed: %s", e)
            replication.status = ReplicationStatus.FAILED.value
            replication.error = str(e)[:500]
            await db.commit()
            return False, f"Replication setup error: {e}"

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

            # Check key difference
            if key_diff == 0:
                result["checks"].append({
                    "name": "key_count",
                    "status": "passed",
                    "message": f"Key counts match: {source_keys}",
                })
            elif key_diff <= 10:
                result["checks"].append({
                    "name": "key_count",
                    "status": "warning",
                    "message": f"Minor key difference: {key_diff} keys",
                })
            else:
                result["checks"].append({
                    "name": "key_count",
                    "status": "failed",
                    "message": f"Significant key difference: {key_diff} keys",
                })

            # Get replication lag info
            repl_info = await self._get_replication_info(
                target_ip, ssh_user, ssh_port, redis_password
            )

            if repl_info.get("role") == "slave":
                lag_bytes = repl_info.get("lag_bytes", 0)
                link_status = repl_info.get("master_link_status", "unknown")

                result["lag"]["bytes"] = lag_bytes
                result["lag"]["link_status"] = link_status

                if link_status == "up":
                    result["checks"].append({
                        "name": "replication_link",
                        "status": "passed",
                        "message": "Replication link is up",
                    })
                else:
                    result["checks"].append({
                        "name": "replication_link",
                        "status": "failed",
                        "message": f"Replication link status: {link_status}",
                    })

                if lag_bytes == 0:
                    result["checks"].append({
                        "name": "replication_lag",
                        "status": "passed",
                        "message": "No replication lag",
                    })
                elif lag_bytes < 1024:
                    result["checks"].append({
                        "name": "replication_lag",
                        "status": "warning",
                        "message": f"Minor lag: {lag_bytes} bytes",
                    })
                else:
                    result["checks"].append({
                        "name": "replication_lag",
                        "status": "failed",
                        "message": f"Significant lag: {lag_bytes} bytes",
                    })
            else:
                result["checks"].append({
                    "name": "role_check",
                    "status": "warning",
                    "message": f"Target role is '{repl_info.get('role', 'unknown')}', not 'slave'",
                })

            # Determine overall sync status
            failed_checks = [c for c in result["checks"] if c["status"] == "failed"]
            result["synced"] = len(failed_checks) == 0

        except Exception as e:
            logger.error("Sync verification failed: %s", e)
            result["checks"].append({
                "name": "verification",
                "status": "failed",
                "message": str(e)[:200],
            })

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
                replication.error = f"Master link down: {repl_info.get('master_link_status')}"

            await db.commit()
            return repl_info

        except Exception as e:
            logger.error("Failed to update lag info: %s", e)
            return None

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _get_redis_password(
        self, host: str, ssh_user: str, ssh_port: int
    ) -> str:
        """Get Redis password from config file."""
        cmd = [
            "/usr/bin/ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            "-p", str(ssh_port),
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
            pass
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
                "-i", f"{target_ip},",
                "-e", f"ansible_user={ssh_user}",
                "-e", f"ansible_port={ssh_port}",
                "-e", "ansible_ssh_common_args='-o StrictHostKeyChecking=no'",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0:
                logger.error("Ansible replication failed: %s", stdout.decode("utf-8", errors="replace"))
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
                "-i", f"{target_ip},",
                "-e", f"ansible_user={ssh_user}",
                "-e", f"ansible_port={ssh_port}",
                "-e", "ansible_ssh_common_args='-o StrictHostKeyChecking=no'",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode != 0:
                logger.error("Ansible promotion failed: %s", stdout.decode("utf-8", errors="replace"))
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
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-p", str(ssh_port),
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
    f"{auth_prefix} redis-cli INFO keyspace && {auth_prefix} redis-cli DBSIZE && {auth_prefix} redis-cli INFO memory",
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
            info = {"databases": {}, "total_keys": 0}

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
                if "keys" in line.lower() and line[0].isdigit():
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

                    if not replication or replication.status != ReplicationStatus.ACTIVE.value:
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
