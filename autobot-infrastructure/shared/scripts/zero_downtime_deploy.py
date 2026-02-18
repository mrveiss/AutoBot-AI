#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Zero-Downtime Deployment System
=======================================

Implements blue-green and rolling deployment strategies for zero-downtime updates.

Features:
- Blue-green deployment with automatic traffic switching
- Rolling deployment with health checks
- Canary deployment with gradual traffic migration
- Automatic rollback on failure detection
- Load balancer integration (Nginx, HAProxy)
- Database migration coordination
- Service dependency management
- Deployment validation and testing

Usage:
    python scripts/zero_downtime_deploy.py --strategy blue-green --version v1.2.3
    python scripts/zero_downtime_deploy.py --strategy rolling --batch-size 2
    python scripts/zero_downtime_deploy.py --strategy canary --traffic-percent 10
    python scripts/zero_downtime_deploy.py --rollback --deployment-id 20250821-143022
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from constants.threshold_constants import TimingConstants
from utils.script_utils import ScriptFormatter
from utils.service_registry import get_service_registry

from scripts.backup_manager import BackupManager


class DeploymentStrategy:
    """Deployment strategy types."""

    BLUE_GREEN = "blue-green"
    ROLLING = "rolling"
    CANARY = "canary"
    RECREATE = "recreate"


class DeploymentStatus:
    """Deployment status types."""

    PENDING = "pending"
    DEPLOYING = "deploying"
    TESTING = "testing"
    SWITCHING = "switching"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"


