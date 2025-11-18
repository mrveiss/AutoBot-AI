# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSH Manager Service
Manages SSH connections and remote command execution across AutoBot's distributed infrastructure

Features:
- Multi-host SSH connection management
- Remote command execution with PTY support
- Integration with SecureCommandExecutor for validation
- Audit logging for all SSH operations
- Host configuration management
- SSH key-based authentication
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import paramiko

from backend.services.ssh_connection_pool import SSHConnectionPool
from src.constants.network_constants import NetworkConstants
from src.secure_command_executor import CommandRisk, SecureCommandExecutor

logger = logging.getLogger(__name__)


@dataclass
class HostConfig:
    """Configuration for an SSH host"""

    name: str
    ip: str
    port: int
    username: str
    description: Optional[str] = None
    enabled: bool = True


@dataclass
class RemoteCommandResult:
    """Result of a remote command execution"""

    host: str
    command: str
    stdout: str
    stderr: str
    exit_code: int
    success: bool
    execution_time: float
    timestamp: datetime
    security_info: Dict[str, Any]


class SSHManager:
    """
    Central SSH management service for AutoBot's distributed infrastructure

    Manages SSH connections to all 6 AutoBot hosts:
    - Main (172.16.168.20): Backend API + Desktop/Terminal VNC
    - Frontend (172.16.168.21): Web interface
    - NPU Worker (172.16.168.22): Hardware AI acceleration
    - Redis (172.16.168.23): Data layer
    - AI Stack (172.16.168.24): AI processing
    - Browser (172.16.168.25): Web automation
    """

    # Default host configurations
    DEFAULT_HOSTS = {
        "main": {
            "ip": NetworkConstants.MAIN_MACHINE_IP,
            "port": 22,
            "user": "autobot",
            "description": "Main machine - Backend API + VNC Desktop",
        },
        "frontend": {
            "ip": NetworkConstants.FRONTEND_VM_IP,
            "port": 22,
            "user": "autobot",
            "description": "Frontend VM - Web interface",
        },
        "npu-worker": {
            "ip": NetworkConstants.NPU_WORKER_VM_IP,
            "port": 22,
            "user": "autobot",
            "description": "NPU Worker VM - Hardware AI acceleration",
        },
        "redis": {
            "ip": NetworkConstants.REDIS_VM_IP,
            "port": 22,
            "user": "autobot",
            "description": "Redis VM - Data layer",
        },
        "ai-stack": {
            "ip": NetworkConstants.AI_STACK_VM_IP,
            "port": 22,
            "user": "autobot",
            "description": "AI Stack VM - AI processing",
        },
        "browser": {
            "ip": NetworkConstants.BROWSER_VM_IP,
            "port": 22,
            "user": "autobot",
            "description": "Browser VM - Web automation (Playwright)",
        },
    }

    def __init__(
        self,
        ssh_key_path: str = "~/.ssh/autobot_key",
        config_path: Optional[str] = None,
        enable_audit_logging: bool = True,
        audit_log_file: str = "logs/audit.log",
    ):
        """
        Initialize SSH Manager

        Args:
            ssh_key_path: Path to SSH private key (default: ~/.ssh/autobot_key)
            config_path: Path to config file (default: None, uses DEFAULT_HOSTS)
            enable_audit_logging: Enable audit logging (default: True)
            audit_log_file: Path to audit log file (default: logs/audit.log)
        """
        self.ssh_key_path = os.path.expanduser(ssh_key_path)
        self.config_path = config_path
        self.enable_audit_logging = enable_audit_logging
        self.audit_log_file = audit_log_file

        # Initialize connection pool
        self.connection_pool = SSHConnectionPool(
            max_connections_per_host=5,
            connect_timeout=30,
            idle_timeout=300,
            health_check_interval=60,
        )

        # Initialize secure command executor for validation
        self.command_executor = SecureCommandExecutor()

        # Load host configurations
        self.hosts: Dict[str, HostConfig] = {}
        self._load_host_configs()

        # Audit logging setup
        if enable_audit_logging:
            self._setup_audit_logging()

        logger.info(
            f"SSH Manager initialized with {len(self.hosts)} hosts, "
            f"key_path={ssh_key_path}"
        )

    def _load_host_configs(self):
        """Load host configurations from config or use defaults"""
        if self.config_path and os.path.exists(self.config_path):
            try:
                # Load from YAML config
                import yaml

                with open(self.config_path, "r") as f:
                    config = yaml.safe_load(f)
                    ssh_config = config.get("ssh", {}).get("hosts", {})

                for name, host_config in ssh_config.items():
                    self.hosts[name] = HostConfig(
                        name=name,
                        ip=host_config["ip"],
                        port=host_config.get("port", 22),
                        username=host_config.get("user", "autobot"),
                        description=host_config.get("description"),
                        enabled=host_config.get("enabled", True),
                    )
                logger.info(
                    f"Loaded {len(self.hosts)} host configs from {self.config_path}"
                )

            except Exception as e:
                logger.warning(
                    f"Failed to load config from {self.config_path}: {e}, using defaults"
                )
                self._load_default_hosts()
        else:
            self._load_default_hosts()

    def _load_default_hosts(self):
        """Load default host configurations"""
        for name, config in self.DEFAULT_HOSTS.items():
            self.hosts[name] = HostConfig(
                name=name,
                ip=config["ip"],
                port=config["port"],
                username=config["user"],
                description=config["description"],
                enabled=True,
            )
        logger.info(f"Loaded {len(self.hosts)} default host configurations")

    def _setup_audit_logging(self):
        """Setup audit logging"""
        try:
            # Ensure log directory exists
            log_dir = os.path.dirname(self.audit_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            # Create audit logger
            self.audit_logger = logging.getLogger("ssh_audit")
            self.audit_logger.setLevel(logging.INFO)

            # File handler
            handler = logging.FileHandler(self.audit_log_file)
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            self.audit_logger.addHandler(handler)

            logger.info(f"Audit logging enabled: {self.audit_log_file}")

        except Exception as e:
            logger.error(f"Failed to setup audit logging: {e}")
            self.enable_audit_logging = False

    def _audit_log(self, event_type: str, data: Dict[str, Any]):
        """Log audit event"""
        if not self.enable_audit_logging:
            return

        try:
            audit_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "data": data,
            }
            self.audit_logger.info(json.dumps(audit_entry))
        except Exception as e:
            logger.error(f"Audit logging failed: {e}")

    async def start(self):
        """Start SSH manager and connection pool"""
        await self.connection_pool.start()
        logger.info("SSH Manager started")

    async def stop(self):
        """Stop SSH manager and cleanup connections"""
        await self.connection_pool.stop()
        logger.info("SSH Manager stopped")

    def get_host_config(self, host: str) -> Optional[HostConfig]:
        """
        Get host configuration by name

        Args:
            host: Host name (e.g., 'main', 'frontend', 'redis')

        Returns:
            HostConfig if found, None otherwise
        """
        return self.hosts.get(host)

    def list_hosts(self) -> List[HostConfig]:
        """List all configured hosts"""
        return list(self.hosts.values())

    async def execute_command(
        self,
        host: str,
        command: str,
        timeout: int = 30,
        validate: bool = True,
        use_pty: bool = False,
    ) -> RemoteCommandResult:
        """
        Execute command on remote host

        Args:
            host: Host name (e.g., 'main', 'frontend')
            command: Command to execute
            timeout: Command timeout in seconds (default: 30)
            validate: Validate command security (default: True)
            use_pty: Use PTY for interactive commands (default: False)

        Returns:
            RemoteCommandResult with command output and metadata

        Raises:
            ValueError: If host not found or command validation fails
            ConnectionError: If SSH connection fails
            TimeoutError: If command execution times out
        """
        start_time = datetime.now()

        # Get host configuration
        host_config = self.get_host_config(host)
        if not host_config:
            raise ValueError(f"Unknown host: {host}")

        if not host_config.enabled:
            raise ValueError(f"Host {host} is disabled")

        # Validate command security if requested
        security_info = {}
        if validate:
            risk_level, reasons = self.command_executor.assess_command_risk(command)
            security_info = {
                "validated": True,
                "risk_level": risk_level.value,
                "reasons": reasons,
            }

            # Block forbidden and high-risk commands
            if risk_level in [CommandRisk.FORBIDDEN, CommandRisk.HIGH]:
                security_info["blocked"] = True
                security_info["reason"] = f"Command blocked: {'; '.join(reasons)}"

                self._audit_log(
                    "command_blocked",
                    {
                        "host": host,
                        "command": command,
                        "risk_level": risk_level.value,
                        "reason": security_info["reason"],
                    },
                )

                raise PermissionError(security_info["reason"])

        # Audit log command execution attempt
        self._audit_log(
            "command_execution",
            {
                "host": host,
                "command": command,
                "timeout": timeout,
                "use_pty": use_pty,
                "validated": validate,
            },
        )

        try:
            # Get SSH connection from pool
            client = await self.connection_pool.get_connection(
                host=host_config.ip,
                port=host_config.port,
                username=host_config.username,
                key_path=self.ssh_key_path,
            )

            # Execute command
            if use_pty:
                stdout, stderr, exit_code = await self._execute_with_pty(
                    client, command, timeout
                )
            else:
                stdout, stderr, exit_code = await self._execute_simple(
                    client, command, timeout
                )

            # Release connection back to pool
            await self.connection_pool.release_connection(
                client,
                host=host_config.ip,
                port=host_config.port,
                username=host_config.username,
            )

            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds()

            # Create result
            result = RemoteCommandResult(
                host=host,
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                success=(exit_code == 0),
                execution_time=execution_time,
                timestamp=datetime.now(),
                security_info=security_info,
            )

            # Audit log result
            self._audit_log(
                "command_completed",
                {
                    "host": host,
                    "command": command,
                    "exit_code": exit_code,
                    "execution_time": execution_time,
                    "success": result.success,
                },
            )

            return result

        except Exception as e:
            logger.error(f"Command execution failed on {host}: {e}")

            # Audit log error
            self._audit_log(
                "command_failed", {"host": host, "command": command, "error": str(e)}
            )

            raise

    async def _execute_simple(
        self, client: paramiko.SSHClient, command: str, timeout: int
    ) -> Tuple[str, str, int]:
        """
        Execute command without PTY

        Args:
            client: SSH client
            command: Command to execute
            timeout: Timeout in seconds

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

            # Read output
            stdout_data = stdout.read().decode("utf-8", errors="replace")
            stderr_data = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()

            return stdout_data, stderr_data, exit_code

        except Exception as e:
            logger.error(f"Simple command execution failed: {e}")
            raise

    async def _execute_with_pty(
        self, client: paramiko.SSHClient, command: str, timeout: int
    ) -> Tuple[str, str, int]:
        """
        Execute command with PTY (for interactive commands)

        Args:
            client: SSH client
            command: Command to execute
            timeout: Timeout in seconds

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        try:
            # Request PTY
            transport = client.get_transport()
            channel = transport.open_session()
            channel.get_pty()

            # Execute command
            channel.exec_command(command)

            # Set timeout
            channel.settimeout(timeout)

            # Read output
            stdout_data = ""
            while True:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode("utf-8", errors="replace")
                    stdout_data += chunk

                if channel.exit_status_ready():
                    break

                await asyncio.sleep(0.1)

            # Get exit status
            exit_code = channel.recv_exit_status()

            # Close channel
            channel.close()

            return stdout_data, "", exit_code

        except Exception as e:
            logger.error(f"PTY command execution failed: {e}")
            raise

    async def execute_command_all_hosts(
        self,
        command: str,
        timeout: int = 30,
        validate: bool = True,
        parallel: bool = True,
    ) -> Dict[str, RemoteCommandResult]:
        """
        Execute command on all enabled hosts

        Args:
            command: Command to execute
            timeout: Command timeout in seconds (default: 30)
            validate: Validate command security (default: True)
            parallel: Execute in parallel (default: True)

        Returns:
            Dictionary mapping host names to RemoteCommandResult
        """
        enabled_hosts = [h.name for h in self.hosts.values() if h.enabled]

        if parallel:
            # Execute in parallel
            tasks = [
                self.execute_command(host, command, timeout, validate)
                for host in enabled_hosts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Map results to hosts
            return {
                host: result if not isinstance(result, Exception) else result
                for host, result in zip(enabled_hosts, results)
            }
        else:
            # Execute sequentially
            results = {}
            for host in enabled_hosts:
                try:
                    results[host] = await self.execute_command(
                        host, command, timeout, validate
                    )
                except Exception as e:
                    results[host] = e

            return results

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        return await self.connection_pool.get_pool_stats()

    async def health_check_all_hosts(self) -> Dict[str, bool]:
        """
        Check health of all configured hosts

        Returns:
            Dictionary mapping host names to health status (True=healthy, False=unhealthy)
        """
        results = {}

        for host_name, host_config in self.hosts.items():
            if not host_config.enabled:
                results[host_name] = None
                continue

            try:
                result = await self.execute_command(
                    host=host_name,
                    command="echo health_check",
                    timeout=5,
                    validate=False,
                )
                results[host_name] = result.success and "health_check" in result.stdout
            except Exception as e:
                logger.warning(f"Health check failed for {host_name}: {e}")
                results[host_name] = False

        return results
