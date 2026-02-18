# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Promoter (Phase 6)

Writes an approved draft skill to autobot-backend/skills/builtin/
and optionally commits it to git.
"""
import asyncio
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


class SkillPromoter:
    """Promotes a draft skill package to the builtin codebase directory."""

    def __init__(self, skills_base_dir: Optional[str] = None) -> None:
        """Initialize with optional override for the builtin skills directory."""
        base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        self.skills_dir = skills_base_dir or os.path.join(
            base, "autobot-backend", "skills", "builtin"
        )

    async def promote(
        self,
        name: str,
        skill_md: str,
        skill_py: Optional[str],
        issue_ref: str = "",
        auto_commit: bool = True,
    ) -> str:
        """Write skill files to disk and optionally git commit.

        Returns the path to the promoted skill directory.
        """
        dest = os.path.join(self.skills_dir, name)
        os.makedirs(dest, exist_ok=True)
        self._write_skill_md(dest, skill_md)
        if skill_py:
            self._write_skill_py(dest, skill_py)
        if auto_commit:
            await self._lint_and_commit(dest, name, issue_ref)
        logger.info("Skill promoted to disk: %s -> %s", name, dest)
        return dest

    @staticmethod
    def _write_skill_md(dest: str, skill_md: str) -> None:
        """Write SKILL.md content to the destination directory."""
        with open(os.path.join(dest, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(skill_md)

    @staticmethod
    def _write_skill_py(dest: str, skill_py: str) -> None:
        """Write skill.py content to the destination directory."""
        with open(os.path.join(dest, "skill.py"), "w", encoding="utf-8") as f:
            f.write(skill_py)

    async def _lint_and_commit(self, dest: str, name: str, issue_ref: str) -> None:
        """Run ruff --fix on skill.py then git commit the promoted skill."""
        skill_py_path = os.path.join(dest, "skill.py")
        if os.path.exists(skill_py_path):
            await _run_cmd(["ruff", "check", "--fix", skill_py_path])
        ref = f" (#{issue_ref})" if issue_ref else ""
        msg = f"feat(skills): promote {name} skill to builtin{ref}"
        await _run_cmd(["git", "add", dest], must_succeed=True)
        await _run_cmd(["git", "commit", "-m", msg], must_succeed=True)
        logger.info("Committed promoted skill: %s", name)


async def _run_cmd(cmd: List[str], must_succeed: bool = False) -> None:
    """Run a subprocess command; log stderr on failure.

    Raises RuntimeError if must_succeed is True and command fails.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = f"Command {cmd[0]} failed: {stderr.decode('utf-8', errors='replace')}"
        if must_succeed:
            raise RuntimeError(msg)
        logger.warning(msg)
