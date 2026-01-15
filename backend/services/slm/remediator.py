# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Remediator Service

Handles conservative remediation actions for unhealthy nodes.

Remediation actions:
- Service restart via SSH
- Health check verification
- Rollback on failure

Design principles:
- Conservative: Only restart services, never re-enroll automatically
- Logged: All actions are logged for audit trail
- Bounded: Max retry limit before marking ERROR
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RemediationAction(Enum):
    """Available remediation actions."""
    RESTART_SERVICE = "restart_service"
    RESTART_ALL_SERVICES = "restart_all_services"
    HEALTH_CHECK = "health_check"


class RemediationResult(Enum):
    """Result of remediation attempt."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"


@dataclass
class RemediationAttempt:
    """Record of a remediation attempt."""
    node_id: str
    node_name: str
    action: RemediationAction
    result: RemediationResult
    timestamp: datetime
    duration_ms: float
    details: Optional[Dict] = None
    error: Optional[str] = None


class SSHExecutor:
    """
    Execute commands on remote nodes via SSH.

    Uses asyncio subprocess for non-blocking execution.
    """

    def __init__(
        self,
        ssh_user: str = "autobot",
        ssh_timeout: int = 30,
        ssh_options: Optional[List[str]] = None,
    ):
        """
        Initialize SSH executor.

        Args:
            ssh_user: Default SSH username
            ssh_timeout: Connection timeout in seconds
            ssh_options: Additional SSH options
        """
        self.ssh_user = ssh_user
        self.ssh_timeout = ssh_timeout
        self.ssh_options = ssh_options or [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
        ]

    async def execute(
        self,
        host: str,
        command: str,
        user: Optional[str] = None,
        port: int = 22,
    ) -> tuple[int, str, str]:
        """
        Execute command on remote host via SSH.

        Args:
            host: Target hostname or IP
            command: Command to execute
            user: SSH username (default: self.ssh_user)
            port: SSH port

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        user = user or self.ssh_user

        ssh_cmd = [
            "ssh",
            *self.ssh_options,
            "-p", str(port),
            f"{user}@{host}",
            command,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.ssh_timeout,
            )

            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )

        except asyncio.TimeoutError:
            logger.warning("SSH command timed out: %s@%s", user, host)
            return (-1, "", "SSH command timed out")
        except Exception as e:
            logger.error("SSH execution error: %s", e)
            return (-1, "", str(e))

    async def check_connectivity(self, host: str, port: int = 22) -> bool:
        """Check if host is reachable via SSH."""
        returncode, _, _ = await self.execute(host, "echo ok", port=port)
        return returncode == 0


class SLMRemediator:
    """
    Service lifecycle remediation manager.

    Provides conservative remediation for unhealthy nodes:
    - Restart failed services
    - Verify recovery via health check
    - Log all remediation attempts
    """

    def __init__(
        self,
        ssh_executor: Optional[SSHExecutor] = None,
        max_retries: int = 3,
    ):
        """
        Initialize remediator.

        Args:
            ssh_executor: SSH executor instance
            max_retries: Maximum remediation attempts per node
        """
        self.ssh = ssh_executor or SSHExecutor()
        self.max_retries = max_retries
        self._history: List[RemediationAttempt] = []

        logger.info("SLM Remediator initialized (max_retries=%d)", max_retries)

    @property
    def history(self) -> List[RemediationAttempt]:
        """Get remediation attempt history."""
        return self._history.copy()

    def get_history_for_node(self, node_id: str) -> List[RemediationAttempt]:
        """Get remediation history for a specific node."""
        return [a for a in self._history if a.node_id == node_id]

    async def restart_service(
        self,
        node_id: str,
        node_name: str,
        host: str,
        service_name: str,
        ssh_user: str = "autobot",
        ssh_port: int = 22,
    ) -> RemediationAttempt:
        """
        Restart a specific service on a node.

        Args:
            node_id: Node ID for logging
            node_name: Node name for logging
            host: Node IP address
            service_name: systemd service name
            ssh_user: SSH username
            ssh_port: SSH port

        Returns:
            RemediationAttempt record
        """
        start = datetime.utcnow()
        command = f"sudo systemctl restart {service_name}"

        logger.info(
            "Restarting service %s on %s (%s)",
            service_name, node_name, host,
        )

        returncode, stdout, stderr = await self.ssh.execute(
            host, command, user=ssh_user, port=ssh_port,
        )

        duration = (datetime.utcnow() - start).total_seconds() * 1000

        if returncode == 0:
            result = RemediationResult.SUCCESS
            logger.info(
                "Service %s restarted successfully on %s (%.0fms)",
                service_name, node_name, duration,
            )
        elif returncode == -1 and "timed out" in stderr:
            result = RemediationResult.TIMEOUT
            logger.warning(
                "Service restart timed out on %s: %s",
                node_name, service_name,
            )
        else:
            result = RemediationResult.FAILURE
            logger.error(
                "Service restart failed on %s: %s (rc=%d, stderr=%s)",
                node_name, service_name, returncode, stderr,
            )

        attempt = RemediationAttempt(
            node_id=node_id,
            node_name=node_name,
            action=RemediationAction.RESTART_SERVICE,
            result=result,
            timestamp=start,
            duration_ms=duration,
            details={"service": service_name, "returncode": returncode},
            error=stderr if result != RemediationResult.SUCCESS else None,
        )

        self._history.append(attempt)
        return attempt

    async def restart_all_services(
        self,
        node_id: str,
        node_name: str,
        host: str,
        services: List[str],
        ssh_user: str = "autobot",
        ssh_port: int = 22,
    ) -> List[RemediationAttempt]:
        """
        Restart all services for a role on a node.

        Args:
            node_id: Node ID for logging
            node_name: Node name for logging
            host: Node IP address
            services: List of systemd service names
            ssh_user: SSH username
            ssh_port: SSH port

        Returns:
            List of RemediationAttempt records
        """
        attempts = []

        for service in services:
            attempt = await self.restart_service(
                node_id=node_id,
                node_name=node_name,
                host=host,
                service_name=service,
                ssh_user=ssh_user,
                ssh_port=ssh_port,
            )
            attempts.append(attempt)

            # Stop on first failure
            if attempt.result != RemediationResult.SUCCESS:
                break

        return attempts

    async def check_node_reachable(
        self,
        node_id: str,
        node_name: str,
        host: str,
        ssh_port: int = 22,
    ) -> RemediationAttempt:
        """
        Check if a node is reachable via SSH.

        Args:
            node_id: Node ID for logging
            node_name: Node name for logging
            host: Node IP address
            ssh_port: SSH port

        Returns:
            RemediationAttempt record
        """
        start = datetime.utcnow()

        reachable = await self.ssh.check_connectivity(host, port=ssh_port)

        duration = (datetime.utcnow() - start).total_seconds() * 1000

        result = RemediationResult.SUCCESS if reachable else RemediationResult.UNREACHABLE

        attempt = RemediationAttempt(
            node_id=node_id,
            node_name=node_name,
            action=RemediationAction.HEALTH_CHECK,
            result=result,
            timestamp=start,
            duration_ms=duration,
            details={"reachable": reachable},
        )

        self._history.append(attempt)
        return attempt


# Singleton instance
_remediator: Optional[SLMRemediator] = None


def get_remediator() -> SLMRemediator:
    """Get or create the singleton remediator instance."""
    global _remediator
    if _remediator is None:
        _remediator = SLMRemediator()
    return _remediator
