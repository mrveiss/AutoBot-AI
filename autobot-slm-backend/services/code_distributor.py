# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code Distributor Service (Issue #741).

Builds the agent code package served by ``GET /code-sync/nodes/{id}/package``.

Pushing code to nodes is not done here: every node sync -- manual, fleet and scheduled -- runs the
fleet-sync job in ``api/code_sync.py`` (``update-all-nodes.yml``, which deploys autobot_shared
before the agent). The rsync path that lived here wrote to a directory #1163 retired (#19352).
"""

import hashlib
import io
import logging
import tarfile
from pathlib import Path

from sqlalchemy import select

from autobot_shared.time_utils import utc_timestamp
from models.database import Setting
from services.database import db_service
from services.git_tracker import DEFAULT_REPO_PATH

logger = logging.getLogger(__name__)

# Configuration
CODE_PACKAGE_DIR = Path("/tmp/slm-code-packages")  # nosec B108
AGENT_CODE_PATH = "autobot-slm-backend/slm/agent"  # Relative to the code_source checkout


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

    async def get_current_commit(self) -> str | None:
        """Get current commit hash from database settings."""
        try:
            async with db_service.session() as db:
                result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
                setting = result.scalar_one_or_none()
                if setting:
                    return setting.value
        except Exception as e:
            logger.error("Failed to get commit hash from database: %s", e)
        return None

    async def build_package(self, commit_hash: str | None = None) -> Path | None:
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
                built_at = utc_timestamp()
                version_content = f'{{"commit": "{commit_hash}", "built_at": "{built_at}"}}'
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


# Singleton instance
_distributor_instance: CodeDistributor | None = None


def get_code_distributor(
    repo_path: str = DEFAULT_REPO_PATH,
) -> CodeDistributor:
    """Get or create the CodeDistributor singleton."""
    global _distributor_instance
    if _distributor_instance is None:
        _distributor_instance = CodeDistributor(repo_path=repo_path)
    return _distributor_instance
