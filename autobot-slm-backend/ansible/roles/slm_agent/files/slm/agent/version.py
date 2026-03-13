# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Version Module (Issue #741).

Manages version tracking for the SLM agent code.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default paths
VERSION_FILE_PATH = Path("/var/lib/slm-agent/version.json")
AGENT_CODE_PATH = Path("/opt/autobot/autobot-slm-agent")  # #1121/#1129


class AgentVersion:
    """
    Manages SLM agent version information.

    Reads and writes version.json file that contains the git commit
    hash of the currently deployed agent code.
    """

    def __init__(
        self,
        version_file: Path = VERSION_FILE_PATH,
        code_path: Path = AGENT_CODE_PATH,
    ):
        """
        Initialize AgentVersion.

        Args:
            version_file: Path to version.json
            code_path: Path to agent code directory
        """
        self.version_file = version_file
        self.code_path = code_path
        self._cached_version: Optional[dict] = None

    def get_version(self) -> Optional[str]:
        """
        Get the current code version (commit hash).

        Returns:
            Commit hash string or None if not available
        """
        version_info = self.get_version_info()
        return version_info.get("commit") if version_info else None

    def get_version_info(self) -> Optional[dict]:
        """
        Get full version information from version.json.

        Returns:
            Dict with commit, built_at, etc. or None if not available
        """
        if self._cached_version:
            return self._cached_version

        if not self.version_file.exists():
            logger.warning("Version file not found: %s", self.version_file)
            return None

        try:
            with open(self.version_file, "r", encoding="utf-8") as f:
                self._cached_version = json.load(f)
                return self._cached_version
        except json.JSONDecodeError as e:
            logger.error("Invalid version.json: %s", e)
            return None
        except Exception as e:
            logger.error("Error reading version file: %s", e)
            return None

    def save_version(
        self,
        commit: str,
        built_at: Optional[datetime] = None,
        extra_data: Optional[dict] = None,
    ) -> bool:
        """
        Save version information to version.json.

        Args:
            commit: Git commit hash
            built_at: Build timestamp (default: now)
            extra_data: Additional metadata

        Returns:
            True if saved successfully
        """
        if built_at is None:
            built_at = datetime.utcnow()

        version_info = {
            "commit": commit,
            "built_at": built_at.isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        if extra_data:
            version_info.update(extra_data)

        try:
            # Ensure directory exists
            self.version_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.version_file, "w", encoding="utf-8") as f:
                json.dump(version_info, f, indent=2)

            # Clear cache
            self._cached_version = version_info

            logger.info("Saved version: %s", commit[:12])
            return True

        except Exception as e:
            logger.error("Failed to save version: %s", e)
            return False

    def clear_cache(self) -> None:
        """Clear cached version info to force re-read."""
        self._cached_version = None

    def is_outdated(self, latest_version: str) -> bool:
        """
        Check if current version is outdated.

        Args:
            latest_version: The latest available version

        Returns:
            True if outdated, False if up-to-date or unknown
        """
        current = self.get_version()
        if not current:
            return False  # Unknown state, not necessarily outdated

        return current != latest_version


# Singleton instance
_version_instance: Optional[AgentVersion] = None


def get_agent_version(
    version_file: Path = VERSION_FILE_PATH,
    code_path: Path = AGENT_CODE_PATH,
) -> AgentVersion:
    """
    Get or create the AgentVersion singleton.

    Args:
        version_file: Path to version.json
        code_path: Path to agent code

    Returns:
        AgentVersion instance
    """
    global _version_instance

    if _version_instance is None:
        _version_instance = AgentVersion(
            version_file=version_file,
            code_path=code_path,
        )

    return _version_instance


def reset_version_instance() -> None:
    """Reset the singleton instance (for testing)."""
    global _version_instance
    _version_instance = None
