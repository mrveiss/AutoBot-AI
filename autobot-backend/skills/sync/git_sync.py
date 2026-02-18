# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Git repository skill sync (Phase 3)."""
import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List

from skills.sync.base_sync import BaseRepoSync
from skills.sync.local_sync import LocalDirSync

logger = logging.getLogger(__name__)


class GitRepoSync(BaseRepoSync):
    """Sync skills from a git repository.

    Clones the repo to a temp directory then delegates to LocalDirSync.
    """

    def __init__(self, url: str, branch: str = "main") -> None:
        """Initialize with repository URL and branch name."""
        self.url = url
        self.branch = branch

    async def discover(self) -> List[Dict[str, Any]]:
        """Clone/pull git repo then scan for skill directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            await self._clone(tmpdir)
            skills_dir = self._find_skills_dir(tmpdir)
            return await LocalDirSync(skills_dir).discover()

    async def _clone(self, dest: str) -> None:
        """Clone repo shallowly into dest directory."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth=1",
                "--branch",
                self.branch,
                self.url,
                dest,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "git clone failed: git binary not found on PATH"
            ) from exc
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git clone failed: {stderr.decode('utf-8', errors='replace')}"
            )
        logger.info("Cloned skill repo %s@%s", self.url, self.branch)

    @staticmethod
    def _find_skills_dir(repo_root: str) -> str:
        """Return skills/ subdir if it exists, else repo root."""
        skills_sub = os.path.join(repo_root, "skills")
        return skills_sub if os.path.isdir(skills_sub) else repo_root