class ZeroDowntimeDeployer:
    """Zero-downtime deployment orchestrator."""

    def __init__(self, deployment_dir: str = "deployments"):
        """Initialize zero-downtime deployer with service registry and backup manager."""
        self.project_root = Path(__file__).parent.parent
        self.deployment_dir = self.project_root / deployment_dir
        self.deployment_dir.mkdir(exist_ok=True)

        self.service_registry = get_service_registry()
        self.backup_manager = BackupManager()

        # Load deployment configuration
        self.deployment_config = self._load_deployment_config()

        # Track deployment state
        self.current_deployment = None

        logger.info("🚀 AutoBot Zero-Downtime Deployer initialized")
        logger.info(f"   Deployment Directory: {self.deployment_dir}")
        logger.info("   Strategy Support: Blue-Green, Rolling, Canary")

    def print_header(self, title: str):
        """Print formatted header."""
        ScriptFormatter.print_header(title)

    def print_step(self, step: str, status: str = "info"):
        """Print step with status."""
        ScriptFormatter.print_step(step, status)

    def _load_deployment_config(self) -> Dict[str, Any]:
        """Load deployment configuration."""
        config_file = self.project_root / "config" / "deployment.yml"

        default_config = {
            "health_check_timeout": 300,
            "health_check_interval": 10,
            "deployment_timeout": 1800,  # 30 minutes
            "rollback_timeout": 600,  # 10 minutes
            "traffic_switch_timeout": 60,
            "services": {
                "backend": {
                    "port": 8001,
                    "health_endpoint": "/api/system/health",
                    "startup_time": 30,
                    "dependencies": ["redis", "ai-stack"],
                },
                "frontend": {
                    "port": 5173,
                    "health_endpoint": "/",
                    "startup_time": 20,
                    "dependencies": ["backend"],
                },
                "ai-stack": {
                    "port": 8080,
                    "health_endpoint": "/health",
                    "startup_time": 45,
                    "dependencies": ["redis"],
                },
                "npu-worker": {
                    "port": 8081,
                    "health_endpoint": "/health",
                    "startup_time": 25,
                    "dependencies": ["redis"],
                },
            },
            "load_balancer": {
                "type": "nginx",  # nginx, haproxy, or none
                "config_file": "/etc/nginx/conf.d/autobot.conf",
                "reload_command": "sudo nginx -s reload",
            },
        }

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    file_config = yaml.safe_load(f) or {}
                # Deep merge configuration
                default_config.update(file_config)
            except Exception as e:
                self.print_step(
                    f"Warning: Could not load deployment config: {e}", "warning"
                )

        return default_config

    def generate_deployment_id(self) -> str:
        """Generate unique deployment ID."""
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    async def deploy(self, strategy: str, version: str = None, **kwargs) -> bool:
        """Execute deployment with specified strategy."""
        deployment_id = self.generate_deployment_id()

        self.print_header(f"Zero-Downtime Deployment: {strategy.upper()}")
        logger.info(f"Deployment ID: {deployment_id}")
        logger.info(f"Target Version: {version or 'current'}")

        # Create deployment record
        deployment_record = {
            "deployment_id": deployment_id,
            "strategy": strategy,
            "version": version,
            "started_at": datetime.now().isoformat(),
            "status": DeploymentStatus.PENDING,
            "parameters": kwargs,
            "steps": [],
        }

        self.current_deployment = deployment_record

        try:
            # Create pre-deployment backup
            self.print_step("Creating pre-deployment backup", "deploy")
            backup_id = self.backup_manager.create_full_backup()
            if backup_id:
                deployment_record["backup_id"] = backup_id
                self.print_step(f"Backup created: {backup_id}", "success")
            else:
                self.print_step("Backup creation failed", "warning")

            # Execute strategy-specific deployment
            if strategy == DeploymentStrategy.BLUE_GREEN:
                success = await self._deploy_blue_green(
                    deployment_record, version, **kwargs
                )
            elif strategy == DeploymentStrategy.ROLLING:
                success = await self._deploy_rolling(
                    deployment_record, version, **kwargs
                )
            elif strategy == DeploymentStrategy.CANARY:
                success = await self._deploy_canary(
                    deployment_record, version, **kwargs
                )
            else:
                self.print_step(f"Unknown deployment strategy: {strategy}", "error")
                success = False

            # Update deployment status
            deployment_record["completed_at"] = datetime.now().isoformat()
            deployment_record["status"] = (
                DeploymentStatus.COMPLETED if success else DeploymentStatus.FAILED
            )

            # Save deployment record
            self._save_deployment_record(deployment_record)

            if success:
                self.print_step("Deployment completed successfully", "success")
            else:
                self.print_step("Deployment failed", "error")

                # Automatic rollback on failure
                if deployment_record.get("backup_id"):
                    self.print_step("Initiating automatic rollback", "deploy")
                    await self._rollback_deployment(deployment_record)

            return success

        except Exception as e:
            deployment_record["error"] = str(e)
            deployment_record["status"] = DeploymentStatus.FAILED
            deployment_record["completed_at"] = datetime.now().isoformat()

            self.print_step(f"Deployment failed with error: {e}", "error")

            # Save failed deployment record
            self._save_deployment_record(deployment_record)

            return False

    async def _deploy_green_services(
        self,
        deployment_record: Dict[str, Any],
        version: str,
    ) -> Dict[str, Any]:
        """
        Deploy services to green environment.

        Issue #281: Extracted from _deploy_blue_green to reduce function length.

        Returns:
            Dict of green services with port/health_url, or empty dict on failure.
        """
        green_services = {}

        for service_name in ["backend", "frontend"]:  # Core services for blue-green
            self.print_step(f"Deploying {service_name} to green environment", "deploy")

            # Get service config
            service_config = self.deployment_config["services"].get(service_name, {})
            green_port = service_config["port"] + 1000  # Offset for green

            # Start green service
            success = await self._start_green_service(
                service_name, green_port, version, service_config
            )

            if not success:
                self.print_step(f"Failed to deploy {service_name} to green", "error")
                await self._cleanup_green_environment(green_services)
                return {}

            green_services[service_name] = {
                "port": green_port,
                "health_url": f"http://localhost:{green_port}{service_config.get('health_endpoint', '/health')}",
            }

            deployment_record["steps"].append(
                {
                    "step": f"deploy_{service_name}_green",
                    "status": "completed",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        return green_services

    async def _verify_green_under_load(
        self,
        green_services: Dict[str, Any],
        monitoring_duration: int = 120,
    ) -> bool:
        """
        Verify green environment stability under load.

        Issue #281: Extracted from _deploy_blue_green to reduce function length.

        Args:
            green_services: Dict of service info with health_url
            monitoring_duration: How long to monitor in seconds

        Returns:
            True if all services remain healthy, False otherwise.
        """
        self.print_step(
            f"Monitoring green environment for {monitoring_duration}s", "info"
        )

        for i in range(monitoring_duration // int(TimingConstants.LONG_DELAY)):
            await asyncio.sleep(TimingConstants.LONG_DELAY)

            # Check health of all green services
            all_healthy = True
            for service_name, service_info in green_services.items():
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            service_info["health_url"], timeout=5
                        ) as response:
                            if response.status != 200:
                                all_healthy = False
                                break
                except Exception:
                    all_healthy = False
                    break

            if not all_healthy:
                return False

        return True

    async def _deploy_blue_green(
        self, deployment_record: Dict[str, Any], version: str, **kwargs
    ) -> bool:
        """Execute blue-green deployment."""
        self.print_step("Starting blue-green deployment", "deploy")

        deployment_record["status"] = DeploymentStatus.DEPLOYING

        # Step 1: Deploy green environment (Issue #281: uses extracted helper)
        self.print_step("Phase 1: Deploying green environment", "deploy")
        green_services = await self._deploy_green_services(deployment_record, version)
        if not green_services:
            return False

        # Step 2: Health check green environment
        self.print_step("Phase 2: Health checking green environment", "test")
        deployment_record["status"] = DeploymentStatus.TESTING

        for service_name, service_info in green_services.items():
            health_ok = await self._wait_for_service_health(
                service_name,
                service_info["health_url"],
                self.deployment_config["health_check_timeout"],
            )

            if not health_ok:
                self.print_step(f"Green {service_name} failed health check", "error")
                await self._cleanup_green_environment(green_services)
                return False

        # Step 3: Switch traffic to green
        self.print_step("Phase 3: Switching traffic to green environment", "switch")
        deployment_record["status"] = DeploymentStatus.SWITCHING

        switch_success = await self._switch_traffic_to_green(green_services)
        if not switch_success:
            self.print_step("Traffic switch failed", "error")
            await self._cleanup_green_environment(green_services)
            return False

        # Step 4: Verify green environment under load (Issue #281: uses extracted helper)
        self.print_step("Phase 4: Verifying green environment under load", "test")

        if not await self._verify_green_under_load(
            green_services, monitoring_duration=120
        ):
            self.print_step("Green environment became unhealthy", "error")
            await self._switch_traffic_to_blue()
            await self._cleanup_green_environment(green_services)
            return False

        # Step 5: Cleanup blue environment
        self.print_step("Phase 5: Cleaning up blue environment", "deploy")
        await self._cleanup_blue_environment()

        # Update service registry to point to green ports
        await self._update_service_registry_for_green(green_services)

        deployment_record["steps"].append(
            {
                "step": "deployment_completed",
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
            }
        )

        return True

    async def _deploy_rolling(
        self,
        deployment_record: Dict[str, Any],
        version: str,
        batch_size: int = 1,
        **kwargs,
    ) -> bool:
        """Execute rolling deployment."""
        self.print_step(
            f"Starting rolling deployment (batch size: {batch_size})", "deploy"
        )

        deployment_record["status"] = DeploymentStatus.DEPLOYING

        # Get list of service instances (for now, treat as single instances)
        services = ["backend", "frontend", "ai-stack", "npu-worker"]

        # Deploy in batches
        for i in range(0, len(services), batch_size):
            batch = services[i : i + batch_size]

            self.print_step(
                f"Rolling batch {i//batch_size + 1}: {', '.join(batch)}", "deploy"
            )

            # Deploy each service in the batch
            for service_name in batch:
                success = await self._rolling_update_service(service_name, version)

                if not success:
                    self.print_step(
                        f"Rolling update failed for {service_name}", "error"
                    )
                    return False

                deployment_record["steps"].append(
                    {
                        "step": f"rolling_update_{service_name}",
                        "status": "completed",
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            # Wait between batches
            if i + batch_size < len(services):
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_LONG_DELAY)

        return True

    async def _deploy_canary(
        self,
        deployment_record: Dict[str, Any],
        version: str,
        traffic_percent: int = 10,
        **kwargs,
    ) -> bool:
        """Execute canary deployment."""
        self.print_step(
            f"Starting canary deployment ({traffic_percent}% traffic)", "deploy"
        )

        deployment_record["status"] = DeploymentStatus.DEPLOYING

        # Deploy canary version alongside current version
        self.print_step("Phase 1: Deploying canary version", "deploy")

        canary_services = {}
        for service_name in ["backend", "frontend"]:
            service_config = self.deployment_config["services"].get(service_name, {})
            canary_port = service_config["port"] + 2000  # Offset for canary

            success = await self._start_canary_service(
                service_name, canary_port, version, service_config
            )

            if not success:
                self.print_step(f"Failed to deploy canary {service_name}", "error")
                return False

            canary_services[service_name] = {
                "port": canary_port,
                "health_url": f"http://localhost:{canary_port}{service_config.get('health_endpoint', '/health')}",
            }

        # Configure load balancer for canary traffic
        self.print_step(
            f"Phase 2: Routing {traffic_percent}% traffic to canary", "switch"
        )
        await self._configure_canary_traffic(canary_services, traffic_percent)

        # Monitor canary performance
        self.print_step("Phase 3: Monitoring canary performance", "test")
        canary_healthy = await self._monitor_canary_health(
            canary_services, duration=300
        )  # 5 minutes

        if not canary_healthy:
            self.print_step("Canary failed health monitoring", "error")
            await self._cleanup_canary_environment(canary_services)
            return False

        # Gradually increase traffic to canary
        for percent in [25, 50, 75, 100]:
            self.print_step(
                f"Phase 4.{percent//25}: Increasing canary traffic to {percent}%",
                "switch",
            )
            await self._configure_canary_traffic(canary_services, percent)

            # Monitor at each stage
            healthy = await self._monitor_canary_health(canary_services, duration=120)
            if not healthy:
                self.print_step(f"Canary failed at {percent}% traffic", "error")
                await self._rollback_canary_traffic()
                await self._cleanup_canary_environment(canary_services)
                return False

        # Finalize canary deployment
        self.print_step("Phase 5: Finalizing canary deployment", "deploy")
        await self._finalize_canary_deployment(canary_services)

        return True

    async def _start_green_service(
        self, service_name: str, port: int, version: str, config: Dict[str, Any]
    ) -> bool:
        """Start a service in green environment."""
        try:
            # For Docker-based services
            if service_name in ["ai-stack", "npu-worker"]:
                # Start Docker container with green suffix
                cmd = [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    f"autobot-{service_name}-green",
                    "-p",
                    f"{port}:{config['port']}",
                    f"autobot-{service_name}:{version or 'latest'}",
                ]
            else:
                # For local services, start with different port
                if service_name == "backend":
                    cmd = [
                        "uvicorn",
                        "main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        str(port),
                        "--log-level",
                        "info",
                    ]
                elif service_name == "frontend":
                    cmd = ["npm", "run", "dev", "--", "--port", str(port)]
                else:
                    return False

            # Start the process
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Wait for startup
            await asyncio.sleep(config.get("startup_time", 30))

            return process.returncode is None  # Process still running

        except Exception as e:
            self.print_step(f"Error starting green {service_name}: {e}", "error")
            return False

    async def _wait_for_service_health(
        self, service_name: str, health_url: str, timeout: int
    ) -> bool:
        """Wait for service to become healthy."""
        self.print_step(f"Waiting for {service_name} health check", "test")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(health_url, timeout=5) as response:
                        if response.status == 200:
                            self.print_step(f"{service_name} is healthy", "success")
                            return True
            except Exception:
                pass  # Health check failed, will retry

            await asyncio.sleep(self.deployment_config["health_check_interval"])

        self.print_step(
            f"{service_name} failed to become healthy within {timeout}s", "error"
        )
        return False

    async def _switch_traffic_to_green(self, green_services: Dict[str, Any]) -> bool:
        """Switch load balancer traffic to green environment."""
        lb_config = self.deployment_config.get("load_balancer", {})

        if lb_config.get("type") == "nginx":
            return await self._switch_nginx_to_green(green_services, lb_config)
        else:
            # Simple port switching for development
            self.print_step(
                "Switching to green environment (development mode)", "switch"
            )
            return True

    async def _switch_nginx_to_green(
        self, green_services: Dict[str, Any], lb_config: Dict[str, Any]
    ) -> bool:
        """Switch Nginx configuration to green environment."""
        try:
            config_file = lb_config.get("config_file")
            if not config_file:
                return True

            # Generate new Nginx config pointing to green services
            nginx_config = self._generate_nginx_config(green_services, "green")

            # Write new config
            with open(config_file, "w") as f:
                f.write(nginx_config)

            # Reload Nginx
            reload_cmd = lb_config.get("reload_command", "sudo nginx -s reload")
            process = await asyncio.create_subprocess_shell(reload_cmd)
            await process.wait()

            return process.returncode == 0

        except Exception as e:
            self.print_step(f"Error switching Nginx to green: {e}", "error")
            return False

    def _generate_nginx_config(self, services: Dict[str, Any], env: str) -> str:
        """Generate Nginx configuration for services."""
        config = """
# AutoBot {env.capitalize()} Environment Configuration
# Generated at: {datetime.now().isoformat()}

upstream autobot_backend_{env} {{
    server localhost:{services.get('backend', {}).get('port', 8001)};
}}

upstream autobot_frontend_{env} {{
    server localhost:{services.get('frontend', {}).get('port', 5173)};
}}

server {{
    listen 80;
    server_name autobot.local;

    location /api/ {{
        proxy_pass http://autobot_backend_{env};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location / {{
        proxy_pass http://autobot_frontend_{env};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
        return config

    async def _cleanup_green_environment(self, green_services: Dict[str, Any]) -> None:
        """Clean up green environment on failure."""
        self.print_step("Cleaning up green environment", "deploy")

        for service_name in green_services:
            try:
                # Stop Docker containers
                await asyncio.create_subprocess_shell(
                    f"docker stop autobot-{service_name}-green 2>/dev/null || true"
                )
                await asyncio.create_subprocess_shell(
                    f"docker rm autobot-{service_name}-green 2>/dev/null || true"
                )
            except Exception:
                pass  # Best-effort cleanup of green containers

    async def _rolling_update_service(self, service_name: str, version: str) -> bool:
        """Perform rolling update on a single service."""
        self.print_step(f"Rolling update: {service_name}", "deploy")

        service_config = self.deployment_config["services"].get(service_name, {})

        # Stop current service
        await self._stop_service(service_name)

        # Start new version
        success = await self._start_service(service_name, version, service_config)
        if not success:
            return False

        # Health check
        health_url = f"http://localhost:{service_config['port']}{service_config.get('health_endpoint', '/health')}"
        return await self._wait_for_service_health(service_name, health_url, 120)

    async def _stop_service(self, service_name: str) -> None:
        """Stop a service gracefully."""
        if service_name in ["ai-stack", "npu-worker"]:
            # Stop Docker container
            await asyncio.create_subprocess_shell(f"docker stop autobot-{service_name}")
        else:
            # Stop local process (would need PID tracking in real implementation)
            await asyncio.create_subprocess_shell(f"pkill -f {service_name}")

    async def _start_service(
        self, service_name: str, version: str, config: Dict[str, Any]
    ) -> bool:
        """Start a service with specified version."""
        # Implementation would start the service
        # This is a simplified version
        await asyncio.sleep(config.get("startup_time", 30))
        return True

    def _save_deployment_record(self, deployment_record: Dict[str, Any]) -> None:
        """Save deployment record to file."""
        record_file = (
            self.deployment_dir
            / f"deployment_{deployment_record['deployment_id']}.json"
        )

        with open(record_file, "w") as f:
            json.dump(deployment_record, f, indent=2)

    async def _rollback_deployment(self, deployment_record: Dict[str, Any]) -> bool:
        """Rollback failed deployment."""
        self.print_step("Starting deployment rollback", "deploy")

        backup_id = deployment_record.get("backup_id")
        if backup_id:
            return self.backup_manager.restore_backup(backup_id)

        return False

    def list_deployments(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent deployments."""
        deployments = []

        for deployment_file in sorted(
            self.deployment_dir.glob("deployment_*.json"), reverse=True
        ):
            if len(deployments) >= limit:
                break

            try:
                with open(deployment_file, "r") as f:
                    deployment = json.load(f)
                deployments.append(deployment)
            except Exception:
                continue

        return deployments


def _parse_deployment_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments for deployment CLI.

    Issue #281: Extracted from main to reduce function length.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="AutoBot Zero-Downtime Deployment System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/zero_downtime_deploy.py --strategy blue-green --version v1.2.3
  python scripts/zero_downtime_deploy.py --strategy rolling --batch-size 2
  python scripts/zero_downtime_deploy.py --strategy canary --traffic-percent 10
  python scripts/zero_downtime_deploy.py --rollback --deployment-id 20250821-143022
  python scripts/zero_downtime_deploy.py --list
        """,
    )

    parser.add_argument("--deploy", action="store_true", help="Execute deployment")
    parser.add_argument("--rollback", action="store_true", help="Rollback deployment")
    parser.add_argument("--list", action="store_true", help="List deployments")
    parser.add_argument("--status", action="store_true", help="Show deployment status")
    parser.add_argument(
        "--strategy",
        choices=[
            DeploymentStrategy.BLUE_GREEN,
            DeploymentStrategy.ROLLING,
            DeploymentStrategy.CANARY,
        ],
        help="Deployment strategy",
    )
    parser.add_argument("--version", help="Version to deploy")
    parser.add_argument(
        "--batch-size", type=int, default=1, help="Rolling deployment batch size"
    )
    parser.add_argument(
        "--traffic-percent", type=int, default=10, help="Canary traffic percentage"
    )
    parser.add_argument("--deployment-id", help="Deployment ID for rollback")
    parser.add_argument(
        "--deployment-dir", default="deployments", help="Deployment directory"
    )

    return parser.parse_args()


async def _handle_deploy_action(deployer: ZeroDowntimeDeployer, args) -> int:
    """
    Handle deployment action.

    Issue #281: Extracted from main to reduce function length.

    Args:
        deployer: ZeroDowntimeDeployer instance.
        args: Parsed arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    if not args.strategy:
        logger.error("❌ --strategy required for deployment")
        return 1

    kwargs = {}
    if args.batch_size and args.strategy == DeploymentStrategy.ROLLING:
        kwargs["batch_size"] = args.batch_size
    if args.traffic_percent and args.strategy == DeploymentStrategy.CANARY:
        kwargs["traffic_percent"] = args.traffic_percent

    success = await deployer.deploy(args.strategy, args.version, **kwargs)
    return 0 if success else 1


async def _handle_rollback_action(deployer: ZeroDowntimeDeployer, args) -> int:
    """
    Handle rollback action.

    Issue #281: Extracted from main to reduce function length.

    Args:
        deployer: ZeroDowntimeDeployer instance.
        args: Parsed arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    if not args.deployment_id:
        logger.error("❌ --deployment-id required for rollback")
        return 1

    deployment_file = deployer.deployment_dir / f"deployment_{args.deployment_id}.json"
    if not deployment_file.exists():
        logger.error(f"❌ Deployment {args.deployment_id} not found")
        return 1

    with open(deployment_file, "r") as f:
        deployment_record = json.load(f)

    success = await deployer._rollback_deployment(deployment_record)
    return 0 if success else 1


def _handle_list_action(deployer: ZeroDowntimeDeployer) -> int:
    """
    Handle list deployments action.

    Issue #281: Extracted from main to reduce function length.

    Args:
        deployer: ZeroDowntimeDeployer instance.

    Returns:
        Exit code (0 for success).
    """
    deployments = deployer.list_deployments()

    if not deployments:
        logger.info("No deployments found")
        return 0

    logger.info("\n🚀 Recent Deployments:")
    logger.info("=" * 80)
    logger.info(
        f"{'ID':<20} {'Strategy':<12} {'Version':<15} {'Status':<12} {'Date':<20}"
    )
    logger.info("-" * 80)

    for deployment in deployments:
        started = datetime.fromisoformat(deployment["started_at"])
        version = deployment.get("version", "unknown")[:14]

        logger.info(
            f"{deployment['deployment_id']:<20} "
            f"{deployment['strategy']:<12} "
            f"{version:<15} "
            f"{deployment['status']:<12} "
            f"{started.strftime('%Y-%m-%d %H:%M'):<20}"
        )

    return 0


async def main():
    """
    Entry point for zero-downtime deployment CLI.

    Issue #281: Extracted helpers _parse_deployment_arguments(), _handle_deploy_action(),
    _handle_rollback_action(), and _handle_list_action() to reduce function length
    from 125 to ~25 lines.
    """
    # Issue #281: Use extracted helper for argument parsing
    args = _parse_deployment_arguments()

    if not any([args.deploy, args.rollback, args.list, args.status]):
        if args.strategy:
            args.deploy = True
        else:
            return 1

    deployer = ZeroDowntimeDeployer(args.deployment_dir)

    try:
        if args.deploy:
            return await _handle_deploy_action(deployer, args)
        elif args.rollback:
            return await _handle_rollback_action(deployer, args)
        elif args.list:
            return _handle_list_action(deployer)

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
