# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Sync Orchestrator Service (Issue #779).

Orchestrates code distribution from code-source through SLM to fleet nodes.
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import select

from models.database import CodeSource, Node, NodeRole, Role, RoleStatus
from services.database import db_service

logger = logging.getLogger(__name__)

# Code cache directory
CODE_CACHE_DIR = Path(os.environ.get("SLM_CODE_CACHE", "/var/lib/slm/code-cache"))
SSH_KEY_PATH = os.environ.get("SLM_SSH_KEY", "/home/autobot/.ssh/autobot_key")


class SyncOrchestrator:
    """Orchestrates role-based code distribution."""

    def __init__(self):
        self.cache_dir = CODE_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def pull_from_source(self) -> Tuple[bool, str, Optional[str]]:
        """
        Pull code from code-source node to SLM cache.

        Returns:
            Tuple of (success, message, commit_hash)
        """
        async with db_service.session() as db:
            # Get active code source
            result = await db.execute(
                select(CodeSource).where(CodeSource.is_active == True)  # noqa: E712
            )
            source = result.scalar_one_or_none()

            if not source:
                return False, "No active code-source configured", None

            # Get source node info
            node_result = await db.execute(
                select(Node).where(Node.node_id == source.node_id)
            )
            node = node_result.scalar_one_or_none()

            if not node:
                return False, f"Code-source node not found: {source.node_id}", None

            # Store for use outside context
            node_ip = node.ip_address
            node_user = node.ssh_user or "autobot"
            repo_path = source.repo_path
            commit = source.last_known_commit or "latest"

        # Pull using rsync
        cache_path = self.cache_dir / commit

        ssh_opts = (
            "ssh -o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            "-o ConnectTimeout=30"
        )
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"

        rsync_cmd = [
            "rsync",
            "-avz",
            "--delete",
            "--exclude",
            ".git",
            "--exclude",
            "__pycache__",
            "--exclude",
            "*.pyc",
            "--exclude",
            "node_modules",
            "--exclude",
            "venv",
            "--exclude",
            ".venv",
            "-e",
            ssh_opts,
            f"{node_user}@{node_ip}:{repo_path}/",
            f"{cache_path}/",
        ]

        try:
            logger.info("Pulling code from %s to cache", node_ip)
            proc = await asyncio.create_subprocess_exec(
                *rsync_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode != 0:
                output = stdout.decode("utf-8", errors="replace")
                logger.error("Pull failed: %s", output[:500])
                return False, f"Pull failed: {output[:200]}", None

            logger.info("Code pulled to cache: %s", cache_path)
            return True, f"Code cached at {commit}", commit

        except asyncio.TimeoutError:
            return False, "Pull timed out", None
        except Exception as e:
            logger.error("Pull error: %s", e)
            return False, str(e), None

    async def sync_node_role(
        self,
        node_id: str,
        role_name: str,
        commit: str,
        restart: bool = True,
    ) -> Tuple[bool, str]:
        """
        Sync a specific role to a node.

        Args:
            node_id: Target node ID
            role_name: Role to sync
            commit: Commit hash to sync
            restart: Whether to restart service after sync

        Returns:
            Tuple of (success, message)
        """
        async with db_service.session() as db:
            # Get node
            node_result = await db.execute(select(Node).where(Node.node_id == node_id))
            node = node_result.scalar_one_or_none()

            if not node:
                return False, f"Node not found: {node_id}"

            # Get role
            role_result = await db.execute(select(Role).where(Role.name == role_name))
            role = role_result.scalar_one_or_none()

            if not role:
                return False, f"Role not found: {role_name}"

            if not role.source_paths:
                return False, f"Role has no source paths: {role_name}"

            # Store values for use outside context
            node_ip = node.ip_address
            node_user = node.ssh_user or "autobot"
            node_port = node.ssh_port or 22
            source_paths = role.source_paths
            target_path = role.target_path
            post_sync_cmd = role.post_sync_cmd
            auto_restart = role.auto_restart
            systemd_service = role.systemd_service

        # Check cache exists
        cache_path = self.cache_dir / commit
        if not cache_path.exists():
            return False, f"Commit not cached: {commit}"

        # Sync each source path
        ssh_opts = (
            "ssh -o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=30 "
            f"-p {node_port}"
        )
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"

        for source_path in source_paths:
            src = cache_path / source_path.rstrip("/")
            if not src.exists():
                logger.warning("Source path not found in cache: %s", src)
                continue

            # Determine target
            if source_path.endswith("/"):
                # Sync contents of directory
                rsync_src = f"{src}/"
            else:
                rsync_src = str(src)

            rsync_cmd = [
                "rsync",
                "-avz",
                "--delete",
                "--exclude",
                "__pycache__",
                "--exclude",
                "*.pyc",
                "-e",
                ssh_opts,
                rsync_src,
                f"{node_user}@{node_ip}:{target_path}/",
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *rsync_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)

                if proc.returncode != 0:
                    output = stdout.decode("utf-8", errors="replace")
                    return False, f"Sync failed for {source_path}: {output[:200]}"

            except asyncio.TimeoutError:
                return False, f"Sync timed out for {source_path}"
            except Exception as e:
                return False, f"Sync error: {e}"

        # Run post-sync command if defined
        if post_sync_cmd:
            try:
                ssh_cmd = [
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-p",
                    str(node_port),
                ]
                if Path(SSH_KEY_PATH).exists():
                    ssh_cmd.extend(["-i", SSH_KEY_PATH])
                ssh_cmd.extend([f"{node_user}@{node_ip}", post_sync_cmd])

                proc = await asyncio.create_subprocess_exec(
                    *ssh_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                await asyncio.wait_for(proc.communicate(), timeout=300)

            except Exception as e:
                logger.warning("Post-sync command failed: %s", e)

        # Restart service if requested
        if restart and auto_restart and systemd_service:
            try:
                ssh_cmd = [
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-p",
                    str(node_port),
                ]
                if Path(SSH_KEY_PATH).exists():
                    ssh_cmd.extend(["-i", SSH_KEY_PATH])
                ssh_cmd.extend(
                    [
                        f"{node_user}@{node_ip}",
                        f"sudo systemctl restart {systemd_service}",
                    ]
                )

                proc = await asyncio.create_subprocess_exec(
                    *ssh_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                await asyncio.wait_for(proc.communicate(), timeout=60)
                logger.info("Restarted %s on %s", systemd_service, node_id)

            except Exception as e:
                logger.warning("Service restart failed: %s", e)

        # Update node role record
        async with db_service.session() as db:
            role_result = await db.execute(
                select(NodeRole).where(
                    NodeRole.node_id == node_id,
                    NodeRole.role_name == role_name,
                )
            )
            node_role = role_result.scalar_one_or_none()

            if node_role:
                node_role.current_version = commit
                node_role.last_synced_at = datetime.utcnow()
                node_role.status = RoleStatus.ACTIVE.value
            else:
                node_role = NodeRole(
                    node_id=node_id,
                    role_name=role_name,
                    assignment_type="auto",
                    status=RoleStatus.ACTIVE.value,
                    current_version=commit,
                    last_synced_at=datetime.utcnow(),
                )
                db.add(node_role)

            await db.commit()

        logger.info("Synced %s to %s (commit: %s)", role_name, node_id, commit[:12])
        return True, f"Synced {role_name} to {node_id}"


# Singleton
_orchestrator: Optional[SyncOrchestrator] = None


def get_sync_orchestrator() -> SyncOrchestrator:
    """Get or create sync orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SyncOrchestrator()
    return _orchestrator
