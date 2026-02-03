# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal completion service using bash compgen for authentic completion.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    """Result of a completion request."""

    completions: List[str]
    prefix: str
    common_prefix: str


class TerminalCompletionService:
    """Bash-like tab completion using compgen subprocess."""

    async def get_completions(
        self, text: str, cursor_pos: int, cwd: str, env: Optional[dict] = None
    ) -> CompletionResult:
        """
        Get completions based on context.

        Args:
            text: Full command line text
            cursor_pos: Cursor position in text
            cwd: Current working directory
            env: Environment variables

        Returns:
            CompletionResult with matching completions
        """
        # Extract the full argument including path context
        text_before_cursor = text[:cursor_pos]
        last_space = text_before_cursor.rfind(" ")
        full_word = text_before_cursor[last_space + 1 :]

        # Extract just the final component for display
        word = self._extract_current_word(text, cursor_pos)
        env = env or os.environ.copy()

        if self._is_first_word(text, cursor_pos):
            completions = await self._complete_commands(word, env)
        elif word.startswith("$"):
            completions = await self._complete_env_vars(word[1:], env)
        else:
            # For paths, pass the full path context
            completions = await self._complete_paths(full_word, cwd)

        return CompletionResult(
            completions=completions,
            prefix=word,
            common_prefix=self._find_common_prefix(completions),
        )

    def _extract_current_word(self, text: str, cursor_pos: int) -> str:
        """Extract the word being completed at cursor position."""
        if not text or cursor_pos == 0:
            return ""

        text_before_cursor = text[:cursor_pos]
        last_space = text_before_cursor.rfind(" ")
        word = text_before_cursor[last_space + 1 :]

        # For paths, extract just the final component after last /
        if "/" in word:
            last_slash = word.rfind("/")
            return word[last_slash + 1 :]

        return word

    def _is_first_word(self, text: str, cursor_pos: int) -> bool:
        """Check if cursor is in the first word (command position)."""
        text_before_cursor = text[:cursor_pos]
        return " " not in text_before_cursor.strip()

    async def _complete_commands(self, prefix: str, env: dict) -> List[str]:
        """Complete commands using compgen."""
        cmd = f'compgen -A alias -A builtin -A command -- "{prefix}" 2>/dev/null'
        return await self._run_compgen(cmd, env)

    async def _complete_env_vars(self, prefix: str, env: dict) -> List[str]:
        """Complete environment variable names."""
        cmd = f'compgen -v -- "{prefix}" 2>/dev/null'
        completions = await self._run_compgen(cmd, env)
        return ["$" + c for c in completions]

    async def _complete_paths(self, prefix: str, cwd: str) -> List[str]:
        """Complete file and directory paths."""
        expanded_prefix = os.path.expanduser(prefix)
        cmd = f'compgen -f -- "{expanded_prefix}" 2>/dev/null'
        completions = await self._run_compgen(
            cmd, {"HOME": os.environ.get("HOME", "")}, cwd
        )

        result = []
        for c in completions:
            full_path = os.path.join(cwd, c) if not os.path.isabs(c) else c
            if os.path.isdir(full_path):
                result.append(c + "/")
            else:
                result.append(c)
        return result

    async def _run_compgen(
        self, cmd: str, env: dict, cwd: Optional[str] = None
    ) -> List[str]:
        """Run compgen command and return results."""
        try:
            proc = await asyncio.create_subprocess_shell(
                f"bash -c '{cmd}'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            lines = stdout.decode().strip().split("\n")
            return [line for line in lines if line]
        except asyncio.TimeoutError:
            logger.warning("Completion command timed out")
            return []
        except Exception as e:
            logger.error("Completion error: %s", e)
            return []

    def _find_common_prefix(self, completions: List[str]) -> str:
        """Find longest common prefix among completions."""
        if not completions:
            return ""
        if len(completions) == 1:
            return completions[0]

        prefix = completions[0]
        for completion in completions[1:]:
            while not completion.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        return prefix
