# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Orchestrator for Portable AutoBot Services

Enables SLM server to start/stop/migrate AutoBot services across machines.
Integrates with SSOT configuration from .env file.

Related to Issue #728 - Service portability across machines.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models.database import Node, Service, ServiceStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AutoBotServiceType(str, Enum):
    """Known AutoBot service types that can be orchestrated."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    REDIS = "redis"
    NPU_WORKER = "npu-worker"
    AI_STACK = "ai-stack"
    BROWSER = "browser"
    SLM_BACKEND = "slm-backend"
    SLM_AGENT = "slm-agent"


@dataclass
class ServiceDefinition:
    """Definition of an AutoBot service with start/stop commands."""

    name: str
    service_type: AutoBotServiceType
    default_host_env: str  # Environment variable name for default host
    default_port_env: str  # Environment variable name for default port
    default_host: str  # Fallback host if env not set
    default_port: int  # Fallback port if env not set
    systemd_service: Optional[str] = None  # Systemd service name if applicable
    start_command: Optional[str] = None  # Custom start command
    stop_command: Optional[str] = None  # Custom stop command
    health_check_path: Optional[str] = None  # HTTP health check path
    health_check_type: str = "http"  # http, redis, ssh
    requires_sudo: bool = True
    working_dir: Optional[str] = None
    description: str = ""
    dependencies: List[str] = field(default_factory=list)


# Service definitions registry (Issue #665)
# Module-level constant to avoid long method definition
_SERVICE_DEFINITIONS = {
    # Backend API Server (runs on main WSL machine)
    "backend": ServiceDefinition(
        name="backend",
        service_type=AutoBotServiceType.BACKEND,
        default_host_env="AUTOBOT_BACKEND_HOST",
        default_port_env="AUTOBOT_BACKEND_PORT",
        default_host="172.16.168.20",  # Main WSL backend host
        default_port=8443,  # Issue #858/#861: HTTPS port
        start_command=(
            "cd /opt/autobot/autobot-backend && "
            "source venv/bin/activate && "
            "nohup python backend/main.py > logs/backend.log 2>&1 &"
        ),
        stop_command="pkill -f 'python.*backend/main.py'",
        health_check_path="/api/health",
        health_check_type="https",  # Backend requires HTTPS on port 8443 (#915)
        requires_sudo=False,
        working_dir="/opt/autobot/autobot-backend",
        description="FastAPI backend API server",
    ),
    # Frontend (Vue.js on frontend VM)
    "frontend": ServiceDefinition(
        name="frontend",
        service_type=AutoBotServiceType.FRONTEND,
        default_host_env="AUTOBOT_FRONTEND_HOST",
        default_port_env="AUTOBOT_FRONTEND_PORT",
        default_host="172.16.168.21",
        default_port=5173,
        systemd_service="nginx",  # Production uses nginx
        start_command=(
            "cd /opt/autobot/autobot-slm-frontend && "
            "nohup npm run dev -- --host 0.0.0.0 --port 5173 > /tmp/vite.log 2>&1 &"
        ),
        stop_command="pkill -f 'npm.*dev' || pkill -f 'vite.*5173'",
        health_check_path="/",
        health_check_type="http",
        requires_sudo=False,
        working_dir="/opt/autobot/autobot-slm-frontend",
        description="Vue.js frontend development server",
    ),
    # Redis Stack (database VM)
    "redis": ServiceDefinition(
        name="redis",
        service_type=AutoBotServiceType.REDIS,
        default_host_env="AUTOBOT_REDIS_HOST",
        default_port_env="AUTOBOT_REDIS_PORT",
        default_host="172.16.168.23",
        default_port=6379,
        systemd_service="redis-stack-server",
        health_check_type="redis",
        requires_sudo=True,
        description="Redis Stack data layer",
    ),
    # NPU Worker (hardware AI acceleration)
    "npu-worker": ServiceDefinition(
        name="npu-worker",
        service_type=AutoBotServiceType.NPU_WORKER,
        default_host_env="AUTOBOT_NPU_WORKER_HOST",
        default_port_env="AUTOBOT_NPU_WORKER_PORT",
        default_host="172.16.168.22",
        default_port=8081,
        systemd_service="autobot-npu-worker",
        start_command=(
            "cd /opt/autobot/autobot-npu-worker && "
            "nohup python -m npu_worker.service --host 0.0.0.0 --port 8081 "
            "> logs/npu-worker.log 2>&1 &"
        ),
        stop_command="pkill -f 'npu.*worker'",
        health_check_path="/health",
        health_check_type="http",
        requires_sudo=False,
        description="NPU hardware AI acceleration worker",
    ),
    # AI Stack (Ollama runs on main/code-source machine)
    "ai-stack": ServiceDefinition(
        name="ai-stack",
        service_type=AutoBotServiceType.AI_STACK,
        default_host_env="AUTOBOT_AI_STACK_HOST",
        default_port_env="AUTOBOT_AI_STACK_PORT",
        default_host="172.16.168.20",
        default_port=11434,
        systemd_service="ollama",
        start_command="ollama serve",
        stop_command="pkill -f 'ollama serve'",
        health_check_path="/api/tags",
        health_check_type="http",
        requires_sudo=False,
        description="Ollama AI LLM server",
    ),
    # Browser automation (Playwright)
    "browser": ServiceDefinition(
        name="browser",
        service_type=AutoBotServiceType.BROWSER,
        default_host_env="AUTOBOT_BROWSER_SERVICE_HOST",
        default_port_env="AUTOBOT_BROWSER_SERVICE_PORT",
        default_host="172.16.168.25",
        default_port=3000,
        start_command=(
            "cd /opt/autobot/autobot-browser-worker && "
            "nohup node playwright-server.js > /tmp/browser.log 2>&1 &"
        ),
        stop_command="pkill -f 'playwright-server'",
        health_check_path="/",
        health_check_type="http",
        requires_sudo=False,
        working_dir="/opt/autobot/autobot-browser-worker",
        description="Playwright browser automation service",
    ),
    # SLM Backend (this server)
    "slm-backend": ServiceDefinition(
        name="slm-backend",
        service_type=AutoBotServiceType.SLM_BACKEND,
        default_host_env="SLM_HOST",
        default_port_env="SLM_PORT",
        default_host="127.0.0.1",  # Self-check: uvicorn binds localhost-only
        default_port=8000,
        systemd_service="slm-backend",
        health_check_path="/api/health",
        health_check_type="http",
        requires_sudo=True,
        description="SLM fleet management backend",
    ),
    # SLM Agent (runs on each managed node)
    "slm-agent": ServiceDefinition(
        name="slm-agent",
        service_type=AutoBotServiceType.SLM_AGENT,
        default_host_env="",
        default_port_env="",
        default_host="",
        default_port=0,
        systemd_service="autobot-agent",
        health_check_type="ssh",
        requires_sudo=True,
        description="SLM node agent for heartbeats",
    ),
}


class ServiceRegistry:
    """
    Registry of known AutoBot services with their configurations.

    Sources configuration from environment variables (SSOT from .env).
    """

    def __init__(self):
        self._load_env()
        self._services = self._build_service_registry()

    def _load_env(self) -> None:
        """Load environment variables from .env file."""
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key not in os.environ:
                            os.environ[key] = value

    def _build_service_registry(self) -> Dict[str, ServiceDefinition]:
        """Build the service registry with SSOT configuration.

        Service definitions are in _SERVICE_DEFINITIONS module constant (Issue #665).
        """
        return _SERVICE_DEFINITIONS.copy()

    def get_service(self, name: str) -> Optional[ServiceDefinition]:
        """Get service definition by name."""
        return self._services.get(name)

    def list_services(self) -> List[ServiceDefinition]:
        """List all registered services."""
        return list(self._services.values())

    def get_service_host(self, name: str) -> str:
        """Get the current host for a service from environment."""
        service = self._services.get(name)
        if not service:
            return ""
        return os.environ.get(service.default_host_env, service.default_host)

    def get_service_port(self, name: str) -> int:
        """Get the current port for a service from environment."""
        service = self._services.get(name)
        if not service:
            return 0
        port_str = os.environ.get(service.default_port_env, str(service.default_port))
        try:
            return int(port_str)
        except ValueError:
            return service.default_port


class ServiceOrchestrator:
    """
    Orchestrates AutoBot services across multiple machines.

    Provides portable service control allowing services to be
    started/stopped/migrated on any enrolled node.
    """

    # Limit concurrent SSH connections to prevent pool exhaustion (#788)
    _SSH_MAX_CONCURRENT = 10

    def __init__(self):
        self.registry = ServiceRegistry()
        self.ssh_key = Path.home() / ".ssh" / "id_rsa"
        self.ssh_user = "autobot"
        self._ssh_semaphore = asyncio.Semaphore(self._SSH_MAX_CONCURRENT)

    async def _resolve_target_node(
        self, db: AsyncSession, service_name: str, node_id: Optional[str]
    ) -> Tuple[Optional[str], Optional[Any], Optional[str]]:
        """Resolve target host and node for a service action.

        Helper for start_service (#825).

        Returns:
            (target_host, node, error_message) - error_message is None on success
        """
        if node_id:
            node = await self._get_node(db, node_id)
            if not node:
                return None, None, f"Node not found: {node_id}"
            return node.ip_address, node, None

        target_host = self.registry.get_service_host(service_name)
        if not target_host:
            return None, None, f"No target host for service: {service_name}"
        node = await self._find_node_by_ip(db, target_host)
        return target_host, node, None

    async def start_service(
        self,
        db: AsyncSession,
        service_name: str,
        node_id: Optional[str] = None,
        force: bool = False,
    ) -> Tuple[bool, str]:
        """
        Start a service on a node.

        Args:
            db: Database session
            service_name: Name of the service to start
            node_id: Target node ID (uses default host if not specified)
            force: Force start even if already running

        Returns:
            (success, message)
        """
        service_def = self.registry.get_service(service_name)
        if not service_def:
            return False, f"Unknown service: {service_name}"

        target_host, node, error = await self._resolve_target_node(
            db, service_name, node_id
        )
        if error:
            return False, error

        # Check if already running (unless force)
        if not force:
            is_running = await self._check_service_health(
                target_host,
                self.registry.get_service_port(service_name),
                service_def.health_check_path,
                service_def.health_check_type,
            )
            if is_running:
                return (
                    True,
                    f"Service {service_name} is already running on {target_host}",
                )

        # Start the service
        if service_def.systemd_service:
            success, message = await self._systemctl_action(
                target_host,
                service_def.systemd_service,
                "start",
                service_def.requires_sudo,
            )
        elif service_def.start_command:
            success, message = await self._run_ssh_command(
                target_host, service_def.start_command, service_def.requires_sudo
            )
        else:
            return False, f"No start method defined for service: {service_name}"

        # Update service record if we have a node
        if success and node:
            await self._update_service_record(
                db, node.node_id, service_name, ServiceStatus.RUNNING.value
            )

        return success, message

    async def stop_service(
        self,
        db: AsyncSession,
        service_name: str,
        node_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Stop a service on a node.

        Args:
            db: Database session
            service_name: Name of the service to stop
            node_id: Target node ID (uses default host if not specified)

        Returns:
            (success, message)
        """
        service_def = self.registry.get_service(service_name)
        if not service_def:
            return False, f"Unknown service: {service_name}"

        # Determine target node
        if node_id:
            node = await self._get_node(db, node_id)
            if not node:
                return False, f"Node not found: {node_id}"
            target_host = node.ip_address
        else:
            target_host = self.registry.get_service_host(service_name)
            node = await self._find_node_by_ip(db, target_host)

        if not target_host:
            return False, f"No target host for service: {service_name}"

        # Stop the service
        if service_def.systemd_service:
            success, message = await self._systemctl_action(
                target_host,
                service_def.systemd_service,
                "stop",
                service_def.requires_sudo,
            )
        elif service_def.stop_command:
            success, message = await self._run_ssh_command(
                target_host, service_def.stop_command, service_def.requires_sudo
            )
        else:
            return False, f"No stop method defined for service: {service_name}"

        # Update service record if we have a node
        if success and node:
            await self._update_service_record(
                db, node.node_id, service_name, ServiceStatus.STOPPED.value
            )

        return success, message

    async def restart_service(
        self,
        db: AsyncSession,
        service_name: str,
        node_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Restart a service on a node.

        Args:
            db: Database session
            service_name: Name of the service to restart
            node_id: Target node ID (uses default host if not specified)

        Returns:
            (success, message)
        """
        service_def = self.registry.get_service(service_name)
        if not service_def:
            return False, f"Unknown service: {service_name}"

        # Determine target node
        if node_id:
            node = await self._get_node(db, node_id)
            if not node:
                return False, f"Node not found: {node_id}"
            target_host = node.ip_address
        else:
            target_host = self.registry.get_service_host(service_name)
            node = await self._find_node_by_ip(db, target_host)

        if not target_host:
            return False, f"No target host for service: {service_name}"

        # Restart the service
        if service_def.systemd_service:
            success, message = await self._systemctl_action(
                target_host,
                service_def.systemd_service,
                "restart",
                service_def.requires_sudo,
            )
        else:
            # Stop then start
            await self.stop_service(db, service_name, node_id)
            await asyncio.sleep(1)
            success, message = await self.start_service(
                db, service_name, node_id, force=True
            )

        # Update service record if we have a node
        if success and node:
            await self._update_service_record(
                db, node.node_id, service_name, ServiceStatus.RUNNING.value
            )

        return success, message

    async def migrate_service(
        self,
        db: AsyncSession,
        service_name: str,
        source_node_id: str,
        target_node_id: str,
    ) -> Tuple[bool, str]:
        """
        Migrate a service from one node to another.

        This stops the service on the source node and starts it on the target.

        Args:
            db: Database session
            service_name: Name of the service to migrate
            source_node_id: Current node running the service
            target_node_id: Target node to run the service

        Returns:
            (success, message)
        """
        service_def = self.registry.get_service(service_name)
        if not service_def:
            return False, f"Unknown service: {service_name}"

        source_node = await self._get_node(db, source_node_id)
        target_node = await self._get_node(db, target_node_id)

        if not source_node:
            return False, f"Source node not found: {source_node_id}"
        if not target_node:
            return False, f"Target node not found: {target_node_id}"

        logger.info(
            "Migrating service %s from %s to %s",
            service_name,
            source_node.hostname,
            target_node.hostname,
        )

        # Stop on source
        stop_success, stop_msg = await self.stop_service(
            db, service_name, source_node_id
        )
        if not stop_success:
            logger.warning(
                "Failed to stop on source (may not be running): %s", stop_msg
            )

        # Start on target
        start_success, start_msg = await self.start_service(
            db, service_name, target_node_id, force=True
        )

        if start_success:
            return True, (
                f"Service {service_name} migrated from "
                f"{source_node.hostname} to {target_node.hostname}"
            )
        else:
            # Try to restart on source if target failed
            logger.error("Migration failed, attempting to restart on source")
            await self.start_service(db, service_name, source_node_id, force=True)
            return False, f"Migration failed: {start_msg}"

    async def get_fleet_status(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Get status of all AutoBot services across the fleet.

        Returns:
            Dict with service statuses and health information
        """
        status = {
            "timestamp": datetime.utcnow().isoformat(),
            "services": {},
            "healthy_count": 0,
            "unhealthy_count": 0,
        }

        for service_def in self.registry.list_services():
            host = self.registry.get_service_host(service_def.name)
            port = self.registry.get_service_port(service_def.name)

            if not host:
                continue

            is_healthy = await self._check_service_health(
                host,
                port,
                service_def.health_check_path,
                service_def.health_check_type,
            )

            # Find node for this host
            node = await self._find_node_by_ip(db, host)

            status["services"][service_def.name] = {
                "host": host,
                "port": port,
                "healthy": is_healthy,
                "node_id": node.node_id if node else None,
                "node_hostname": node.hostname if node else None,
                "description": service_def.description,
                "systemd_service": service_def.systemd_service,
            }

            if is_healthy:
                status["healthy_count"] += 1
            else:
                status["unhealthy_count"] += 1

        return status

    async def start_all_services(
        self, db: AsyncSession, exclude: Optional[List[str]] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Start all AutoBot services in dependency order.

        Args:
            db: Database session
            exclude: List of service names to skip

        Returns:
            Dict of service name -> (success, message)
        """
        exclude = exclude or []
        results = {}

        # Start order based on dependencies
        start_order = [
            "redis",  # Data layer first
            "backend",  # Backend needs Redis
            "frontend",  # Frontend needs Backend
            "ai-stack",  # AI services
            "npu-worker",  # NPU acceleration
            "browser",  # Browser automation
        ]

        for service_name in start_order:
            if service_name in exclude:
                results[service_name] = (True, "Skipped (excluded)")
                continue

            success, message = await self.start_service(db, service_name)
            results[service_name] = (success, message)

            # Wait between services
            if success:
                await asyncio.sleep(2)

        return results

    async def stop_all_services(
        self, db: AsyncSession, exclude: Optional[List[str]] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Stop all AutoBot services in reverse dependency order.

        Args:
            db: Database session
            exclude: List of service names to skip

        Returns:
            Dict of service name -> (success, message)
        """
        exclude = exclude or []
        results = {}

        # Stop order (reverse of start)
        stop_order = [
            "browser",
            "npu-worker",
            "ai-stack",
            "frontend",
            "backend",
            "redis",  # Data layer last
        ]

        for service_name in stop_order:
            if service_name in exclude:
                results[service_name] = (True, "Skipped (excluded)")
                continue

            success, message = await self.stop_service(db, service_name)
            results[service_name] = (success, message)

        return results

    # =========================================================================
    # Private helper methods
    # =========================================================================

    async def _get_node(self, db: AsyncSession, node_id: str) -> Optional[Node]:
        """Get node by ID."""
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        return result.scalar_one_or_none()

    async def _find_node_by_ip(
        self, db: AsyncSession, ip_address: str
    ) -> Optional[Node]:
        """Find node by IP address."""
        result = await db.execute(select(Node).where(Node.ip_address == ip_address))
        return result.scalar_one_or_none()

    async def _update_service_record(
        self, db: AsyncSession, node_id: str, service_name: str, status: str
    ) -> None:
        """Update or create service record in database."""
        result = await db.execute(
            select(Service).where(
                Service.node_id == node_id,
                Service.service_name == service_name,
            )
        )
        service = result.scalar_one_or_none()

        if service:
            service.status = status
            service.last_checked = datetime.utcnow()
        else:
            service = Service(
                node_id=node_id,
                service_name=service_name,
                status=status,
                last_checked=datetime.utcnow(),
            )
            db.add(service)

        await db.commit()

    async def _run_ssh_command(
        self, host: str, command: str, requires_sudo: bool = False
    ) -> Tuple[bool, str]:
        """Run a command on a remote host via SSH."""
        async with self._ssh_semaphore:
            return await self._execute_ssh(host, command, requires_sudo)

    async def _execute_ssh(
        self, host: str, command: str, requires_sudo: bool = False
    ) -> Tuple[bool, str]:
        """Execute SSH subprocess (#788: split from _run_ssh_command)."""
        ssh_cmd = [
            "/usr/bin/ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "-i",
            str(self.ssh_key),
            f"{self.ssh_user}@{host}",
        ]

        if requires_sudo:
            command = f"sudo -n {command}"

        ssh_cmd.append(command)

        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)

            if process.returncode == 0:
                output = stdout.decode("utf-8", errors="replace")
                return True, output or "Command completed successfully"
            else:
                error = stderr.decode("utf-8", errors="replace")
                return False, f"Command failed: {error[:500]}"

        except asyncio.TimeoutError:
            return False, "SSH command timed out"
        except Exception as e:
            logger.exception("SSH command error: %s", e)
            return False, f"SSH error: {str(e)[:200]}"

    async def _systemctl_action(
        self, host: str, service: str, action: str, requires_sudo: bool = True
    ) -> Tuple[bool, str]:
        """Run a systemctl action on a remote host."""
        if requires_sudo:
            command = f"sudo -n systemctl {action} {service}"
        else:
            command = f"systemctl --user {action} {service}"

        return await self._run_ssh_command(host, command, requires_sudo=False)

    async def _check_service_health(
        self,
        host: str,
        port: int,
        path: Optional[str],
        check_type: str,
    ) -> bool:
        """Check if a service is healthy."""
        try:
            if check_type == "https" and path:
                return await self._check_https_health(host, port, path)
            elif check_type == "http" and path:
                return await self._check_http_health(host, port, path)
            elif check_type == "redis":
                return await self._check_redis_health(host, port)
            elif check_type == "ssh":
                return await self._check_ssh_health(host)
            else:
                # Default to port check
                return await self._check_port_open(host, port)
        except Exception as e:
            logger.debug("Health check failed for %s:%d - %s", host, port, e)
            return False

    async def _check_https_health(self, host: str, port: int, path: str) -> bool:
        """Check HTTPS health endpoint (skips cert verification for self-signed certs)."""
        cmd = ["curl", "-skf", "--max-time", "5", f"https://{host}:{port}{path}"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return process.returncode == 0

    async def _check_http_health(self, host: str, port: int, path: str) -> bool:
        """Check HTTP health endpoint."""
        cmd = ["curl", "-sf", "--max-time", "5", f"http://{host}:{port}{path}"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return process.returncode == 0

    async def _check_redis_health(self, host: str, port: int) -> bool:
        """Check Redis health via PING."""
        password = os.environ.get("AUTOBOT_REDIS_PASSWORD", "")
        cmd = ["redis-cli", "-h", host, "-p", str(port)]
        if password:
            cmd.extend(["-a", password, "--no-auth-warning"])
        cmd.append("ping")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        return b"PONG" in stdout

    async def _check_ssh_health(self, host: str) -> bool:
        """Check if SSH connection is possible."""
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=3",
            "-o",
            "BatchMode=yes",
            "-i",
            str(self.ssh_key),
            f"{self.ssh_user}@{host}",
            "echo ok",
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=5.0)
        return process.returncode == 0

    async def _check_port_open(self, host: str, port: int) -> bool:
        """Check if a port is open."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=3.0,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False


# Singleton instance
service_orchestrator = ServiceOrchestrator()
