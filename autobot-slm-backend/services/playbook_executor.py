# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ansible Playbook Executor Service

Unified service for executing Ansible playbooks from API endpoints.
Used by Code Sync, Updates, and Infrastructure pages.
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PlaybookExecutor:
    """Execute Ansible playbooks programmatically."""

    def __init__(self, ansible_dir: Optional[Path] = None):
        """
        Initialize playbook executor.

        Args:
            ansible_dir: Path to Ansible directory (defaults to autobot-slm-backend/ansible)
        """
        if ansible_dir is None:
            ansible_dir = Path(
                os.getenv("SLM_ANSIBLE_DIR", "/opt/autobot/autobot-slm-backend/ansible")
            )
        self.ansible_dir = ansible_dir
        self.inventory_path = ansible_dir / "inventory" / "slm-nodes.yml"

    def _find_ansible_playbook(self) -> str:
        """Find ansible-playbook executable."""
        ansible_path = shutil.which("ansible-playbook")
        if ansible_path:
            return ansible_path

        # Try common paths
        common_paths = [
            "/usr/bin/ansible-playbook",
            "/usr/local/bin/ansible-playbook",
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        raise FileNotFoundError(
            "ansible-playbook not found. Install: apt install ansible"
        )

    async def execute_playbook(
        self,
        playbook_name: str,
        limit: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        extra_vars: Optional[Dict[str, str]] = None,
        check_mode: bool = False,
    ) -> Dict[str, any]:
        """
        Execute an Ansible playbook.

        Args:
            playbook_name: Name of playbook file (e.g., "update-all-nodes.yml")
            limit: List of hosts to limit execution to
            tags: List of tags to run
            extra_vars: Extra variables to pass to playbook
            check_mode: Run in check mode (dry run)

        Returns:
            Dict with keys: success (bool), output (str), returncode (int)
        """
        playbook_path = self.ansible_dir / playbook_name

        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        if not self.inventory_path.exists():
            raise FileNotFoundError(f"Inventory not found: {self.inventory_path}")

        # Build command
        ansible_cmd = self._find_ansible_playbook()
        cmd = [
            ansible_cmd,
            "-i",
            str(self.inventory_path),
            str(playbook_path),
        ]

        # Add limit
        if limit:
            cmd.extend(["--limit", ",".join(limit)])

        # Add tags
        if tags:
            cmd.extend(["--tags", ",".join(tags)])

        # Add extra vars
        if extra_vars:
            for key, value in extra_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

        # Add check mode
        if check_mode:
            cmd.append("--check")

        logger.info(f"Executing Ansible playbook: {' '.join(cmd[:5])}...")

        # Set environment
        env = {
            **os.environ,
            "ANSIBLE_FORCE_COLOR": "0",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_SSH_RETRIES": "3",
            "ANSIBLE_LOCAL_TEMP": "/tmp/ansible_local_tmp",  # nosec B108 - Avoid ProtectHome conflicts
        }

        # Execute
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
                env=env,
            )

            stdout, _ = await process.communicate()
            output = stdout.decode("utf-8", errors="replace")

            success = process.returncode == 0

            if success:
                logger.info(f"Playbook {playbook_name} completed successfully")
            else:
                logger.error(
                    f"Playbook {playbook_name} failed with code {process.returncode}"
                )

            return {
                "success": success,
                "output": output,
                "returncode": process.returncode,
            }

        except Exception as e:
            logger.exception(f"Failed to execute playbook {playbook_name}: {e}")
            return {
                "success": False,
                "output": f"Error: {str(e)}",
                "returncode": -1,
            }


# Singleton instance
_playbook_executor: Optional[PlaybookExecutor] = None


def get_playbook_executor() -> PlaybookExecutor:
    """Get singleton playbook executor instance."""
    global _playbook_executor
    if _playbook_executor is None:
        _playbook_executor = PlaybookExecutor()
    return _playbook_executor
