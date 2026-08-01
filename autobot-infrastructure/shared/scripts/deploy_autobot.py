#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Deployment Automation Script
====================================

Automates deployment of AutoBot across different deployment modes:
- local: Hybrid local + Docker deployment (default)
- docker_local: Full Docker deployment on single machine
- distributed: Services across multiple machines
- kubernetes: Kubernetes cluster deployment

Usage:
    python scripts/deploy_autobot.py --mode local
    python scripts/deploy_autobot.py --mode docker_local --build
    python scripts/deploy_autobot.py --mode distributed --config config/deployment/production.yml
    python scripts/deploy_autobot.py --mode kubernetes --namespace autobot-prod
"""

import argparse
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# --- Standalone replacements for backend-only modules (#11761) --------------
# `utils/` and `constants/` exist only under autobot-backend/ and are not
# importable from this directory; shared scripts stay standalone (#11759).
# Canonical sources mirrored below:
#   autobot_shared/ssot_constants.py::TimingConstants
#   autobot-backend/utils/service_registry.py (surface used by this script)


class TimingConstants:
    """Standalone copy of the timing values used by this script."""

    MEDIUM_DELAY = 5.0
    LONG_DELAY = 10.0


class DeploymentMode(Enum):
    """Deployment modes (mirrors backend utils/service_registry.py)."""

    LOCAL = "local"
    DOCKER_LOCAL = "docker_local"
    DISTRIBUTED = "distributed"
    KUBERNETES = "kubernetes"
    CLOUD = "cloud"


class ServiceStatus(Enum):
    """Service health status (mirrors backend utils/service_registry.py)."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Service health state."""

    status: ServiceStatus
    last_check: float
    response_time: float = 0.0


# Port env aliases + defaults mirror autobot_shared/ssot_config.py;
# health paths mirror autobot_shared/ssot_constants.py.
_SERVICE_DEFS = {
    "backend": ("AUTOBOT_BACKEND_PORT", 8001, "/api/health"),
    "frontend": ("AUTOBOT_FRONTEND_PORT", 5173, "/"),
    "redis": ("AUTOBOT_REDIS_PORT", 6379, None),
    "ollama": ("AUTOBOT_OLLAMA_PORT", 11434, "/api/tags"),
    "ai-stack": ("AUTOBOT_AI_STACK_PORT", 8080, "/health"),
    "npu-worker": ("AUTOBOT_NPU_WORKER_PORT", 8081, "/health"),
    "playwright-vnc": ("AUTOBOT_BROWSER_SERVICE_PORT", 9001, "/health"),
}


