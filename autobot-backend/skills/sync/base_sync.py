# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Base sync interface for skill repositories (Phase 3)."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

import yaml

from autobot_shared.frontmatter import split_frontmatter


class BaseRepoSync(ABC):
    """Abstract base for all skill repo sync implementations."""

    @abstractmethod
    async def discover(self) -> List[Dict[str, Any]]:
        """Return list of skill package dicts found in this repo."""

    @staticmethod
    def _parse_skill_md(content: str) -> Dict[str, Any]:
        """Parse YAML frontmatter from SKILL.md content into manifest dict."""
        raw, _ = split_frontmatter(content)
        if raw is None:
            return {}
        try:
            return yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            return {}
