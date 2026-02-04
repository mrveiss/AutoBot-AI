# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secure Sandbox Executor

Integration module for executing commands in the enhanced Docker sandbox
with advanced security features.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from docker.errors import DockerException, ImageNotFound

import docker
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class SandboxSecurityLevel(Enum):
    """Security levels for sandbox execution"""

    LOW = "low"  # Permissive, for trusted operations
    MEDIUM = "medium"  # Balanced security and functionality
    HIGH = "high"  # Maximum isolation and restrictions


class SandboxExecutionMode(Enum):
    """Execution modes for different use cases"""

    COMMAND = "command"  # Single command execution
    SCRIPT = "script"  # Script file execution
    INTERACTIVE = "interactive"  # Interactive session
    BATCH = "batch"  # Batch command execution


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution"""

    security_level: SandboxSecurityLevel = SandboxSecurityLevel.HIGH
    execution_mode: SandboxExecutionMode = SandboxExecutionMode.COMMAND
    timeout: int = 300  # 5 minutes default
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    enable_monitoring: bool = True
    enable_network: bool = False
    allowed_commands: Optional[List[str]] = None
    blocked_commands: Optional[List[str]] = None
    environment: Optional[Dict[str, str]] = None
    volumes: Optional[Dict[str, Dict[str, str]]] = None


@dataclass
class SandboxResult:
    """Result of sandbox execution"""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    container_id: str
    security_events: List[Dict[str, Any]]
    resource_usage: Dict[str, Any]
    metadata: Dict[str, Any]


class SecureSandboxExecutor:
    """
    Advanced secure sandbox executor using Docker with enhanced security features.

    Features:
    - Multi-level security isolation
    - Resource usage monitoring
    - Command validation and filtering
    - Security event logging
    - Network isolation controls
    - File system restrictions
    """

    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        """Initialize secure sandbox executor with Docker client and Redis monitoring."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Docker client
        try:
            self.docker_client = docker_client or docker.from_env()
            self.logger.info("Docker client initialized")
        except DockerException as e:
            self.logger.error("Failed to initialize Docker client: %s", e)
            raise

        # Redis for monitoring and coordination
        self.redis_client = get_redis_client(async_client=False)

        # Container management
        self.active_containers: Dict[str, str] = {}
        self.container_prefix = "autobot-sandbox-"

        # Security monitoring
        self.security_events_key = "autobot:sandbox:security:events:"
        self.metrics_key = "autobot:sandbox:metrics:"

        # Ensure sandbox image is available
        self._ensure_sandbox_image()

    def _ensure_sandbox_image(self):
        """Ensure the secure sandbox image is available"""
        image_name = "autobot/secure-sandbox:latest"

        try:
            self.docker_client.images.get(image_name)
            self.logger.info("Sandbox image %s is available", image_name)
        except ImageNotFound:
            self.logger.warning("Sandbox image %s not found, building...", image_name)
            # In production, this would trigger a build process
            # For now, we'll use the basic sandbox image as fallback
            try:
                self.docker_client.images.pull("alpine:3.18")
                self.logger.info("Using alpine:3.18 as fallback sandbox image")
            except Exception as e:
                self.logger.error("Failed to pull fallback image: %s", e)
                raise

    def _create_validation_failure_result(
        self, command: Union[str, List[str]], container_id: str
    ) -> SandboxResult:
        """
        Create a SandboxResult for command validation failure.

        Issue #281: Extracted helper for validation failure result building.

        Args:
            command: Command that failed validation
            container_id: Container identifier

        Returns:
            SandboxResult indicating validation failure
        """
        return SandboxResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="Command validation failed",
            execution_time=0,
            container_id=container_id,
            security_events=[
                {
                    "type": "command_blocked",
                    "command": str(command),
                    "reason": "Failed security validation",
                }
            ],
            resource_usage={},
            metadata={"validation_failed": True},
        )

    def _execute_container_with_timeout(
        self, container, config: SandboxConfig
    ) -> Tuple[int, str, str, Dict[str, Any]]:
        """
        Execute container and collect raw output data. Issue #620.

        Args:
            container: Docker container instance
            config: Sandbox configuration

        Returns:
            Tuple of (exit_code, stdout, stderr, resource_usage)
        """
        container.start()
        try:
            exit_code = container.wait(timeout=config.timeout)["StatusCode"]
        except Exception:
            container.kill()
            exit_code = -9

        logs = container.logs(stdout=True, stderr=True, stream=False)
        stdout_logs, stderr_logs = self._parse_logs(logs)
        stats = container.stats(stream=False)
        resource_usage = self._parse_resource_usage(stats)

        return exit_code, stdout_logs, stderr_logs, resource_usage

    def _build_sandbox_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        execution_time: float,
        container_id: str,
        security_events: List[Dict[str, Any]],
        resource_usage: Dict[str, Any],
        config: SandboxConfig,
    ) -> SandboxResult:
        """
        Build SandboxResult from execution data. Issue #620.

        Args:
            exit_code: Container exit code
            stdout: Standard output
            stderr: Standard error
            execution_time: Total execution time
            container_id: Container identifier
            security_events: Collected security events
            resource_usage: Resource usage metrics
            config: Sandbox configuration

        Returns:
            SandboxResult with execution details
        """
        return SandboxResult(
            success=(exit_code == 0),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            execution_time=execution_time,
            container_id=container_id,
            security_events=security_events,
            resource_usage=resource_usage,
            metadata={
                "security_level": config.security_level.value,
                "execution_mode": config.execution_mode.value,
            },
        )

    async def _run_container_and_collect_results(
        self,
        container,
        container_id: str,
        config: SandboxConfig,
        start_time: float,
    ) -> SandboxResult:
        """
        Run container, wait for completion, and collect results. Issue #620.

        Args:
            container: Docker container instance
            container_id: Container identifier
            config: Sandbox configuration
            start_time: Execution start timestamp

        Returns:
            SandboxResult with execution details
        """
        if config.enable_monitoring:
            asyncio.create_task(self._monitor_container(container.id, container_id))

        (
            exit_code,
            stdout,
            stderr,
            resource_usage,
        ) = self._execute_container_with_timeout(container, config)
        security_events = await self._collect_security_events(container_id)
        execution_time = time.time() - start_time

        result = self._build_sandbox_result(
            exit_code,
            stdout,
            stderr,
            execution_time,
            container_id,
            security_events,
            resource_usage,
            config,
        )
        await self._log_execution_metrics(container_id, result)
        return result

    async def execute_command(
        self, command: Union[str, List[str]], config: Optional[SandboxConfig] = None
    ) -> SandboxResult:
        """
        Execute a command in the secure sandbox.

        Issue #281: Refactored from 111 lines to use extracted helper methods.

        Args:
            command: Command to execute (string or list)
            config: Sandbox configuration

        Returns:
            SandboxResult with execution details
        """
        config = config or SandboxConfig()
        container_id = f"{self.container_prefix}{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        self.logger.info("Executing command in sandbox: %s", command)

        try:
            # Validate command
            if not self._validate_command(command, config):
                # Issue #281: uses helper
                return self._create_validation_failure_result(command, container_id)

            # Prepare container configuration
            container_config = self._prepare_container_config(command, config)

            # Create and start container
            container = self.docker_client.containers.create(**container_config)
            self.active_containers[container_id] = container.id

            # Issue #281: uses helper
            return await self._run_container_and_collect_results(
                container, container_id, config, start_time
            )

        except Exception as e:
            self.logger.error("Sandbox execution error: %s", e)
            return SandboxResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=time.time() - start_time,
                container_id=container_id,
                security_events=[],
                resource_usage={},
                metadata={"error": str(e)},
            )
        finally:
            # Cleanup
            await self._cleanup_container(container_id)

    async def execute_script(
        self,
        script_content: str,
        language: str = "bash",
        config: Optional[SandboxConfig] = None,
    ) -> SandboxResult:
        """
        Execute a script in the secure sandbox.

        Args:
            script_content: Script content to execute
            language: Script language (bash, python, etc.)
            config: Sandbox configuration

        Returns:
            SandboxResult with execution details
        """
        config = config or SandboxConfig(execution_mode=SandboxExecutionMode.SCRIPT)

        # Create temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{language}", delete=False
        ) as f:
            f.write(script_content)
            script_path = f.name

        try:
            # Determine interpreter
            interpreters = {
                "bash": "/bin/bash",
                "sh": "/bin/sh",
                "python": "/usr/bin/python3",
                "python3": "/usr/bin/python3",
            }

            interpreter = interpreters.get(language, "/bin/sh")
            command = [interpreter, script_path]

            # Execute script
            result = await self.execute_command(command, config)

            return result

        finally:
            # Clean up script file
            # Issue #358 - avoid blocking
            try:
                await asyncio.to_thread(os.unlink, script_path)
            except Exception as e:
                self.logger.debug(
                    "Failed to cleanup script file %s: %s", script_path, e
                )

    def _validate_command(
        self, command: Union[str, List[str]], config: SandboxConfig
    ) -> bool:
        """Validate command against security policies."""
        command_parts = command.split() if isinstance(command, str) else command

        if not command_parts:
            return False

        command_name = command_parts[0]

        if self._is_command_blocked(command_name, config):
            return False

        if config.security_level == SandboxSecurityLevel.HIGH:
            if not self._is_command_allowed(command_name, config):
                return False

        return True

    def _is_command_blocked(self, command_name: str, config: SandboxConfig) -> bool:
        """Check if a command is in the blocked list. Issue #620."""
        default_blocked = [
            "sudo",
            "su",
            "doas",
            "mount",
            "umount",
            "iptables",
            "netfilter",
            "docker",
            "podman",
            "systemctl",
            "service",
            "reboot",
            "shutdown",
            "halt",
        ]

        blocked = config.blocked_commands or default_blocked
        if command_name in blocked:
            self.logger.warning("Command blocked by security policy: %s", command_name)
            return True
        return False

    def _is_command_allowed(self, command_name: str, config: SandboxConfig) -> bool:
        """Check if a command is in the whitelist for high security mode. Issue #620."""
        default_allowed = [
            "bash",
            "sh",
            "python3",
            "python",
            "ls",
            "cat",
            "echo",
            "grep",
            "sed",
            "awk",
            "find",
            "which",
            "env",
            "printenv",
        ]

        allowed = config.allowed_commands or default_allowed
        if command_name not in allowed:
            self.logger.warning("Command not in whitelist: %s", command_name)
            return False
        return True

    def _apply_security_level_config(
        self, container_config: Dict[str, Any], config: SandboxConfig
    ) -> None:
        """
        Apply security level specific settings to container configuration.

        Extracted from _prepare_container_config() to reduce function length. Issue #620.

        Args:
            container_config: Container configuration dictionary to modify
            config: Sandbox configuration with security level
        """
        if config.security_level == SandboxSecurityLevel.HIGH:
            container_config["environment"]["SECURITY_LEVEL"] = "high"
            container_config["environment"]["MONITOR_ENABLED"] = "true"
        elif config.security_level == SandboxSecurityLevel.MEDIUM:
            container_config["environment"]["SECURITY_LEVEL"] = "medium"
            container_config["cap_add"] = ["DAC_OVERRIDE", "CHOWN"]
        else:  # LOW
            container_config["environment"]["SECURITY_LEVEL"] = "low"
            container_config["cap_add"] = [
                "DAC_OVERRIDE",
                "CHOWN",
                "FOWNER",
                "SETUID",
                "SETGID",
            ]

    def _apply_volume_config(
        self, container_config: Dict[str, Any], config: SandboxConfig
    ) -> None:
        """
        Apply volume configuration to container.

        Extracted from _prepare_container_config() to reduce function length. Issue #620.

        Args:
            container_config: Container configuration dictionary to modify
            config: Sandbox configuration with volumes
        """
        if config.volumes:
            container_config["volumes"] = config.volumes
        else:
            # Default volumes
            container_config["tmpfs"] = {  # nosec B108 - container tmpfs mounts
                "/tmp": "size=50M,mode=1777",
                "/sandbox/tmp": "size=50M,mode=1777",
            }

    def _prepare_container_config(
        self, command: Union[str, List[str]], config: SandboxConfig
    ) -> Dict[str, Any]:
        """Prepare Docker container configuration"""
        container_config = {
            "image": "autobot/secure-sandbox:latest",
            "command": command if isinstance(command, list) else command.split(),
            "name": f"{self.container_prefix}{uuid.uuid4().hex[:8]}",
            "detach": True,
            "remove": False,
            "network_mode": "none" if not config.enable_network else "bridge",
            "read_only": True,
            "security_opt": ["no-new-privileges"],
            "cap_drop": ["ALL"],
            "cap_add": [],
            "mem_limit": config.memory_limit,
            "memswap_limit": config.memory_limit,
            "cpu_quota": int(config.cpu_limit * 100000),
            "cpu_period": 100000,
            "environment": config.environment or {},
            "labels": {
                "com.autobot.sandbox": "true",
                "com.autobot.security": config.security_level.value,
                "com.autobot.timestamp": str(time.time()),
            },
        }

        self._apply_security_level_config(container_config, config)
        self._apply_volume_config(container_config, config)

        return container_config

    def _parse_logs(self, logs: bytes) -> Tuple[str, str]:
        """Parse container logs into stdout and stderr"""
        # Docker logs format includes stream headers
        # For simplicity, we'll treat all as stdout for now
        # In production, would parse the stream headers properly
        try:
            log_text = logs.decode("utf-8", errors="replace")
            return log_text, ""
        except Exception:
            return "", "Failed to parse logs"

    def _parse_resource_usage(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Parse container stats into resource usage metrics"""
        try:
            cpu_stats = stats.get("cpu_stats", {})
            memory_stats = stats.get("memory_stats", {})

            # Calculate CPU usage percentage
            cpu_delta = cpu_stats.get("cpu_usage", {}).get(
                "total_usage", 0
            ) - stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
            system_delta = cpu_stats.get("system_cpu_usage", 0) - stats.get(
                "precpu_stats", {}
            ).get("system_cpu_usage", 0)

            cpu_percent = 0.0
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * 100.0

            return {
                "cpu_percent": cpu_percent,
                "memory_used": memory_stats.get("usage", 0),
                "memory_limit": memory_stats.get("limit", 0),
                "memory_percent": (
                    (memory_stats.get("usage", 0) / memory_stats.get("limit", 1)) * 100
                ),
            }
        except Exception as e:
            self.logger.error("Failed to parse resource usage: %s", e)
            return {}

    async def _monitor_container(self, container_id: str, sandbox_id: str):
        """Monitor container for security events"""
        try:
            container = self.docker_client.containers.get(container_id)

            # Stream logs for security events
            for line in container.logs(stream=True, follow=True):
                try:
                    log_line = line.decode("utf-8", errors="replace")

                    # Check for security indicators
                    security_indicators = [
                        ("BLOCKED_OUT:", "network_blocked"),
                        ("BLOCKED_IN:", "network_blocked"),
                        ("PORT_SCAN:", "port_scan_detected"),
                        ("ANOMALY DETECTED:", "anomaly_detected"),
                        ("EMERGENCY:", "emergency_action"),
                    ]

                    for indicator, event_type in security_indicators:
                        if indicator in log_line:
                            event = {
                                "timestamp": time.time(),
                                "type": event_type,
                                "message": log_line.strip(),
                                "container_id": sandbox_id,
                            }

                            # Store in Redis (Issue #361 - avoid blocking)
                            event_key = f"{self.security_events_key}{sandbox_id}"
                            event_json = json.dumps(event)
                            await asyncio.to_thread(
                                lambda: (
                                    self.redis_client.lpush(event_key, event_json),
                                    self.redis_client.expire(event_key, 3600),
                                )
                            )

                            self.logger.warning(
                                f"Security event in {sandbox_id}: {event_type}"
                            )

                except Exception as e:
                    self.logger.error("Error processing container log: %s", e)

        except Exception as e:
            self.logger.error("Container monitoring error: %s", e)

    async def _collect_security_events(self, container_id: str) -> List[Dict[str, Any]]:
        """Collect security events for a container"""
        try:
            event_key = f"{self.security_events_key}{container_id}"
            events = []

            # Get all events from Redis (Issue #361 - avoid blocking)
            raw_events = await asyncio.to_thread(
                self.redis_client.lrange, event_key, 0, -1
            )

            for raw_event in raw_events:
                try:
                    event = json.loads(raw_event)
                    events.append(event)
                except Exception as e:
                    self.logger.debug("Skipping malformed security event: %s", e)

            return events

        except Exception as e:
            self.logger.error("Failed to collect security events: %s", e)
            return []

    async def _log_execution_metrics(self, container_id: str, result: SandboxResult):
        """Log execution metrics to Redis"""
        try:
            metrics = {
                "container_id": container_id,
                "timestamp": time.time(),
                "success": result.success,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
                "resource_usage": result.resource_usage,
                "security_events_count": len(result.security_events),
            }

            # Store in Redis (Issue #361 - avoid blocking)
            metrics_key = f"{self.metrics_key}{container_id}"
            metrics_json = json.dumps(metrics)
            success = result.success

            def _store_metrics():
                self.redis_client.setex(metrics_key, 3600, metrics_json)
                stat_key = "successful_executions" if success else "failed_executions"
                self.redis_client.hincrby("autobot:sandbox:stats", stat_key, 1)

            await asyncio.to_thread(_store_metrics)

        except Exception as e:
            self.logger.error("Failed to log metrics: %s", e)

    async def _cleanup_container(self, container_id: str):
        """Clean up container and related resources"""
        try:
            # Remove from active containers
            docker_id = self.active_containers.pop(container_id, None)

            if docker_id:
                try:
                    container = self.docker_client.containers.get(docker_id)
                    container.remove(force=True)
                    self.logger.info("Cleaned up container %s", container_id)
                except Exception as e:
                    self.logger.error("Failed to remove container: %s", e)

            # Clean up Redis keys (they have TTL but we can be explicit)
            # Keys will expire automatically

        except Exception as e:
            self.logger.error("Cleanup error: %s", e)

    async def get_sandbox_stats(self) -> Dict[str, Any]:
        """Get sandbox execution statistics"""
        try:
            # Issue #361 - avoid blocking
            stats = await asyncio.to_thread(
                self.redis_client.hgetall, "autobot:sandbox:stats"
            )

            return {
                "successful_executions": int(stats.get(b"successful_executions", 0)),
                "failed_executions": int(stats.get(b"failed_executions", 0)),
                "active_containers": len(self.active_containers),
                "security_levels_available": [
                    level.value for level in SandboxSecurityLevel
                ],
            }

        except Exception as e:
            self.logger.error("Failed to get stats: %s", e)
            return {}


# Global instance for easy access with lazy initialization
# Lazy loading prevents startup blocking while ensuring security is available

import threading

_sandbox_lock = threading.Lock()
_sandbox_instance = None


def get_secure_sandbox() -> Optional[SecureSandboxExecutor]:
    """Get or create the global secure sandbox instance with thread-safe lazy initialization"""
    global _sandbox_instance

    if _sandbox_instance is not None:
        return _sandbox_instance

    with _sandbox_lock:
        if _sandbox_instance is None:
            try:
                logger.info(
                    "Initializing secure sandbox for command execution security"
                ),
                _sandbox_instance = SecureSandboxExecutor()
                logger.info("Secure sandbox initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize secure sandbox: %s", e)
                logger.warning(
                    "Command execution will proceed without sandboxing - SECURITY RISK"
                ),
                _sandbox_instance = None

        return _sandbox_instance


# Maintain backward compatibility
secure_sandbox = None  # Will be initialized on first access via get_secure_sandbox()


async def execute_in_sandbox(
    command: Union[str, List[str]],
    security_level: str = "high",
    timeout: int = 300,
    **kwargs,
) -> SandboxResult:
    """
    Convenience function to execute a command in the sandbox.

    Args:
        command: Command to execute
        security_level: Security level (low, medium, high)
        timeout: Execution timeout in seconds
        **kwargs: Additional configuration options

    Returns:
        SandboxResult with execution details
    """
    sandbox = get_secure_sandbox()
    if sandbox is None:
        # Fallback error result when sandbox unavailable
        return SandboxResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="Secure sandbox unavailable - command execution blocked for security",
            execution_time=0,
            container_id="unavailable",
            security_events=[
                {
                    "type": "sandbox_unavailable",
                    "command": str(command),
                    "reason": "Failed to initialize secure sandbox",
                    "timestamp": time.time(),
                }
            ],
            resource_usage={},
            metadata={"error": "sandbox_unavailable"},
        )

    config = SandboxConfig(
        security_level=SandboxSecurityLevel(security_level), timeout=timeout, **kwargs
    )

    return await sandbox.execute_command(command, config)
