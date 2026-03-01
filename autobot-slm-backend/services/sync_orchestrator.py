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

from models.database import CodeSource, Node, NodeRole, Role, RoleStatus
from services.database import db_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SyncNodeContext:
    """Context object for sync_node_role operation.

    Helper for sync_node_role (Issue #665).
    """

    def __init__(self):
        self.node_ip: str = ""
        self.node_user: str = "autobot"
        self.node_port: int = 22
        self.source_paths: list = []
        self.target_path: str = ""
        self.post_sync_cmd: Optional[str] = None
        self.auto_restart: bool = False
        self.systemd_service: Optional[str] = None


# Code cache directory
CODE_CACHE_DIR = Path(os.environ.get("SLM_CODE_CACHE", "/var/lib/slm/code-cache"))
SSH_KEY_PATH = os.environ.get("SLM_SSH_KEY", "/home/autobot/.ssh/autobot_key")


class SyncOrchestrator:
    """Orchestrates role-based code distribution."""

    def __init__(self):
        self.cache_dir = CODE_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def _get_node_and_role_info(
        self, node_id: str, role_name: str
    ) -> Tuple[bool, str, Optional[SyncNodeContext]]:
        """
        Get node and role information from database.

        Helper for sync_node_role (Issue #665).

        Returns:
            Tuple of (success, message, context) where context contains node/role info.
        """
        async with db_service.session() as db:
            node_result = await db.execute(select(Node).where(Node.node_id == node_id))
            node = node_result.scalar_one_or_none()

            if not node:
                return False, f"Node not found: {node_id}", None

            role_result = await db.execute(select(Role).where(Role.name == role_name))
            role = role_result.scalar_one_or_none()

            if not role:
                return False, f"Role not found: {role_name}", None

            if not role.source_paths:
                return False, f"Role has no source paths: {role_name}", None

            ctx = SyncNodeContext()
            ctx.node_ip = node.ip_address
            ctx.node_user = node.ssh_user or "autobot"
            ctx.node_port = node.ssh_port or 22
            ctx.source_paths = role.source_paths
            ctx.target_path = role.target_path
            ctx.post_sync_cmd = role.post_sync_cmd
            ctx.auto_restart = role.auto_restart
            ctx.systemd_service = role.systemd_service

        return True, "OK", ctx

    def _build_ssh_options(self, port: int) -> str:
        """
        Build SSH options string for rsync.

        Helper for sync_node_role (Issue #665).
        """
        ssh_opts = (
            "ssh -o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=30 "
            f"-p {port}"
        )
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"
        return ssh_opts

    def _build_ssh_command(self, port: int, user: str, host: str) -> list:
        """
        Build base SSH command list.

        Helper for sync_node_role (Issue #665).
        """
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-p",
            str(port),
        ]
        if Path(SSH_KEY_PATH).exists():
            ssh_cmd.extend(["-i", SSH_KEY_PATH])
        ssh_cmd.append(f"{user}@{host}")
        return ssh_cmd

    async def _rsync_source_path(
        self,
        cache_path: Path,
        source_path: str,
        ssh_opts: str,
        ctx: SyncNodeContext,
    ) -> Tuple[bool, str]:
        """
        Rsync a single source path to the target node.

        Helper for sync_node_role (Issue #665).
        """
        src = cache_path / source_path.rstrip("/")
        if not src.exists():
            logger.warning("Source path not found in cache: %s", src)
            return True, "skipped"

        rsync_src = f"{src}/" if source_path.endswith("/") else str(src)
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
            f"{ctx.node_user}@{ctx.node_ip}:{ctx.target_path}/",
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
            return True, "OK"

        except asyncio.TimeoutError:
            return False, f"Sync timed out for {source_path}"
        except Exception as e:
            return False, f"Sync error: {e}"

    async def _run_post_sync_command(self, ctx: SyncNodeContext) -> None:
        """
        Execute post-sync command on remote node.

        Helper for sync_node_role (Issue #665).
        """
        if not ctx.post_sync_cmd:
            return

        try:
            ssh_cmd = self._build_ssh_command(ctx.node_port, ctx.node_user, ctx.node_ip)
            ssh_cmd.append(ctx.post_sync_cmd)

            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await asyncio.wait_for(proc.communicate(), timeout=300)
        except Exception as e:
            logger.warning("Post-sync command failed: %s", e)

    async def _restart_systemd_service(
        self, ctx: SyncNodeContext, node_id: str, restart: bool
    ) -> None:
        """
        Restart systemd service on remote node if configured.

        Helper for sync_node_role (Issue #665).
        """
        if not (restart and ctx.auto_restart and ctx.systemd_service):
            return

        try:
            ssh_cmd = self._build_ssh_command(ctx.node_port, ctx.node_user, ctx.node_ip)
            ssh_cmd.append(f"sudo systemctl restart {ctx.systemd_service}")

            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)
            logger.info("Restarted %s on %s", ctx.systemd_service, node_id)
        except Exception as e:
            logger.warning("Service restart failed: %s", e)

    async def _update_node_role_record(
        self, node_id: str, role_name: str, commit: str
    ) -> None:
        """
        Update or create NodeRole record in database.

        Helper for sync_node_role (Issue #665).
        """
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

    async def _get_source_node_info(self, db) -> Tuple[bool, str, Optional[dict]]:
        """
        Get active code source and node information from database.

        Helper for pull_from_source (Issue #665).

        Returns:
            Tuple of (success, message, node_info_dict) where node_info_dict contains
            node_ip, node_user, repo_path, and commit.
        """
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

        # Return node info
        node_info = {
            "node_ip": node.ip_address,
            "node_user": node.ssh_user or "autobot",
            "repo_path": source.repo_path,
            "branch": source.branch,
            "commit": source.last_known_commit or "latest",
        }

        return True, "OK", node_info

    def _build_rsync_command(
        self, node_ip: str, node_user: str, repo_path: str, cache_path: Path
    ) -> list:
        """
        Build rsync command for pulling code from source node.

        Helper for pull_from_source (Issue #665).
        """
        ssh_opts = (
            "ssh -o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            "-o ConnectTimeout=30"
        )
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"

        return [
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

    async def _get_current_git_commit(
        self, node_ip: str, node_user: str, repo_path: str
    ) -> Optional[str]:
        """
        Get current git commit from source node via SSH.

        Helper for pull_from_source.

        Args:
            node_ip: Source node IP address
            node_user: SSH user for source node
            repo_path: Path to git repository on source node

        Returns:
            Full 40-character commit hash, or None if failed
        """
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
        ]
        if Path(SSH_KEY_PATH).exists():
            ssh_cmd.extend(["-i", SSH_KEY_PATH])

        ssh_cmd.extend(
            [
                f"{node_user}@{node_ip}",
                f"git -C {repo_path} rev-parse HEAD 2>/dev/null || echo ''",
            ]
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)

            if proc.returncode != 0:
                logger.warning(
                    "Failed to get git commit from %s: %s",
                    node_ip,
                    stderr.decode("utf-8", errors="replace")[:200],
                )
                return None

            commit = stdout.decode("utf-8", errors="replace").strip()
            if len(commit) == 40 and commit.isalnum():
                return commit

            logger.warning("Invalid git commit format from %s: %s", node_ip, commit)
            return None

        except asyncio.TimeoutError:
            logger.warning("Timeout getting git commit from %s", node_ip)
            return None
        except Exception as e:
            logger.warning("Error getting git commit from %s: %s", node_ip, e)
            return None

    async def _update_code_source_commit(self, db: "AsyncSession", commit: str) -> None:
        """
        Update active code source with new commit hash.

        Helper for pull_from_source.

        Args:
            db: Database session
            commit: New commit hash to set
        """
        result = await db.execute(
            select(CodeSource).where(CodeSource.is_active == True)  # noqa: E712
        )
        source = result.scalar_one_or_none()

        if source:
            source.last_known_commit = commit
            await db.commit()
            logger.info("Updated CodeSource commit to %s", commit[:12])

    async def _run_rsync(
        self,
        rsync_cmd: list,
        commit: str,
        node_ip: str,
        cache_path: Path,
    ) -> Tuple[bool, str, Optional[str]]:
        """Execute rsync to pull code to cache. Helper for pull_from_source. Ref: #1088."""
        try:
            logger.info(
                "Pulling code from %s to cache (commit: %s)", node_ip, commit[:12]
            )
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
            return True, f"Code cached at {commit[:12]}", commit
        except asyncio.TimeoutError:
            return False, "Pull timed out", None
        except Exception as e:
            logger.error("Pull error: %s", e)
            return False, str(e), None

    def _is_local_source(self, node_ip: str) -> bool:
        """Return True if the code-source node is this machine. Helper for #1194."""
        from urllib.parse import urlparse

        from config import settings

        own_ip = urlparse(settings.external_url).hostname or ""
        return node_ip in {"127.0.0.1", "localhost", own_ip}

    async def _git_pull_local(self, repo_path: str, branch: str) -> Tuple[bool, str]:
        """Run git pull origin <branch> in a local repo. Helper for #1194."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                repo_path,
                "pull",
                "origin",
                branch,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode("utf-8", errors="replace")
            if proc.returncode != 0:
                logger.error("git pull failed in %s: %s", repo_path, output[:300])
                return False, f"git pull failed: {output[:200]}"
            logger.info("git pull succeeded in %s: %s", repo_path, output[:80])
            return True, output[:100]
        except asyncio.TimeoutError:
            return False, "git pull timed out"
        except Exception as e:
            logger.error("git pull error in %s: %s", repo_path, e)
            return False, str(e)

    async def _get_local_git_commit(self, repo_path: str) -> Optional[str]:
        """Get git HEAD commit from a local repo without SSH. Helper for #1194."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                repo_path,
                "rev-parse",
                "HEAD",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            commit = stdout.decode("utf-8", errors="replace").strip()
            if len(commit) == 40 and commit.isalnum():
                return commit
            logger.warning("Unexpected git HEAD output: %s", commit[:50])
            return None
        except Exception as e:
            logger.warning("Could not get local git commit: %s", e)
            return None

    def _build_local_rsync_command(self, repo_path: str, cache_path: Path) -> list:
        """Build rsync command for local-to-local copy (no SSH). Helper for #1194."""
        return [
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
            f"{repo_path}/",
            f"{cache_path}/",
        ]

    async def _fetch_and_update_commit(
        self, db: AsyncSession, node_info: dict, is_local: bool
    ) -> str:
        """Fetch current commit from source and update DB if it changed. Helper for #1194."""
        if is_local:
            current_commit = await self._get_local_git_commit(node_info["repo_path"])
        else:
            current_commit = await self._get_current_git_commit(
                node_info["node_ip"], node_info["node_user"], node_info["repo_path"]
            )
        if not current_commit:
            logger.warning("Could not get git commit, using database value")
            return node_info["commit"]
        if current_commit != node_info["commit"]:
            logger.info(
                "Updating code source commit: %s -> %s",
                node_info["commit"][:12],
                current_commit[:12],
            )
            await self._update_code_source_commit(db, current_commit)
            node_info["commit"] = current_commit
        return current_commit

    async def pull_from_source(self) -> Tuple[bool, str, Optional[str]]:
        """Pull code from code-source node to SLM cache. Ref: #1088, #1194.

        When code source is local, runs git pull first to update from GitHub.
        When remote, uses SSH rsync as before.
        """
        async with db_service.session() as db:
            success, msg, node_info = await self._get_source_node_info(db)
            if not success:
                return False, msg, None

            is_local = self._is_local_source(node_info["node_ip"])
            if is_local:
                # Update the git clone first, then read new HEAD (#1194)
                ok, pull_msg = await self._git_pull_local(
                    node_info["repo_path"], node_info["branch"]
                )
                if not ok:
                    return False, pull_msg, None

            await self._fetch_and_update_commit(db, node_info, is_local)

        commit = node_info["commit"]
        cache_path = self.cache_dir / commit
        if is_local:
            rsync_cmd = self._build_local_rsync_command(
                node_info["repo_path"], cache_path
            )
        else:
            rsync_cmd = self._build_rsync_command(
                node_info["node_ip"],
                node_info["node_user"],
                node_info["repo_path"],
                cache_path,
            )
        return await self._run_rsync(
            rsync_cmd, commit, node_info["node_ip"], cache_path
        )

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
        # Get node and role info from database
        success, msg, ctx = await self._get_node_and_role_info(node_id, role_name)
        if not success:
            return False, msg

        # Check cache exists
        cache_path = self.cache_dir / commit
        if not cache_path.exists():
            return False, f"Commit not cached: {commit}"

        # Sync each source path
        ssh_opts = self._build_ssh_options(ctx.node_port)
        for source_path in ctx.source_paths:
            success, msg = await self._rsync_source_path(
                cache_path, source_path, ssh_opts, ctx
            )
            if not success:
                return False, msg

        # Run post-sync command and restart service
        await self._run_post_sync_command(ctx)
        await self._restart_systemd_service(ctx, node_id, restart)

        # Update database record
        await self._update_node_role_record(node_id, role_name, commit)

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