class ServiceRegistry:
    """Env-driven standalone stand-in for the backend ServiceRegistry."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize registry from environment (optional config file ignored)."""
        self.config_file = config_file
        self.deployment_mode = self._detect_deployment_mode()
        self.services: Dict[str, str] = {name: self._build_url(name) for name in _SERVICE_DEFS}

    @staticmethod
    def _detect_deployment_mode() -> DeploymentMode:
        """Detect deployment mode from env, falling back to container heuristic."""
        mode = os.environ.get("AUTOBOT_DEPLOYMENT_MODE", "").lower()
        if mode:
            try:
                return DeploymentMode(mode)
            except ValueError:
                logger.warning("Invalid AUTOBOT_DEPLOYMENT_MODE: %s", mode)
        return DeploymentMode.DOCKER_LOCAL if os.path.exists("/.dockerenv") else DeploymentMode.LOCAL

    @staticmethod
    def _build_url(name: str) -> str:
        """Build a service base URL from environment overrides."""
        host_env = f"AUTOBOT_{name.upper().replace('-', '_')}_HOST"
        host = os.environ.get(host_env, "localhost")
        port_env, default_port, _health = _SERVICE_DEFS[name]
        port = int(os.environ.get(port_env, default_port))
        scheme = "redis" if name == "redis" else "http"
        return f"{scheme}://{host}:{port}"

    def list_services(self) -> List[str]:
        """List registered service names."""
        return list(self.services)

    def get_service_url(self, service_name: str, path: str = "") -> str:
        """Get full URL for a service."""
        if service_name not in self.services:
            raise ValueError(f"Service '{service_name}' not found in registry")
        return f"{self.services[service_name]}{path}"

    @staticmethod
    def _probe(url: str, timeout: float = 5.0) -> bool:
        """Probe a service: TCP connect for redis, HTTP GET otherwise."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "redis":
            try:
                with socket.create_connection((parsed.hostname, parsed.port), timeout=timeout):
                    return True
            except OSError:
                return False
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                return response.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    async def check_service_health(self, service_name: str) -> ServiceHealth:
        """Check health of a single service."""
        _port_env, _default_port, health_path = _SERVICE_DEFS[service_name]
        url = self.get_service_url(service_name, health_path or "")
        start = time.time()
        ok = await asyncio.get_running_loop().run_in_executor(None, self._probe, url)
        return ServiceHealth(
            status=ServiceStatus.HEALTHY if ok else ServiceStatus.UNHEALTHY,
            last_check=time.time(),
            response_time=time.time() - start,
        )

    async def check_all_services_health(self) -> Dict[str, ServiceHealth]:
        """Check health of all registered services."""
        names = self.list_services()
        results = await asyncio.gather(*(self.check_service_health(name) for name in names))
        return dict(zip(names, results))

    def get_deployment_info(self) -> Dict[str, Any]:
        """Get deployment information."""
        return {
            "deployment_mode": self.deployment_mode.value,
            "services_count": len(self.services),
            "services": {name: {"url": url} for name, url in self.services.items()},
        }


_registry: Optional[ServiceRegistry] = None


def get_service_registry(config_file: Optional[str] = None) -> ServiceRegistry:
    """Get the process-wide ServiceRegistry instance."""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry(config_file)
    return _registry


# --- end standalone replacements (#11761) -----------------------------------


class AutoBotDeployer:
    """Handles deployment automation for AutoBot across different modes."""

    def __init__(self, mode: str, config_file: Optional[str] = None, namespace: str = "autobot"):
        """Initialize deployer with mode, config, and service registry."""
        self.mode = DeploymentMode(mode)
        self.config_file = config_file
        self.namespace = namespace
        self.project_root = Path(__file__).parent.parent
        self.deployment_started = False

        # Load deployment configuration
        self.service_registry = get_service_registry(config_file)

        logger.info("🚀 AutoBot Deployer initialized")
        logger.info(f"   Mode: {self.mode.value}")
        logger.info(f"   Config: {config_file or 'default'}")
        logger.info(f"   Namespace: {namespace}")

    # Standalone copies of ScriptFormatter.print_header/print_step
    # (autobot-backend/utils/script_utils.py) — this script must not
    # import backend modules (#11761).
    def print_header(self, title: str, width: int = 60):
        """Print formatted header."""
        print(f"\n{'=' * width}")  # noqa: print  # canonical: ignore py-print-smoke
        print(f"  {title}")  # noqa: print  # canonical: ignore py-print-smoke
        print("=" * width)  # noqa: print  # canonical: ignore py-print-smoke

    def print_step(self, step: str, status: str = "info"):
        """Print deployment step with status."""
        status_symbols = {
            "info": "📋",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "running": "🔄",
        }
        symbol = status_symbols.get(status, "📋")
        print(f"{symbol} {step}")  # noqa: print  # canonical: ignore py-print-smoke

    def run_command(self, command: str, check: bool = True, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run shell command with error handling."""
        self.print_step(f"Running: {command}", "running")
        try:
            result = subprocess.run(
                command,
                shell=True,
                check=check,
                capture_output=True,
                text=True,
                cwd=cwd or self.project_root,
            )
            if result.returncode == 0:
                self.print_step("Command succeeded", "success")
            else:
                self.print_step(f"Command failed: {result.stderr}", "error")
            return result
        except subprocess.CalledProcessError as e:
            self.print_step(f"Command failed: {e}", "error")
            if check:
                raise
            return e

    def check_prerequisites(self) -> bool:
        """Check deployment prerequisites."""
        self.print_header("Checking Prerequisites")

        prerequisites = []

        # Check Docker
        try:
            result = self.run_command("docker --version", check=False)
            if result.returncode == 0:
                prerequisites.append(("Docker", True, result.stdout.strip()))
            else:
                prerequisites.append(("Docker", False, "Not installed"))
        except Exception as e:
            prerequisites.append(("Docker", False, str(e)))

        # Check Docker Compose
        try:
            result = self.run_command("docker compose version", check=False)
            if result.returncode == 0:
                prerequisites.append(("Docker Compose", True, result.stdout.strip()))
            else:
                prerequisites.append(("Docker Compose", False, "Not installed"))
        except Exception as e:
            prerequisites.append(("Docker Compose", False, str(e)))

        # Check Python
        try:
            result = self.run_command("python3 --version", check=False)
            if result.returncode == 0:
                prerequisites.append(("Python 3", True, result.stdout.strip()))
            else:
                prerequisites.append(("Python 3", False, "Not installed"))
        except Exception as e:
            prerequisites.append(("Python 3", False, str(e)))

        # Check Node.js (for frontend)
        try:
            result = self.run_command("node --version", check=False)
            if result.returncode == 0:
                prerequisites.append(("Node.js", True, result.stdout.strip()))
            else:
                prerequisites.append(("Node.js", False, "Not installed"))
        except Exception as e:
            prerequisites.append(("Node.js", False, str(e)))

        # Print results
        all_good = True
        for name, available, version in prerequisites:
            if available:
                self.print_step(f"{name}: {version}", "success")
            else:
                self.print_step(f"{name}: {version}", "error")
                all_good = False

        if not all_good:
            self.print_step("Some prerequisites are missing", "error")

        return all_good

    def prepare_environment(self):
        """Prepare environment for deployment."""
        self.print_header("Preparing Environment")

        # Create necessary directories
        dirs_to_create = ["data", "logs", "reports", "docker/logs"]

        for dir_name in dirs_to_create:
            dir_path = self.project_root / dir_name
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                self.print_step(f"Created directory: {dir_path}", "success")

        # Set up Python virtual environment if needed
        venv_path = self.project_root / "venv"
        if not venv_path.exists() and self.mode in [
            DeploymentMode.LOCAL,
            DeploymentMode.DISTRIBUTED,
        ]:
            self.print_step("Creating Python virtual environment", "info")
            self.run_command(f"python3 -m venv {venv_path}")

            # Install requirements
            pip_cmd = f"{venv_path}/bin/pip"
            self.run_command(f"{pip_cmd} install --upgrade pip")
            self.run_command(f"{pip_cmd} install -r requirements.txt")
            self.print_step("Virtual environment ready", "success")

    def deploy_local(self):
        """Deploy in local hybrid mode (default)."""
        self.print_header("Deploying in Local Hybrid Mode")

        # Start Docker services only
        compose_file = self.project_root / "docker/compose/docker-compose.hybrid.yml"
        if compose_file.exists():
            self.print_step("Starting Docker services (Redis, AI Stack, etc.)", "info")
            self.run_command(f"docker compose -f {compose_file} up -d")
            self.print_step("Docker services started", "success")
        else:
            self.print_step(f"Compose file not found: {compose_file}", "error")
            return False

        # Backend and frontend run on host
        self.print_step("Backend and Frontend will run on host via run_agent.sh", "info")
        self.print_step("Use './run_agent.sh' to start the full application", "success")

        return True

    def deploy_docker_local(self, build: bool = False):
        """Deploy in full Docker mode on single machine."""
        self.print_header("Deploying in Full Docker Mode")

        compose_file = self.project_root / "docker/compose/docker-compose.full.yml"

        if build:
            self.print_step("Building Docker images", "info")
            self.run_command(f"docker compose -f {compose_file} build")

        self.print_step("Starting all services in Docker", "info")
        self.run_command(f"docker compose -f {compose_file} up -d")

        self.print_step("All services deployed in Docker", "success")
        return True

    def deploy_distributed(self):
        """Deploy in distributed mode across multiple machines."""
        self.print_header("Deploying in Distributed Mode")

        # Load distributed configuration
        if not self.config_file:
            self.config_file = self.project_root / "config/deployment/distributed.yml"

        if not os.path.exists(self.config_file):
            self.print_step(f"Distributed config file not found: {self.config_file}", "error")
            return False

        with open(self.config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        services = config.get("services", {})

        self.print_step(f"Loaded distributed configuration with {len(services)} services", "info")

        # Deploy each service based on its host configuration
        for service_name, service_config in services.items():
            host = service_config.get("host", "localhost")

            if host == "localhost" or host.startswith("127.0.0.1"):
                # Local service - deploy with Docker
                self.print_step(f"Deploying {service_name} locally", "info")
                compose_file = f"docker/compose/docker-compose.{service_name}.yml"
                if os.path.exists(compose_file):
                    self.run_command(f"docker compose -f {compose_file} up -d")
            else:
                # Remote service - would need SSH deployment (placeholder)
                self.print_step(
                    f"Remote deployment for {service_name} on {host} (manual setup required)",
                    "warning",
                )

        self.print_step("Distributed deployment initiated", "success")
        return True

    def deploy_kubernetes(self, build_images: bool = False):
        """Deploy to Kubernetes cluster."""
        self.print_header("Deploying to Kubernetes")

        # Check kubectl
        result = self.run_command("kubectl version --client", check=False)
        if result.returncode != 0:
            self.print_step("kubectl not available", "error")
            return False

        k8s_dir = self.project_root / "k8s"
        if not k8s_dir.exists():
            self.print_step("Creating Kubernetes manifests", "info")
            k8s_dir.mkdir(exist_ok=True)

            # Create sample namespace manifest
            namespace_manifest = """
apiVersion: v1
kind: Namespace
metadata:
  name: {self.namespace}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: autobot-backend
  namespace: {self.namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: autobot-backend
  template:
    metadata:
      labels:
        app: autobot-backend
    spec:
      containers:
      - name: backend
        image: autobot-backend:latest
        ports:
        - containerPort: 8001
---
apiVersion: v1
kind: Service
metadata:
  name: autobot-backend-service
  namespace: {self.namespace}
spec:
  selector:
    app: autobot-backend
  ports:
  - port: 8001
    targetPort: 8001
  type: ClusterIP
"""

            with open(k8s_dir / "autobot-deployment.yml", "w", encoding="utf-8") as f:
                f.write(namespace_manifest)

            self.print_step("Kubernetes manifests created", "success")

        # Apply manifests
        self.print_step(f"Applying Kubernetes manifests to namespace: {self.namespace}", "info")
        self.run_command(f"kubectl apply -f {k8s_dir}/")

        self.print_step("Kubernetes deployment applied", "success")
        return True

    async def wait_for_services(self, timeout: int = 300):
        """Wait for services to be healthy."""
        self.print_header("Waiting for Services to be Ready")

        start_time = time.time()
        healthy_services = set()
        all_services = self.service_registry.list_services()

        while time.time() - start_time < timeout:
            try:
                health_results = await self.service_registry.check_all_services_health()

                for service, health in health_results.items():
                    if health.status.value == "healthy" and service not in healthy_services:
                        self.print_step(f"{service} is healthy", "success")
                        healthy_services.add(service)
                    elif health.status.value != "healthy":
                        if time.time() - start_time > 60:  # Only show after 1 minute
                            self.print_step(f"{service} is {health.status.value}", "warning")

                if len(healthy_services) == len(all_services):
                    self.print_step("All services are healthy!", "success")
                    return True

                await asyncio.sleep(TimingConstants.MEDIUM_DELAY)

            except Exception as e:
                self.print_step(f"Health check error: {e}", "warning")
                await asyncio.sleep(TimingConstants.LONG_DELAY)

        self.print_step(
            f"Timeout waiting for services. {len(healthy_services)}/{len(all_services)} healthy",
            "warning",
        )
        return False

    def generate_deployment_info(self) -> Dict[str, Any]:
        """Generate deployment information."""
        info = self.service_registry.get_deployment_info()

        info.update(
            {
                "deployment_mode": self.mode.value,
                "deployment_time": time.time(),
                "deployer_version": "1.0.0",
                "project_root": str(self.project_root),
                "config_file": self.config_file,
            }
        )

        return info

    def save_deployment_info(self, info: Dict[str, Any]):
        """Save deployment information to file."""
        info_file = self.project_root / "deployment_info.json"

        with open(info_file, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, default=str)

        self.print_step(f"Deployment info saved to: {info_file}", "success")

    async def deploy(self, build: bool = False, wait_for_health: bool = True) -> bool:
        """Main deployment method."""
        try:
            self.deployment_started = True

            # Check prerequisites
            if not self.check_prerequisites():
                self.print_step("Prerequisites check failed", "error")
                return False

            # Prepare environment
            self.prepare_environment()

            # Deploy based on mode
            success = False
            if self.mode == DeploymentMode.LOCAL:
                success = self.deploy_local()
            elif self.mode == DeploymentMode.DOCKER_LOCAL:
                success = self.deploy_docker_local(build=build)
            elif self.mode == DeploymentMode.DISTRIBUTED:
                success = self.deploy_distributed()
            elif self.mode == DeploymentMode.KUBERNETES:
                success = self.deploy_kubernetes(build_images=build)
            else:
                self.print_step(f"Unknown deployment mode: {self.mode}", "error")
                return False

            if not success:
                self.print_step("Deployment failed", "error")
                return False

            # Wait for services to be healthy
            if wait_for_health and self.mode != DeploymentMode.KUBERNETES:
                await self.wait_for_services()

            # Generate and save deployment info
            deployment_info = self.generate_deployment_info()
            self.save_deployment_info(deployment_info)

            self.print_header("Deployment Summary")
            self.print_step(f"Mode: {self.mode.value}", "info")
            self.print_step(f"Services: {len(deployment_info['services'])}", "info")
            self.print_step("Deployment completed successfully!", "success")

            return True

        except Exception as e:
            self.print_step(f"Deployment failed: {e}", "error")
            return False

    def cleanup(self):
        """Clean up deployment."""
        self.print_header("Cleaning Up Deployment")

        if self.mode in [DeploymentMode.LOCAL, DeploymentMode.DOCKER_LOCAL]:
            # Stop Docker services
            compose_files = [
                "docker/compose/docker-compose.hybrid.yml",
                "docker/compose/docker-compose.full.yml",
            ]

            for compose_file in compose_files:
                if os.path.exists(compose_file):
                    self.print_step(f"Stopping services from {compose_file}", "info")
                    self.run_command(f"docker compose -f {compose_file} down", check=False)

        elif self.mode == DeploymentMode.KUBERNETES:
            self.print_step(
                f"Removing Kubernetes resources from namespace: {self.namespace}",
                "info",
            )
            self.run_command(f"kubectl delete namespace {self.namespace}", check=False)

        self.print_step("Cleanup completed", "success")


def main():
    """Entry point for AutoBot deployment automation CLI."""
    parser = argparse.ArgumentParser(
        description="AutoBot Deployment Automation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/deploy_autobot.py --mode local
  python scripts/deploy_autobot.py --mode docker_local --build
  python scripts/deploy_autobot.py --mode distributed --config config/deployment/production.yml
  python scripts/deploy_autobot.py --mode kubernetes --namespace autobot-prod --build
  python scripts/deploy_autobot.py --cleanup --mode local
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["local", "docker_local", "distributed", "kubernetes"],
        default="local",
        help="Deployment mode (default: local)",
    )

    parser.add_argument("--config", help="Configuration file path")

    parser.add_argument("--namespace", default="autobot", help="Kubernetes namespace (default: autobot)")

    parser.add_argument("--build", action="store_true", help="Build Docker images before deployment")

    parser.add_argument("--cleanup", action="store_true", help="Clean up existing deployment")

    parser.add_argument("--no-wait", action="store_true", help="Don't wait for services to be healthy")

    args = parser.parse_args()

    try:
        deployer = AutoBotDeployer(mode=args.mode, config_file=args.config, namespace=args.namespace)

        if args.cleanup:
            deployer.cleanup()
            return 0

        # Run deployment
        success = asyncio.run(deployer.deploy(build=args.build, wait_for_health=not args.no_wait))

        return 0 if success else 1

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Deployment cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Deployment failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
