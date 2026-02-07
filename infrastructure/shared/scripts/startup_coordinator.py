#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Startup Coordinator

Manages startup sequence with proper state reporting and dependencies.
Each component reports its state before dependent components can start.
"""
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiohttp
import psutil

# Import centralized Redis client and network constants
sys.path.append(str(Path(__file__).parent.parent))
from src.constants.network_constants import NetworkConstants, ServiceURLs
from src.constants.threshold_constants import TimingConstants
from src.utils.redis_client import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/startup_coordinator.log"),
    ],
)
logger = logging.getLogger(__name__)


class ComponentState(Enum):
    """States a component can be in during startup"""

    PENDING = "pending"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    STOPPED = "stopped"


def _restore_component_from_data(comp: "ComponentInfo", data: dict) -> None:
    """Restore component state from saved data (Issue #315 - extracted)."""
    comp.state = ComponentState(data.get("state", "pending"))
    comp.pid = data.get("pid")
    comp.health_status = HealthStatus(data.get("health_status", "unknown"))


async def _check_redis_health() -> bool:
    """Check Redis health via centralized client (Issue #315 - extracted)."""
    try:
        redis_client = await get_redis_client("main")
        if redis_client:
            await redis_client.ping()
            return True
        return False
    except Exception:
        return False


def _terminate_process_gracefully(name: str, process: subprocess.Popen) -> bool:
    """Terminate a process gracefully with fallback to kill (Issue #315 - extracted)."""
    if process.poll() is not None:
        return False  # Process already stopped

    logger.info("Stopping %s (PID: %s)", name, process.pid)
    process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("Force killing %s", name)
        process.kill()
        process.wait()

    logger.info("✅ %s stopped", name)
    return True


class HealthStatus(Enum):
    """Health check results"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentInfo:
    """Information about a startup component"""

    name: str
    state: ComponentState = ComponentState.PENDING
    pid: Optional[int] = None
    port: Optional[int] = None
    health_url: Optional[str] = None
    dependencies: List[str] = None
    start_command: Optional[str] = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    start_time: Optional[float] = None
    ready_time: Optional[float] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        """Initialize default dependencies list if not provided."""
        if self.dependencies is None:
            self.dependencies = []


class StartupCoordinator:
    """Coordinates the startup of AutoBot components with proper dependency management"""

    def __init__(self):
        """Initialize startup coordinator with component definitions and state management."""
        self.components: Dict[str, ComponentInfo] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        self.startup_state_file = Path("data/startup_state.json")
        self.max_startup_time = 300  # 5 minutes max for any component
        self.health_check_timeout = 5  # 5 seconds for health checks

        # Define component startup order and dependencies
        self._define_components()

    def _define_components(self):
        """Define all components and their dependencies"""

        # Core infrastructure (no dependencies)
        self.components["redis"] = ComponentInfo(
            name="redis",
            port=NetworkConstants.REDIS_PORT,
            health_url=ServiceURLs.REDIS_LOCAL,
            dependencies=[],
        )

        self.components["logging"] = ComponentInfo(name="logging", dependencies=[])

        # Configuration (no dependencies - just loads config files)
        self.components["config"] = ComponentInfo(name="config", dependencies=[])

        # Backend API (depends on redis and config)
        self.components["backend"] = ComponentInfo(
            name="backend",
            port=NetworkConstants.BACKEND_PORT,
            health_url=f"{ServiceURLs.BACKEND_LOCAL}/api/system/health",
            dependencies=["redis", "config"],
            start_command=f"uvicorn main:app --host 0.0.0.0 --port {NetworkConstants.BACKEND_PORT} --log-level info",
        )

        # Frontend (depends on backend being ready)
        self.components["frontend"] = ComponentInfo(
            name="frontend",
            port=NetworkConstants.FRONTEND_PORT,
            health_url=ServiceURLs.FRONTEND_LOCAL,
            dependencies=["backend"],
            start_command="npm run dev",
        )

        # Optional components
        self.components["ai_stack"] = ComponentInfo(
            name="ai_stack", dependencies=["redis", "config"]
        )

    def save_state(self):
        """Save current startup state to file"""
        try:
            state_data = {name: asdict(comp) for name, comp in self.components.items()}
            self.startup_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.startup_state_file, "w") as f:
                json.dump(state_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save startup state: %s", e)

    def load_state(self):
        """Load startup state from file if it exists (Issue #315 - refactored)."""
        if not self.startup_state_file.exists():
            return

        try:
            with open(self.startup_state_file, "r") as f:
                state_data = json.load(f)

            for name, data in state_data.items():
                if name in self.components:
                    _restore_component_from_data(self.components[name], data)

            logger.info("Loaded previous startup state")
        except Exception as e:
            logger.warning("Could not load previous startup state: %s", e)

    async def check_health(self, component: ComponentInfo) -> bool:
        """Check if a component is healthy (Issue #315 - refactored)."""
        if not component.health_url:
            return component.pid and psutil.pid_exists(component.pid)

        try:
            healthy = await self._perform_health_check(component)
            component.health_status = (
                HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY
            )
            return healthy
        except Exception as e:
            logger.debug("Health check failed for %s: %s", component.name, e)
            component.health_status = HealthStatus.UNHEALTHY
            return False

    async def _perform_health_check(self, component: "ComponentInfo") -> bool:
        """Perform the actual health check based on URL type (Issue #315 - extracted, #359 - async)."""
        if component.health_url.startswith("http"):
            # Issue #359: Use async HTTP client instead of blocking requests
            timeout = aiohttp.ClientTimeout(total=self.health_check_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(component.health_url) as response:
                    return response.status == 200

        if component.health_url.startswith("redis"):
            # Issue #359: Direct async call instead of creating new event loop
            return await _check_redis_health()

        return False

    def check_dependencies_ready(self, component: ComponentInfo) -> bool:
        """Check if all dependencies of a component are ready"""
        for dep_name in component.dependencies:
            if dep_name not in self.components:
                logger.error(
                    "Unknown dependency '%s' for component '%s'",
                    dep_name,
                    component.name,
                )
                return False

            dep = self.components[dep_name]
            if dep.state != ComponentState.READY:
                logger.debug(
                    "Dependency '%s' not ready for '%s' (state: %s)",
                    dep_name,
                    component.name,
                    dep.state,
                )
                return False

        return True

    def _get_component_env_and_cwd(self, component: ComponentInfo) -> tuple:
        """Get environment and working directory for a component (Issue #665: extracted helper)."""
        env = os.environ.copy()
        cwd = None

        if component.name == "backend":
            cwd = "backend"
            env["PYTHONPATH"] = os.path.abspath(".") + ":" + env.get("PYTHONPATH", "")
        elif component.name == "frontend":
            cwd = "autobot-vue"

        return env, cwd

    async def _wait_for_component_health(
        self, component: ComponentInfo, process: subprocess.Popen
    ) -> bool:
        """Wait for component to become healthy with timeout (Issue #665: extracted helper)."""
        max_wait = self.max_startup_time
        check_interval = 2

        for attempt in range(0, max_wait, check_interval):
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                error_msg = f"Process died: {stderr.decode()}"
                logger.error("❌ %s failed: %s", component.name, error_msg)
                component.error_message = error_msg
                component.state = ComponentState.FAILED
                self.save_state()
                return False

            if await self.check_health(component):
                component.state = ComponentState.READY
                component.ready_time = time.time()
                startup_duration = component.ready_time - component.start_time
                logger.info(
                    "✅ %s is ready (took %.1fs)", component.name, startup_duration
                )
                self.save_state()
                return True

            if attempt % 10 == 0 and attempt > 0:
                logger.info(
                    "⏳ Waiting for %s to be ready... (%ss elapsed)",
                    component.name,
                    attempt,
                )

            await asyncio.sleep(check_interval)

        logger.error("❌ %s did not become ready within %ss", component.name, max_wait)
        component.error_message = f"Startup timeout ({max_wait}s)"
        component.state = ComponentState.FAILED
        self.save_state()
        return False

    async def start_component(self, component: ComponentInfo) -> bool:
        """Start a single component"""
        logger.info("🚀 Starting component: %s", component.name)
        component.state = ComponentState.STARTING
        component.start_time = time.time()
        self.save_state()

        try:
            if component.start_command:
                logger.info("Executing: %s", component.start_command)

                env, cwd = self._get_component_env_and_cwd(component)

                process = subprocess.Popen(
                    component.start_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    cwd=cwd,
                )

                self.processes[component.name] = process
                component.pid = process.pid

                logger.info("Started %s with PID %s", component.name, component.pid)

                return await self._wait_for_component_health(component, process)
            else:
                logger.info("✅ %s is ready (built-in)", component.name)
                component.state = ComponentState.READY
                component.ready_time = time.time()
                self.save_state()
                return True

        except Exception as e:
            error_msg = f"Failed to start: {str(e)}"
            logger.error("❌ %s failed: %s", component.name, error_msg)
            component.error_message = error_msg
            component.state = ComponentState.FAILED
            self.save_state()
            return False

    async def startup_sequence(
        self, target_components: Optional[Set[str]] = None
    ) -> bool:
        """Execute the complete startup sequence"""
        if target_components is None:
            target_components = set(self.components.keys())

        logger.info("🎯 Starting AutoBot with state-based startup coordination")
        logger.info("Target components: %s", ", ".join(sorted(target_components)))

        # Load any previous state
        self.load_state()

        started_components = set()
        failed_components = set()

        while True:
            # Find components that are ready to start
            ready_to_start = []

            for name, component in self.components.items():
                if (
                    name in target_components
                    and name not in started_components
                    and name not in failed_components
                    and component.state == ComponentState.PENDING
                    and self.check_dependencies_ready(component)
                ):
                    ready_to_start.append(component)

            if not ready_to_start:
                # Check if we're done
                remaining = target_components - started_components - failed_components
                if not remaining:
                    break

                # Check if we're stuck (all remaining components have failed dependencies)
                all_stuck = True
                for name in remaining:
                    component = self.components[name]
                    if self.check_dependencies_ready(component):
                        all_stuck = False
                        break

                if all_stuck:
                    logger.error(
                        "❌ Startup stuck! Remaining components have failed dependencies: %s",
                        remaining,
                    )
                    return False

                # Wait a bit and try again
                logger.info("⏳ Waiting for dependencies...")
                await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
                continue

            # Start components in parallel if they don't depend on each other
            tasks = []
            for component in ready_to_start:
                task = asyncio.create_task(self.start_component(component))
                tasks.append((component.name, task))

            # Wait for all to complete
            for name, task in tasks:
                success = await task
                if success:
                    started_components.add(name)
                    logger.info("✅ Component '%s' started successfully", name)
                else:
                    failed_components.add(name)
                    logger.error("❌ Component '%s' failed to start", name)

        # Final status
        total_target = len(target_components)
        successful = len(started_components)
        len(failed_components)

        logger.info(
            "🎯 Startup completed: %s/%s components started", successful, total_target
        )

        if failed_components:
            logger.error("❌ Failed components: %s", ", ".join(failed_components))
            return False

        logger.info("🎉 All components started successfully!")
        return True

    def stop_all(self):
        """Stop all running processes (Issue #315 - refactored)."""
        logger.info("🛑 Stopping all components...")

        for name, process in self.processes.items():
            try:
                if _terminate_process_gracefully(name, process):
                    self.components[name].state = ComponentState.STOPPED
            except Exception as e:
                logger.error("Error stopping %s: %s", name, e)

        self.save_state()

        if self.startup_state_file.exists():
            self.startup_state_file.unlink()


async def main():
    """Main startup coordinator entry point with argument parsing and signal handling."""
    coordinator = StartupCoordinator()

    # Set up signal handling
    def signal_handler(signum, frame):
        """Handle shutdown signals by stopping all components gracefully."""
        logger.info("Received signal %s, shutting down...", signum)
        coordinator.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Parse command line arguments
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Startup Coordinator")
    parser.add_argument(
        "--components",
        nargs="*",
        help="Specific components to start (default: all)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current component status",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop all components",
    )

    args = parser.parse_args()

    if args.status:
        coordinator.load_state()
        print("\n🔍 Component Status:")
        for name, comp in coordinator.components.items():
            status_icon = {
                ComponentState.PENDING: "⏳",
                ComponentState.STARTING: "🚀",
                ComponentState.READY: "✅",
                ComponentState.FAILED: "❌",
                ComponentState.STOPPED: "🛑",
            }.get(comp.state, "❓")

            print(
                f"  {status_icon} {name:<12} {comp.state.value:<8} "
                f"PID: {comp.pid or 'N/A':<6} "
                f"Health: {comp.health_status.value}"
            )
        return

    if args.stop:
        coordinator.stop_all()
        return

    # Start components
    target_components = None
    if args.components:
        target_components = set(args.components)
        # Validate component names
        invalid = target_components - set(coordinator.components.keys())
        if invalid:
            logger.error("Invalid component names: %s", invalid)
            logger.info("Available: %s", ", ".join(coordinator.components.keys()))
            return

    success = await coordinator.startup_sequence(target_components)
    if not success:
        logger.error("❌ Startup failed!")
        sys.exit(1)

    logger.info("✅ AutoBot is ready!")

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(TimingConstants.LONG_DELAY)

            # Periodic health checks
            for name, component in coordinator.components.items():
                if component.state == ComponentState.READY:
                    healthy = await coordinator.check_health(component)
                    if not healthy:
                        logger.warning("⚠️ Component %s health check failed", name)
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
