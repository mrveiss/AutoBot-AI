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
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
CODE_PACKAGE_DIR = Path("/tmp/slm-code-packages")
AGENT_CODE_PATH = "src/slm/agent"  # Relative to repo root


class CodeDistributor:
    """
    Builds and distributes code packages to SLM agents.
    """

    def __init__(self, repo_path: str = "/home/kali/Desktop/AutoBot"):
        """
        Initialize CodeDistributor.

        Args:
            repo_path: Path to the git repository
        """
        self.repo_path = Path(repo_path)
        self.package_dir = CODE_PACKAGE_DIR
        self.package_dir.mkdir(parents=True, exist_ok=True)

    async def get_current_commit(self) -> Optional[str]:
        """Get current commit hash from repository."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(self.repo_path),
                "rev-parse",
                "HEAD",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return stdout.decode().strip()
        except Exception as e:
            logger.error("Failed to get commit hash: %s", e)
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
    ) -> tuple[bool, str]:
        """
        Trigger sync on a specific node via SSH.

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
        # Build the sync command for the agent
        restart_flag = "--restart" if restart else "--no-restart"
        strategy_flag = f"--strategy={strategy}"

        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=30",
            "-o",
            "BatchMode=yes",
            "-p",
            str(ssh_port),
            f"{ssh_user}@{ip_address}",
            f"slm-agent sync {restart_flag} {strategy_flag}",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            output = stdout.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                logger.info("Sync triggered on node %s", node_id)
                return True, f"Sync initiated: {output.strip()}"
            else:
                logger.warning("Sync failed on node %s: %s", node_id, output)
                return False, f"Sync failed: {output.strip()}"

        except asyncio.TimeoutError:
            logger.error("Sync timeout on node %s", node_id)
            return False, "Sync command timed out"
        except Exception as e:
            logger.error("Sync error on node %s: %s", node_id, e)
            return False, f"Sync error: {e}"


# Singleton instance
_distributor_instance: Optional[CodeDistributor] = None


def get_code_distributor(
    repo_path: str = "/home/kali/Desktop/AutoBot",
) -> CodeDistributor:
    """Get or create the CodeDistributor singleton."""
    global _distributor_instance
    if _distributor_instance is None:
        _distributor_instance = CodeDistributor(repo_path=repo_path)
    return _distributor_instance
