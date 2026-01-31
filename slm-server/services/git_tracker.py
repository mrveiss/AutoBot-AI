# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Git Tracker Service (Issue #741).

Tracks git repository version and checks for updates from remote.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


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

    async def _run_git_command(self, *args: str) -> tuple[str, int]:
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


def get_git_tracker(repo_path: str = "/home/kali/Desktop/AutoBot") -> GitTracker:
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
