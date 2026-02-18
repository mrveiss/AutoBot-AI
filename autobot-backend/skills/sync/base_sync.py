# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Base sync interface for skill repositories (Phase 3)."""
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import yaml


class BaseRepoSync(ABC):
    """Abstract base for all skill repo sync implementations."""

    @abstractmethod
    async def discover(self) -> List[Dict[str, Any]]:
        """Return list of skill package dicts found in this repo."""

    @staticmethod
    def _parse_skill_md(content: str) -> Dict[str, Any]:
        """Parse YAML frontmatter from SKILL.md content into manifest dict."""
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}
        try:
            return yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return {}
