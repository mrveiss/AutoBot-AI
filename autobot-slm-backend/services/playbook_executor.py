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

    def _parse_play1_task(self, task_name: str) -> Optional[Dict[str, str]]:
        """
        Parse Play 1 (SLM) task name for progress.

        Helper for _parse_progress (Issue #880).
        """
        if "Starting SLM Server" in task_name:
            return {
                "stage": "slm_starting",
                "message": "Preparing SLM server update...",
            }
        elif "Sync autobot-slm-backend" in task_name:
            return {"stage": "slm_syncing", "message": "Syncing SLM backend code..."}
        elif "Restart autobot-slm-backend" in task_name:
            return {
                "stage": "slm_restarting",
                "message": "Restarting SLM backend (expect brief disconnect)...",
            }
        elif "Wait for SLM backend" in task_name:
            return {
                "stage": "slm_waiting",
                "message": "Waiting for SLM backend to stabilize...",
            }
        elif "SLM Server Update Complete" in task_name:
            return {"stage": "slm_complete", "message": "SLM server update complete ✓"}
        return None

    def _parse_play2_task(self, task_name: str) -> Optional[Dict[str, str]]:
        """
        Parse Play 2 (Infrastructure) task name for progress.

        Helper for _parse_progress (Issue #880).
        """
        if "Starting Node Update" in task_name:
            return {
                "stage": "nodes_starting",
                "message": "Starting infrastructure node updates...",
            }
        elif "Backend | Sync" in task_name:
            return {"stage": "node_backend", "message": "Syncing backend node code..."}
        elif "Frontend | Sync" in task_name:
            return {
                "stage": "node_frontend",
                "message": "Syncing frontend node code...",
            }
        elif "NPU | Sync" in task_name:
            return {"stage": "node_npu", "message": "Syncing NPU worker code..."}
        elif "Browser | Sync" in task_name:
            return {
                "stage": "node_browser",
                "message": "Syncing browser automation code...",
            }
        elif "Node Update Complete" in task_name:
            return {"stage": "node_complete", "message": "Node update complete ✓"}
        return None

    def _parse_play_line(self, line: str) -> Optional[Dict[str, str]]:
        """
        Parse PLAY line for overall progress.

        Helper for _parse_progress (Issue #880).
        """
        if "Play 1 - Update SLM Server First" in line:
            return {
                "stage": "play1_start",
                "message": "Play 1: Updating SLM server first...",
            }
        elif "Play 2 - Update Other Infrastructure" in line:
            return {
                "stage": "play2_start",
                "message": "Play 2: Updating infrastructure nodes...",
            }
        elif "Fleet Update Summary" in line:
            return {"stage": "complete", "message": "Fleet update complete ✓"}
        return None

    def _parse_progress(self, line: str) -> Optional[Dict[str, str]]:
        """
        Parse Ansible output line for progress updates (Issue #880).

        Args:
            line: Single line of Ansible output

        Returns:
            Dict with 'stage' and 'message' keys if progress found, None otherwise
        """
        # Match TASK lines with [PLAY N] prefix
        if "TASK [" in line and "[PLAY " in line:
            try:
                task_start = line.index("TASK [")
                task_name = line[task_start + 6 :].split("]")[0]

                if "[PLAY 1]" in task_name:
                    return self._parse_play1_task(task_name)
                elif "[PLAY 2]" in task_name:
                    return self._parse_play2_task(task_name)
            except (ValueError, IndexError):
                pass

        # Match PLAY lines for overall progress
        if "PLAY [" in line:
            return self._parse_play_line(line)

        return None

    def _build_ansible_command(
        self,
        playbook_path: Path,
        limit: Optional[List[str]],
        tags: Optional[List[str]],
        extra_vars: Optional[Dict[str, str]],
        check_mode: bool,
    ) -> List[str]:
        """
        Build Ansible command with parameters.

        Helper for execute_playbook (Issue #880).
        """
        ansible_cmd = self._find_ansible_playbook()
        cmd = [ansible_cmd, "-i", str(self.inventory_path), str(playbook_path)]

        if limit:
            cmd.extend(["--limit", ",".join(limit)])
        if tags:
            cmd.extend(["--tags", ",".join(tags)])
        if extra_vars:
            for key, value in extra_vars.items():
                cmd.extend(["-e", f"{key}={value}"])
        if check_mode:
            cmd.append("--check")

        return cmd

    async def _stream_playbook_output(
        self,
        process: asyncio.subprocess.Process,
        progress_callback: Optional[callable],
    ) -> List[str]:
        """
        Stream and parse playbook output for progress.

        Helper for execute_playbook (Issue #880).
        """
        output_lines = []
        if process.stdout:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="replace").rstrip()
                output_lines.append(line_str)

                if progress_callback:
                    progress = self._parse_progress(line_str)
                    if progress:
                        try:
                            await progress_callback(progress)
                        except Exception as e:
                            logger.debug(
                                f"Progress callback error: {e}", exc_info=False
                            )

        return output_lines

    async def execute_playbook(
        self,
        playbook_name: str,
        limit: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        extra_vars: Optional[Dict[str, str]] = None,
        check_mode: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, any]:
        """
        Execute an Ansible playbook with optional progress updates (Issue #880).

        Args:
            playbook_name: Name of playbook file (e.g., "update-all-nodes.yml")
            limit: List of hosts to limit execution to
            tags: List of tags to run
            extra_vars: Extra variables to pass to playbook
            check_mode: Run in check mode (dry run)
            progress_callback: Async function to call with progress updates

        Returns:
            Dict with keys: success (bool), output (str), returncode (int)
        """
        playbook_path = self.ansible_dir / playbook_name

        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")
        if not self.inventory_path.exists():
            raise FileNotFoundError(f"Inventory not found: {self.inventory_path}")

        cmd = self._build_ansible_command(
            playbook_path, limit, tags, extra_vars, check_mode
        )
        logger.info(f"Executing Ansible playbook: {' '.join(cmd[:5])}...")

        env = {
            **os.environ,
            "ANSIBLE_FORCE_COLOR": "0",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_SSH_RETRIES": "3",
            "ANSIBLE_LOCAL_TEMP": "/tmp/ansible_local_tmp",  # nosec B108
        }

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
                env=env,
            )

            output_lines = await self._stream_playbook_output(
                process, progress_callback
            )
            await process.wait()
            output = "\n".join(output_lines)

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
