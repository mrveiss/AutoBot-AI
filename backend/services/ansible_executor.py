# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ansible Executor Service

Executes Ansible playbooks with real-time event streaming using ansible-runner.
Provides async interface for integration with Celery tasks.
"""

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional

from backend.type_defs.common import Metadata
import ansible_runner

logger = logging.getLogger(__name__)


class AnsibleExecutor:
    """
    Executes Ansible playbooks with real-time event streaming
    """

    def __init__(self, private_data_dir: Optional[str] = None):
        """
        Initialize Ansible executor

        Args:
            private_data_dir: Directory for ansible-runner artifacts.
                            Defaults to /tmp/ansible-runner
        """
        if private_data_dir is None:
            private_data_dir = "/tmp/ansible-runner"

        self.private_data_dir = Path(private_data_dir)
        self.private_data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"AnsibleExecutor initialized with private_data_dir: {self.private_data_dir}"
        )

    async def run_playbook(
        self,
        playbook_path: str,
        inventory: Metadata,
        extra_vars: Optional[Metadata] = None,
        event_callback: Optional[Callable[[Dict], None]] = None,
        run_id: Optional[str] = None,
    ) -> ansible_runner.Runner:
        """
        Execute Ansible playbook with event streaming

        Args:
            playbook_path: Path to playbook (relative to ansible/)
            inventory: Dynamic inventory dictionary
            extra_vars: Variables to pass to playbook
            event_callback: Callback function for real-time events
            run_id: Unique identifier for this run

        Returns:
            ansible_runner.Runner instance with results
        """
        if extra_vars is None:
            extra_vars = {}

        if run_id is None:
            run_id = f"deploy_{id(asyncio.current_task())}"

        logger.info(
            f"Starting Ansible playbook execution: {playbook_path} (run_id: {run_id})"
        )

        # Execute in thread pool (ansible-runner is synchronous)
        loop = asyncio.get_event_loop()
        runner = await loop.run_in_executor(
            None,
            self._execute_runner,
            playbook_path,
            inventory,
            extra_vars,
            event_callback,
            run_id,
        )

        return runner

    def _execute_runner(
        self,
        playbook_path: str,
        inventory: Metadata,
        extra_vars: Metadata,
        event_callback: Optional[Callable[[Dict], None]],
        run_id: str,
    ) -> ansible_runner.Runner:
        """
        Synchronous runner execution (called from thread pool)

        Args:
            playbook_path: Path to playbook
            inventory: Dynamic inventory dictionary
            extra_vars: Variables to pass to playbook
            event_callback: Callback function for real-time events
            run_id: Unique identifier for this run

        Returns:
            ansible_runner.Runner instance with results
        """
        inventory_file = None
        temp_dir = None

        try:
            # Create temporary directory for this run
            temp_dir = tempfile.mkdtemp(
                prefix=f"ansible_{run_id}_", dir=self.private_data_dir
            )
            temp_path = Path(temp_dir)

            # Write inventory to temp file
            inventory_file = temp_path / "inventory.json"
            with open(inventory_file, "w") as f:
                json.dump(inventory, f, indent=2)

            logger.info(f"Executing playbook: {playbook_path}")
            logger.debug(f"Inventory: {inventory}")
            logger.debug(f"Extra vars: {extra_vars}")

            # Run ansible-runner
            runner = ansible_runner.run(
                private_data_dir=str(temp_path),
                playbook=playbook_path,
                inventory=str(inventory_file),
                extravars=extra_vars,
                quiet=False,
                json_mode=True,
                event_handler=(
                    event_callback if event_callback else self._default_event_handler
                ),
                ident=run_id,
            )

            # Log execution results
            if runner.status == "successful":
                logger.info(
                    f"Playbook execution successful: {playbook_path} (run_id: {run_id})"
                )
            else:
                logger.error(
                    f"Playbook execution failed: {playbook_path} (run_id: {run_id})"
                )
                logger.error(f"Status: {runner.status}")
                logger.error(f"Return code: {runner.rc}")

            return runner

        except Exception as e:
            logger.exception(f"Error executing playbook {playbook_path}: {e}")
            raise

        finally:
            # Cleanup temporary files
            if temp_dir and Path(temp_dir).exists():
                try:
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")

    def _default_event_handler(self, event: Dict):
        """Default event handler for logging"""
        event_type = event.get("event", "unknown")
        if event_type in ["runner_on_ok", "runner_on_failed", "runner_on_unreachable"]:
            logger.info(f"Ansible event: {event_type} - {event.get('event_data', {})}")
        else:
            logger.debug(f"Ansible event: {event_type}")

    async def get_playbook_path(self, playbook_name: str) -> str:
        """
        Resolve playbook path relative to AutoBot ansible directory

        Args:
            playbook_name: Name of playbook (e.g., 'deploy_role.yml')

        Returns:
            Full path to playbook
        """
        # Assuming AutoBot ansible directory structure
        base_path = Path(__file__).parent.parent.parent / "ansible"
        playbook_path = base_path / "playbooks" / playbook_name

        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        return str(playbook_path)
