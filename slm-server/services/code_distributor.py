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

        # SSH options for rsync
        ssh_opts = (
            f"ssh -o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            f"-o ConnectTimeout=30 "
            f"-p {ssh_port}"
        )

        # Add SSH key if it exists
        if Path(SSH_KEY_PATH).exists():
            ssh_opts += f" -i {SSH_KEY_PATH}"

        # Step 1: Ensure remote directory exists
        mkdir_cmd = [
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
            mkdir_cmd.extend(["-i", SSH_KEY_PATH])
        mkdir_script = (
            f"sudo mkdir -p {REMOTE_AGENT_PATH} && "
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

        # Step 2: Rsync agent code to remote node
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
            f"{ssh_user}@{ip_address}:{REMOTE_AGENT_PATH}/",
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

        except asyncio.TimeoutError:
            logger.error("Rsync timeout on node %s", node_id)
            return False, "Rsync timed out"
        except Exception as e:
            logger.error("Rsync error on node %s: %s", node_id, e)
            return False, f"Rsync error: {e}"

        # Step 3: Update version.json on remote node
        version_json = (
            f'{{"commit": "{commit_hash}", '
            f'"synced_at": "{datetime.utcnow().isoformat()}", '
            f'"source": "fleet-sync"}}'
        )
        version_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-p",
            str(ssh_port),
        ]
        if Path(SSH_KEY_PATH).exists():
            version_cmd.extend(["-i", SSH_KEY_PATH])
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

        # Step 4: Restart slm-agent service if requested
        if restart and strategy != "manual":
            restart_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-p",
                str(ssh_port),
            ]
            if Path(SSH_KEY_PATH).exists():
                restart_cmd.extend(["-i", SSH_KEY_PATH])
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

        # Step 5: Update node version in database
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
