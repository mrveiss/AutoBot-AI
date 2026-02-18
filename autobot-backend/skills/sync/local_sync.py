# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Local directory skill repo sync (Phase 3)."""
import logging
import os
from typing import Any, Dict, List, Optional

from skills.models import SkillState
from skills.sync.base_sync import BaseRepoSync

logger = logging.getLogger(__name__)


class LocalDirSync(BaseRepoSync):
    """Sync skills from a local directory tree.

    Scans for subdirectories containing SKILL.md files.
    """

    def __init__(self, path: str) -> None:
        """Initialize with the root directory to scan."""
        self.path = path

    async def discover(self) -> List[Dict[str, Any]]:
        """Scan path for directories containing SKILL.md."""
        packages = []
        try:
            entries = list(os.scandir(self.path))
        except (FileNotFoundError, PermissionError) as exc:
            logger.error("Cannot scan skill repo path %s: %s", self.path, exc)
            return []
        for entry in entries:
            if not entry.is_dir():
                continue
            package = self._load_skill_package(entry)
            if package is not None:
                packages.append(package)
        return packages

    def _load_skill_package(self, entry: os.DirEntry) -> Optional[Dict[str, Any]]:
        """Load a single skill package from a directory entry.

        Returns None if the directory does not contain SKILL.md.
        """
        skill_md_path = os.path.join(entry.path, "SKILL.md")
        if not os.path.exists(skill_md_path):
            return None
        try:
            with open(skill_md_path, encoding="utf-8") as f:
                skill_md = f.read()
        except OSError as exc:
            logger.warning("Cannot read SKILL.md at %s: %s", skill_md_path, exc)
            return None
        skill_py = self._read_skill_py(entry.path)
        manifest = self._parse_skill_md(skill_md)
        return {
            "name": manifest.get("name", entry.name),
            "version": manifest.get("version", "1.0.0"),
            "state": SkillState.INSTALLED,
            "skill_md": skill_md,
            "skill_py": skill_py,
            "manifest": manifest,
        }

    @staticmethod
    def _read_skill_py(skill_dir: str) -> Optional[str]:
        """Read skill.py content if present, else return None."""
        skill_py_path = os.path.join(skill_dir, "skill.py")
        if not os.path.exists(skill_py_path):
            return None
        try:
            with open(skill_py_path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None
