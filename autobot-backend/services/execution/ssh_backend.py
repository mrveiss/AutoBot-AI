# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SSH Execution Backend (Issue #4343)

Executes tasks on remote machines via SSH.
Supports key-based and password authentication.
"""

import asyncio
from typing import Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

try:
    import paramiko
    from paramiko import RejectPolicy, SSHClient
except ImportError:
    paramiko = None
    SSHClient = None

from services.execution.base_backend import (
    BackendType,
    ExecutionBackend,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)

logger = get_logger(__name__)


class SSHBackend(ExecutionBackend):
    """Execute tasks on remote machines via SSH (Issue #4343)."""

    def __init__(
        self,
        hostname: str,
        port: int = 22,
        username: str = "autobot",
        password: str | None = None,
        private_key_path: str | None = None,
        timeout: int = 30,
    ) -> None:
        """Initialize SSH backend.

        Args:
            hostname: Remote host address
            port: SSH port (default: 22)
            username: SSH username
            password: SSH password (if using password auth)
            private_key_path: Path to private key (if using key auth)
            timeout: Connection timeout in seconds

        Raises:
            RuntimeError: If paramiko is not installed
        """
        super().__init__(BackendType.SSH)

        if paramiko is None:
            raise RuntimeError("paramiko package not installed. " "Install with: pip install paramiko")

        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.private_key_path = private_key_path
        self.timeout = timeout
        self._client: SSHClient | None = None

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute task on remote machine via SSH.

        Args:
            task: ExecutionTask with code

        Returns:
            ExecutionResult with captured output

        Raises:
            RuntimeError: If SSH connection fails
        """
        if not await self.is_healthy():
            raise RuntimeError("SSH backend is not healthy")

        result = ExecutionResult(
            task_id=task.task_id,
            status=ExecutionStatus.PENDING,
            backend_type=self.backend_type.value,
        )

        try:
            result.started_at = now_utc()
            result.status = ExecutionStatus.RUNNING

            # Get SSH client
            client = await self._get_ssh_client()

            # Prepare command
            cmd = self._prepare_command(task)

            # Execute with timeout
            try:
                stdin, stdout, stderr = await asyncio.wait_for(
                    self._execute_command(client, cmd),
                    timeout=task.timeout_seconds,
                )

                result.stdout = stdout.read().decode(encoding="utf-8", errors="replace")
                result.stderr = stderr.read().decode(encoding="utf-8", errors="replace")
                result.return_code = stdout.channel.recv_exit_status()

                result.status = ExecutionStatus.SUCCESS if result.return_code == 0 else ExecutionStatus.FAILED

            except asyncio.TimeoutError:
                result.status = ExecutionStatus.TIMEOUT
                result.stderr = f"Command exceeded timeout of {task.timeout_seconds}s"
                result.return_code = -1

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.stderr = f"SSH execution error: {str(e)}"
            result.return_code = -1
            logger.exception(f"Error executing task {task.task_id} via SSH: {e}")

        finally:
            result.completed_at = now_utc()
            if result.started_at:
                result.execution_time_ms = (result.completed_at - result.started_at).total_seconds() * 1000

        return result

    async def health_check(self) -> bool:
        """Check if SSH connection is available.

        Returns:
            True if SSH connection can be established
        """
        try:
            client = await self._get_ssh_client()
            # Try a simple command
            stdin, stdout, stderr = client.exec_command(
                "true"
            )  # nosec B601 - hardcoded literal command in health check, not user input
            stdout.channel.recv_exit_status()
            return True
        except Exception as e:
            logger.warning(f"SSH health check failed: {e}")
            return False

    async def cleanup(self) -> None:
        """Close SSH connection."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing SSH connection: {e}")

    async def verify_task_compatibility(self, task: ExecutionTask) -> Tuple[bool, str]:
        """Verify task can run via SSH.

        Args:
            task: Task to check

        Returns:
            Tuple of (is_compatible, reason)
        """
        supported_languages = ["python", "bash", "shell"]
        if task.language.lower() not in supported_languages:
            return (
                False,
                f"Language '{task.language}' not supported via SSH. " f"Supported: {', '.join(supported_languages)}",
            )

        return True, ""

    async def _get_ssh_client(self) -> SSHClient:
        """Get or create SSH client connection.

        Returns:
            Connected SSHClient instance

        Raises:
            RuntimeError: If connection fails
        """
        if self._client is None:
            self._client = SSHClient()
            self._client.load_system_host_keys()
            self._client.set_missing_host_key_policy(RejectPolicy())

            try:
                self._client.connect(
                    self.hostname,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    key_filename=self.private_key_path,
                    timeout=self.timeout,
                )
            except Exception as e:
                self._client = None
                err_msg = str(e)
                if "not found in known_hosts" in err_msg or ("Server" in err_msg and "known_hosts" in err_msg):
                    raise RuntimeError(
                        f"SSH host key for '{self.hostname}' is not in known_hosts. "
                        "Run: ssh-keyscan -H <host> >> ~/.ssh/known_hosts as the autobot service user."
                    ) from e
                raise RuntimeError(f"SSH connection failed: {e}") from e

        return self._client

    async def _execute_command(self, client: SSHClient, cmd: str):
        """Execute command via SSH (async wrapper).

        Args:
            client: SSHClient instance
            cmd: Command to execute

        Returns:
            Tuple of (stdin, stdout, stderr)
        """
        # Run in executor to avoid blocking
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, client.exec_command, cmd)

    def _prepare_command(self, task: ExecutionTask) -> str:
        """Prepare command for SSH execution.

        Args:
            task: ExecutionTask with code

        Returns:
            Command string for SSH
        """
        language = task.language.lower()

        if language == "python":
            # Escape code for shell
            escaped_code = task.code.replace('"', '\\"')
            return f'python -c "{escaped_code}"'
        elif language in ("bash", "shell"):
            # Escape code for shell
            escaped_code = task.code.replace('"', '\\"')
            return f'bash -c "{escaped_code}"'
        else:
            escaped_code = task.code.replace('"', '\\"')
            return f'bash -c "{escaped_code}"'
