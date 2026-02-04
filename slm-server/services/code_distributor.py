# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Distributor Service (Issue #741).

Handles building and distributing code packages to nodes.
"""

import asyncio
import hashlib
import io
import logging
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import select

from models.database import Setting
from services.database import db_service

logger = logging.getLogger(__name__)

# Configuration
CODE_PACKAGE_DIR = Path("/tmp/slm-code-packages")
AGENT_CODE_PATH = "src/slm/agent"  # Relative to repo root
DEFAULT_REPO_PATH = os.environ.get("SLM_REPO_PATH", "/home/autobot/AutoBot")
# Remote agent installation path on managed nodes
REMOTE_AGENT_PATH = "/opt/slm-agent"
# SSH key for connecting to managed nodes
SSH_KEY_PATH = os.environ.get("SLM_SSH_KEY", "/home/autobot/.ssh/autobot_key")


class CodeDistributor:
    """
    Builds and distributes code packages to SLM agents.
    """

    def __init__(self, repo_path: str = DEFAULT_REPO_PATH):
        """
        Initialize CodeDistributor.

        Args:
            repo_path: Path to the git repository
        """
        self.repo_path = Path(repo_path)
        self.package_dir = CODE_PACKAGE_DIR
        self.package_dir.mkdir(parents=True, exist_ok=True)

    async def get_current_commit(self) -> Optional[str]:
        """Get current commit hash from database settings."""
        try:
            async with db_service.session() as db:
                result = await db.execute(
                    select(Setting).where(Setting.key == "slm_agent_latest_commit")
                )
                setting = result.scalar_one_or_none()
                if setting:
                    return setting.value
        except Exception as e:
            logger.error("Failed to get commit hash from database: %s", e)
        return None

    async def build_package(self, commit_hash: Optional[str] = None) -> Optional[Path]:
        """
        Build a code package tarball for distribution.

        Args:
            commit_hash: Specific commit to package (default: current HEAD)

        Returns:
            Path to the created tarball or None if failed
        """
        if not commit_hash:
            commit_hash = await self.get_current_commit()

        if not commit_hash:
            logger.error("Cannot build package: no commit hash")
            return None

        agent_path = self.repo_path / AGENT_CODE_PATH
        if not agent_path.exists():
            logger.error("Agent code path not found: %s", agent_path)
            return None

        # Create package filename
        package_name = f"slm-agent-{commit_hash[:12]}.tar.gz"
        package_path = self.package_dir / package_name

        # Check if already built
        if package_path.exists():
            logger.debug("Package already exists: %s", package_path)
            return package_path

        try:
            # Create tarball
            with tarfile.open(package_path, "w:gz") as tar:
                # Add agent code
                tar.add(agent_path, arcname="agent")

                # Create and add version.json
                built_at = datetime.utcnow().isoformat()
                version_content = (
                    f'{{"commit": "{commit_hash}", "built_at": "{built_at}"}}'
                )
                version_bytes = version_content.encode("utf-8")
                version_info = tarfile.TarInfo(name="version.json")
                version_info.size = len(version_bytes)
                tar.addfile(version_info, io.BytesIO(version_bytes))

            logger.info("Built code package: %s", package_path)
            return package_path

        except Exception as e:
            logger.error("Failed to build package: %s", e)
            if package_path.exists():
                package_path.unlink()
            return None

    def get_package_checksum(self, package_path: Path) -> str:
        """Calculate SHA256 checksum of package."""
        sha256 = hashlib.sha256()
        with open(package_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _build_ssh_command(self, ssh_port: int) -> list:
        """
        Build base SSH command list with common options.

        Helper for trigger_node_sync (Issue #665).

        Args:
            ssh_port: SSH port number

        Returns:
            List of SSH command arguments with common options
        """
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=30",
            "-p",
            str(ssh_port),
        ]
        if Path(SSH_KEY_PATH).exists():
            cmd.extend(["-i", SSH_KEY_PATH])
        return cmd

    async def _ensure_remote_directories(
        self, node_id: str, ip_address: str, ssh_user: str, ssh_port: int
    ) -> None:
        """
        Create remote directory structure for agent installation.

        Helper for trigger_node_sync (Issue #665).

        Args:
            node_id: Node identifier for logging
            ip_address: Node IP address
            ssh_user: SSH username
            ssh_port: SSH port
        """
        mkdir_cmd = self._build_ssh_command(ssh_port)
        mkdir_script = (
            f"sudo mkdir -p {REMOTE_AGENT_PATH}/slm/agent && "
            f"sudo chown -R {ssh_user}:{ssh_user} {REMOTE_AGENT_PATH}"
        )
        mkdir_cmd.extend([f"{ssh_user}@{ip_address}", mkdir_script])

        try:
            proc = await asyncio.create_subprocess_exec(
                *mkdir_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except Exception as e:
            logger.warning("Could not create remote dir on %s: %s", node_id, e)

    async def _create_slm_package_init(
        self, node_id: str, ip_address: str, ssh_user: str, ssh_port: int
    ) -> None:
        """
        Create slm package __init__.py for proper Python import.

        Helper for trigger_node_sync (Issue #665).

        Args:
            node_id: Node identifier for logging
            ip_address: Node IP address
            ssh_user: SSH username
            ssh_port: SSH port
        """
        slm_init_cmd = self._build_ssh_command(ssh_port)
        slm_init_content = (
            "# AutoBot - AI-Powered Automation Platform\\n"
            "# Copyright (c) 2025 mrveiss\\n"
            "# Author: mrveiss\\n"
            '"""SLM Package."""'
        )
        slm_init_script = (
            f"echo -e '{slm_init_content}' > {REMOTE_AGENT_PATH}/slm/__init__.py"
        )
        slm_init_cmd.extend([f"{ssh_user}@{ip_address}", slm_init_script])

        try:
            proc = await asyncio.create_subprocess_exec(
                *slm_init_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except Exception as e:
            logger.warning("Could not create slm/__init__.py on %s: %s", node_id, e)

    async def _rsync_agent_code(
        self,
        node_id: str,
        ip_address: str,
        ssh_user: str,
        ssh_port: int,
        agent_source: Path,
        ssh_opts: str,
    ) -> Tuple[bool, str]:
        """
        Rsync agent code to remote node.

        Helper for trigger_node_sync (Issue #665).

        Args:
            node_id: Node identifier for logging
            ip_address: Node IP address
            ssh_user: SSH username
            ssh_port: SSH port
            agent_source: Path to agent source code
            ssh_opts: SSH options string for rsync

        Returns:
            Tuple of (success, error_message or empty string)
        """
        rsync_cmd = [
            "rsync",
            "-avz",
            "--delete",
            "--exclude",
            "__pycache__",
            "--exclude",
            "*.pyc",
            "--exclude",
            ".git",
            "-e",
            ssh_opts,
            f"{agent_source}/",
            f"{ssh_user}@{ip_address}:{REMOTE_AGENT_PATH}/slm/agent/",
        ]

        try:
            logger.info("Syncing code to node %s (%s)", node_id, ip_address)
            proc = await asyncio.create_subprocess_exec(
                *rsync_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            rsync_output = stdout.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                logger.error("Rsync failed on node %s: %s", node_id, rsync_output)
                return False, f"Rsync failed: {rsync_output.strip()}"

            logger.info("Code synced to node %s", node_id)
            return True, ""

        except asyncio.TimeoutError:
            logger.error("Rsync timeout on node %s", node_id)
            return False, "Rsync timed out"
        except Exception as e:
            logger.error("Rsync error on node %s: %s", node_id, e)
            return False, f"Rsync error: {e}"

    async def _update_remote_version(
        self,
        node_id: str,
        ip_address: str,
        ssh_user: str,
        ssh_port: int,
        commit_hash: str,
    ) -> None:
        """
        Update version.json on remote node.

        Helper for trigger_node_sync (Issue #665).

        Args:
            node_id: Node identifier for logging
            ip_address: Node IP address
            ssh_user: SSH username
            ssh_port: SSH port
            commit_hash: Current commit hash
        """
        version_json = (
            f'{{"commit": "{commit_hash}", '
            f'"synced_at": "{datetime.utcnow().isoformat()}", '
            f'"source": "fleet-sync"}}'
        )
        version_cmd = self._build_ssh_command(ssh_port)
        version_cmd.extend(
            [
                f"{ssh_user}@{ip_address}",
                f"echo '{version_json}' | sudo tee /var/lib/slm-agent/version.json > /dev/null",
            ]
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *version_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except Exception as e:
            logger.warning("Could not update version.json on %s: %s", node_id, e)

    async def _restart_slm_agent(
        self, node_id: str, ip_address: str, ssh_user: str, ssh_port: int
    ) -> None:
        """
        Restart slm-agent service on remote node.

        Helper for trigger_node_sync (Issue #665).

        Args:
            node_id: Node identifier for logging
            ip_address: Node IP address
            ssh_user: SSH username
            ssh_port: SSH port
        """
        restart_cmd = self._build_ssh_command(ssh_port)
        restart_cmd.extend(
            [
                f"{ssh_user}@{ip_address}",
                "sudo systemctl restart slm-agent || true",
            ]
        )

        try:
            logger.info("Restarting slm-agent on node %s", node_id)
            proc = await asyncio.create_subprocess_exec(
                *restart_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            restart_output = stdout.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                logger.info("slm-agent restarted on node %s", node_id)
            else:
                logger.warning(
                    "slm-agent restart may have failed on %s: %s",
                    node_id,
                    restart_output,
                )
        except Exception as e:
            logger.warning("Could not restart slm-agent on %s: %s", node_id, e)

    async def _update_node_database(self, node_id: str, commit_hash: str) -> None:
        """
        Update node version in database.

        Helper for trigger_node_sync (Issue #665).

        Args:
            node_id: Node identifier
            commit_hash: Current commit hash
        """
        try:
            from models.database import CodeStatus, Node

            async with db_service.session() as db:
                result = await db.execute(select(Node).where(Node.node_id == node_id))
                node = result.scalar_one_or_none()
                if node:
                    node.code_version = commit_hash
                    node.code_status = CodeStatus.UP_TO_DATE
                    await db.commit()
                    logger.info("Updated node %s version in database", node_id)
        except Exception as e:
            logger.warning("Could not update node version in database: %s", e)

    async def trigger_node_sync(
        self,
        node_id: str,
        ip_address: str,
        ssh_user: str = "autobot",
        ssh_port: int = 22,
        restart: bool = True,
        strategy: str = "graceful",
    ) -> Tuple[bool, str]:
        """
        Sync code to a specific node via rsync and optionally restart service.

        Issue #741: Actual code sync implementation using rsync.

        Args:
            node_id: Node identifier
            ip_address: Node IP address
            ssh_user: SSH username
            ssh_port: SSH port
            restart: Whether to restart service after sync
            strategy: Restart strategy (immediate/graceful/manual)

        Returns:
            Tuple of (success, message)
        """
        agent_source = self.repo_path / AGENT_CODE_PATH
        if not agent_source.exists():
            return False, f"Agent source not found: {agent_source}"

        # Get current commit for version tracking
        commit_hash = await self.get_current_commit()
        if not commit_hash:
            return False, "Could not determine current commit"

        # Build SSH options string for rsync
        ssh_opts = (
            f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=30 -p {ssh_port}"
        )
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"

        # Step 1: Ensure remote directory structure exists
        await self._ensure_remote_directories(node_id, ip_address, ssh_user, ssh_port)

        # Step 1.5: Create slm package __init__.py for proper Python import
        await self._create_slm_package_init(node_id, ip_address, ssh_user, ssh_port)

        # Step 2: Rsync agent code to remote node
        success, error_msg = await self._rsync_agent_code(
            node_id, ip_address, ssh_user, ssh_port, agent_source, ssh_opts
        )
        if not success:
            return False, error_msg

        # Step 3: Update version.json on remote node
        await self._update_remote_version(
            node_id, ip_address, ssh_user, ssh_port, commit_hash
        )

        # Step 4: Restart slm-agent service if requested
        if restart and strategy != "manual":
            await self._restart_slm_agent(node_id, ip_address, ssh_user, ssh_port)

        # Step 5: Update node version in database
        await self._update_node_database(node_id, commit_hash)

        return True, f"Code synced successfully (commit: {commit_hash})"


# Singleton instance
_distributor_instance: Optional[CodeDistributor] = None


def get_code_distributor(
    repo_path: str = DEFAULT_REPO_PATH,
) -> CodeDistributor:
    """Get or create the CodeDistributor singleton."""
    global _distributor_instance
    if _distributor_instance is None:
        _distributor_instance = CodeDistributor(repo_path=repo_path)
    return _distributor_instance
