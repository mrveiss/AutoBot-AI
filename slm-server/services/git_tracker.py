# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Git Tracker Service (Issue #741).

Tracks git repository version and checks for updates from remote.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Setting

logger = logging.getLogger(__name__)

# Import db_service at module level for testing
try:
    from services.database import db_service
except ImportError:
    # Allow testing without full service initialization
    db_service = None  # type: ignore

# Configuration
VERSION_CHECK_INTERVAL = 300  # 5 minutes
DEFAULT_REPO_PATH = os.environ.get("SLM_REPO_PATH", "/opt/autobot")


class GitTracker:
    """
    Tracks git repository versions and checks for remote updates.

    Used by SLM to monitor the agent code repository and notify
    nodes when updates are available.
    """

    def __init__(
        self,
        repo_path: str,
        remote: str = "origin",
        branch: str = "main",
    ):
        """
        Initialize GitTracker.

        Args:
            repo_path: Path to the git repository
            remote: Remote name (default: origin)
            branch: Branch to track (default: main)
        """
        self.repo_path = repo_path
        self.remote = remote
        self.branch = branch
        self.latest_commit: Optional[str] = None
        self.last_fetch: Optional[datetime] = None

    async def _run_git_command(self, *args: str) -> Tuple[str, int]:
        """
        Run a git command and return output.

        Args:
            *args: Git command arguments

        Returns:
            Tuple of (stdout, return_code)
        """
        cmd = ["git", "-C", self.repo_path, *args]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.warning(
                    "Git command failed: %s, stderr: %s",
                    " ".join(cmd),
                    stderr.decode().strip(),
                )

            return stdout.decode().strip(), proc.returncode

        except Exception as e:
            logger.error("Error running git command: %s", e)
            return "", 1

    async def get_local_commit(self) -> Optional[str]:
        """
        Get the current commit hash of the local repository.

        Returns:
            Current commit hash or None if error
        """
        output, returncode = await self._run_git_command("rev-parse", "HEAD")

        if returncode == 0 and output:
            return output
        return None

    async def fetch_remote(self) -> bool:
        """
        Fetch updates from the remote repository.

        Returns:
            True if fetch succeeded, False otherwise
        """
        _, returncode = await self._run_git_command("fetch", self.remote)

        if returncode == 0:
            self.last_fetch = datetime.utcnow()
            return True
        return False

    async def get_remote_commit(self, branch: Optional[str] = None) -> Optional[str]:
        """
        Get the latest commit hash from the remote branch.

        Args:
            branch: Branch name (uses self.branch if not specified)

        Returns:
            Remote commit hash or None if error
        """
        target_branch = branch or self.branch
        ref = f"{self.remote}/{target_branch}"

        output, returncode = await self._run_git_command("rev-parse", ref)

        if returncode == 0 and output:
            return output
        return None

    async def check_for_updates(self, fetch: bool = True) -> dict:
        """
        Check if updates are available from the remote.

        Args:
            fetch: Whether to fetch from remote first (default: True)

        Returns:
            Dict with has_update, local_commit, remote_commit, last_fetch
        """
        if fetch:
            await self.fetch_remote()

        local_commit = await self.get_local_commit()
        remote_commit = await self.get_remote_commit()

        has_update = (
            local_commit is not None
            and remote_commit is not None
            and local_commit != remote_commit
        )

        if remote_commit:
            self.latest_commit = remote_commit

        return {
            "has_update": has_update,
            "local_commit": local_commit,
            "remote_commit": remote_commit,
            "last_fetch": self.last_fetch.isoformat() if self.last_fetch else None,
        }

    async def pull_updates(self) -> bool:
        """
        Pull updates from the remote repository.

        Returns:
            True if pull succeeded, False otherwise
        """
        _, returncode = await self._run_git_command("pull", self.remote, self.branch)
        return returncode == 0


# Singleton instance for the SLM agent code repository
_tracker_instance: Optional[GitTracker] = None


def get_git_tracker(repo_path: str = DEFAULT_REPO_PATH) -> GitTracker:
    """
    Get or create the GitTracker singleton instance.

    Args:
        repo_path: Path to the repository

    Returns:
        GitTracker instance
    """
    global _tracker_instance

    if _tracker_instance is None:
        _tracker_instance = GitTracker(repo_path=repo_path)

    return _tracker_instance


async def update_latest_version_setting(
    db: AsyncSession,
    commit_hash: str,
) -> None:
    """
    Update the slm_agent_latest_commit setting in database.

    Args:
        db: Database session
        commit_hash: The latest commit hash to store
    """
    result = await db.execute(
        select(Setting).where(Setting.key == "slm_agent_latest_commit")
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = commit_hash
    else:
        setting = Setting(
            key="slm_agent_latest_commit",
            value=commit_hash,
        )
        db.add(setting)

    await db.commit()
    logger.info("Updated slm_agent_latest_commit to: %s", commit_hash[:12])


async def version_check_task(
    repo_path: str = DEFAULT_REPO_PATH,
    interval: int = VERSION_CHECK_INTERVAL,
) -> None:
    """
    Background task that periodically checks for code updates.

    Args:
        repo_path: Path to the git repository
        interval: Check interval in seconds (default: 300 = 5 min)
    """
    tracker = get_git_tracker(repo_path)
    logger.info("Starting version check task (interval: %ds)", interval)

    while True:
        try:
            result = await tracker.check_for_updates()

            if result["remote_commit"]:
                async with db_service.session() as db:
                    await update_latest_version_setting(db, result["remote_commit"])

                if result["has_update"]:
                    logger.info(
                        "Update available: local=%s, remote=%s",
                        result["local_commit"][:12]
                        if result["local_commit"]
                        else "unknown",
                        result["remote_commit"][:12],
                    )
            else:
                logger.warning("Failed to get remote commit hash")

        except Exception as e:
            logger.error("Version check failed: %s", e)

        await asyncio.sleep(interval)


def start_version_checker(
    repo_path: str = DEFAULT_REPO_PATH,
    interval: int = VERSION_CHECK_INTERVAL,
) -> asyncio.Task:
    """
    Start the version checker background task.

    Args:
        repo_path: Path to the git repository
        interval: Check interval in seconds

    Returns:
        The asyncio Task object
    """
    return asyncio.create_task(version_check_task(repo_path, interval))
