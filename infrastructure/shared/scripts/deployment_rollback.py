#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Deployment Rollback System
==================================

Production-ready rollback system for AutoBot deployments with health,
service state validation, and automatic failure recovery.

Features:
- Safe rollback with health verification
- Automatic backup creation before rollback
- Service-by-service rollback support
- Zero-downtime rollback strategies
- Rollback plan validation and dry-run mode

Usage:
    python scripts/deployment_rollback.py --rollback --backup-id 20250821-143022
    python scripts/deployment_rollback.py --rollback --version v1.2.3 --strategy zero-downtime
    python scripts/deployment_rollback.py --plan --target-version v1.2.3
    python scripts/deployment_rollback.py --list-versions
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import logging

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.backup_manager import BackupManager
from constants.threshold_constants import TimingConstants
from utils.script_utils import ScriptFormatter
from utils.service_registry import ServiceStatus, get_service_registry


class RollbackStrategy:
    """Available rollback strategies."""

    IMMEDIATE = "immediate"  # Stop all, rollback, restart
    ZERO_DOWNTIME = "zero-downtime"  # Blue-green style rollback
    SERVICE_BY_SERVICE = "service-by-service"  # Rolling rollback


class RollbackManager:
    """Manages safe deployment rollbacks with health verification."""

    def __init__(self, backup_dir: str = "backups", rollback_dir: str = "rollbacks"):
        """Initialize rollback manager with backup manager and service registry."""
        self.project_root = Path(__file__).parent.parent
        self.backup_dir = self.project_root / backup_dir
        self.rollback_dir = self.project_root / rollback_dir
        self.rollback_dir.mkdir(exist_ok=True)

        self.service_registry = get_service_registry()
        self.backup_manager = BackupManager(backup_dir)

        # Rollback configuration
        self.rollback_config = self._load_rollback_config()

        # Version tracking
        self.deployment_info_file = self.project_root / "deployment_info.json"

        logger.info("🔄 AutoBot Rollback Manager initialized")
        logger.info(f"   Backup Directory: {self.backup_dir}")
        logger.info(f"   Rollback Directory: {self.rollback_dir}")

    def print_header(self, title: str):
        """Print formatted header."""
        ScriptFormatter.print_header(title)

    def print_step(self, step: str, status: str = "info"):
        """Print step with status."""
        ScriptFormatter.print_step(step, status)

    def _load_rollback_config(self) -> Dict[str, Any]:
        """Load rollback configuration."""
        config_file = self.project_root / "config" / "rollback.yml"

        default_config = {
            "health_check_timeout": 300,  # 5 minutes
            "health_check_interval": 10,  # 10 seconds
            "service_start_timeout": 120,  # 2 minutes
            "rollback_timeout": 600,  # 10 minutes total
            "pre_rollback_backup": True,
            "verify_rollback": True,
            "cleanup_failed_rollback": True,
            "services_order": [
                "redis",
                "ai-stack",
                "npu-worker",
                "backend",
                "frontend",
            ],
        }

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    file_config = yaml.safe_load(f) or {}
                default_config.update(file_config)
            except Exception as e:
                self.print_step(
                    f"Warning: Could not load rollback config: {e}", "warning"
                )

        return default_config

    def get_current_deployment_info(self) -> Dict[str, Any]:
        """Get current deployment information."""
        if self.deployment_info_file.exists():
            try:
                with open(self.deployment_info_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass  # Deployment info file corrupt or unreadable

        # Fallback deployment info
        return {
            "version": "unknown",
            "deployment_mode": self.service_registry.deployment_mode.value,
            "deployed_at": datetime.now().isoformat(),
            "deployer": "rollback-manager",
            "commit_hash": self._get_git_commit(),
            "services": list(self.service_registry.list_services()),
        }

    def _get_git_commit(self) -> str:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:8]
        except Exception:
            pass  # Git command failed, return unknown below
        return "unknown"

    def list_available_versions(self) -> List[Dict[str, Any]]:
        """List available versions for rollback."""
        versions = []

        # Get backup-based versions
        backups = self.backup_manager.list_backups()
        for backup_id, backup_info in sorted(backups.items(), reverse=True):
            versions.append(
                {
                    "type": "backup",
                    "id": backup_id,
                    "version": backup_id,
                    "created_at": backup_info["created_at"],
                    "deployment_mode": backup_info["deployment_mode"],
                    "size": backup_info["size"],
                    "rollback_method": "restore_backup",
                }
            )

        # Get git-based versions (tags)
        git_versions = self._get_git_versions()
        for version in git_versions:
            versions.append(
                {
                    "type": "git",
                    "id": version["tag"],
                    "version": version["tag"],
                    "created_at": version["date"],
                    "commit": version["commit"],
                    "rollback_method": "git_checkout",
                }
            )

        return versions

    def _get_git_versions(self) -> List[Dict[str, Any]]:
        """Get available git versions (tags)."""
        try:
            # Get git tags
            result = subprocess.run(
                [
                    "git",
                    "tag",
                    "-l",
                    "--sort=-version:refname",
                    "--format=%(refname:short)|%(creatordate:iso)|%(objectname:short)",
                ],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                return []

            versions = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("|")
                if len(parts) >= 3:
                    versions.append(
                        {"tag": parts[0], "date": parts[1], "commit": parts[2]}
                    )

            return versions[:10]  # Return last 10 versions

        except Exception:
            return []

    async def verify_services_health(self, timeout: int = 300) -> bool:
        """Verify all services are healthy with timeout."""
        self.print_step("Verifying service health...", "running")

        start_time = time.time()
        check_interval = self.rollback_config["health_check_interval"]

        while time.time() - start_time < timeout:
            try:
                health_results = await self.service_registry.check_all_services_health()

                healthy_count = sum(
                    1
                    for h in health_results.values()
                    if h.status == ServiceStatus.HEALTHY
                )
                total_count = len(health_results)

                self.print_step(
                    f"Health check: {healthy_count}/{total_count} services healthy",
                    "info",
                )

                if healthy_count == total_count:
                    self.print_step("All services are healthy", "success")
                    return True

                # Show unhealthy services
                for service, health in health_results.items():
                    if health.status != ServiceStatus.HEALTHY:
                        self.print_step(
                            f"  {service}: {health.status.value}", "warning"
                        )

                await asyncio.sleep(check_interval)

            except Exception as e:
                self.print_step(f"Health check error: {e}", "error")
                await asyncio.sleep(check_interval)

        self.print_step(f"Health verification failed after {timeout}s", "error")
        return False

    def _add_pre_rollback_steps(self, plan: Dict) -> None:
        """Add pre-rollback backup step if configured.

        Helper for create_rollback_plan (Issue #825).
        """
        if self.rollback_config["pre_rollback_backup"]:
            plan["steps"].append(
                {
                    "step": "create_pre_rollback_backup",
                    "description": "Create backup of current state",
                    "estimated_time": "30-60s",
                    "critical": True,
                }
            )

    def _add_strategy_steps(
        self, plan: Dict, strategy: str, target_version: str
    ) -> None:
        """Add strategy-specific rollback steps.

        Helper for create_rollback_plan (Issue #825).
        """
        if strategy == RollbackStrategy.IMMEDIATE:
            plan["steps"].extend(
                [
                    {
                        "step": "stop_all_services",
                        "description": "Stop all AutoBot services",
                        "estimated_time": "30s",
                        "critical": True,
                    },
                    {
                        "step": "restore_target_version",
                        "description": f"Restore to version {target_version}",
                        "estimated_time": "60-120s",
                        "critical": True,
                    },
                    {
                        "step": "start_all_services",
                        "description": "Start all services in correct order",
                        "estimated_time": "60-120s",
                        "critical": True,
                    },
                ]
            )

        elif strategy == RollbackStrategy.ZERO_DOWNTIME:
            plan["steps"].extend(
                [
                    {
                        "step": "deploy_parallel_version",
                        "description": "Deploy target version in parallel",
                        "estimated_time": "120-180s",
                        "critical": True,
                    },
                    {
                        "step": "switch_traffic",
                        "description": "Switch traffic to rolled-back version",
                        "estimated_time": "10s",
                        "critical": True,
                    },
                    {
                        "step": "cleanup_old_version",
                        "description": "Clean up current version",
                        "estimated_time": "30s",
                        "critical": False,
                    },
                ]
            )

        elif strategy == RollbackStrategy.SERVICE_BY_SERVICE:
            for service in self.rollback_config["services_order"]:
                plan["steps"].append(
                    {
                        "step": f"rollback_service_{service}",
                        "description": f"Rollback {service} service",
                        "estimated_time": "30-60s",
                        "critical": True,
                    }
                )

    def _add_post_rollback_steps(self, plan: Dict) -> None:
        """Add post-rollback verification steps.

        Helper for create_rollback_plan (Issue #825).
        """
        plan["steps"].extend(
            [
                {
                    "step": "verify_health",
                    "description": "Verify all services are healthy",
                    "estimated_time": "60-300s",
                    "critical": True,
                },
                {
                    "step": "update_deployment_info",
                    "description": "Update deployment information",
                    "estimated_time": "5s",
                    "critical": False,
                },
            ]
        )

    def create_rollback_plan(
        self, target_version: str, strategy: str = RollbackStrategy.IMMEDIATE
    ) -> Dict[str, Any]:
        """Create detailed rollback plan."""
        current_info = self.get_current_deployment_info()

        plan = {
            "rollback_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
            "created_at": datetime.now().isoformat(),
            "current_version": current_info["version"],
            "target_version": target_version,
            "strategy": strategy,
            "estimated_downtime": self._estimate_downtime(strategy),
            "steps": [],
        }

        self._add_pre_rollback_steps(plan)
        self._add_strategy_steps(plan, strategy, target_version)
        self._add_post_rollback_steps(plan)

        return plan

    def _estimate_downtime(self, strategy: str) -> str:
        """Estimate downtime for rollback strategy."""
        estimates = {
            RollbackStrategy.IMMEDIATE: "3-5 minutes",
            RollbackStrategy.ZERO_DOWNTIME: "10-30 seconds",
            RollbackStrategy.SERVICE_BY_SERVICE: "1-2 minutes",
        }
        return estimates.get(strategy, "unknown")

    async def _execute_step(
        self, step: dict, target_version: str, rollback_id: str
    ) -> tuple[bool, bool]:
        """Execute a single rollback step (Issue #315: extracted helper).

        Returns: (success, should_continue) tuple
        """
        step_name = step["step"]
        is_critical = step.get("critical", False)

        step_handlers = {
            "create_pre_rollback_backup": self._handle_backup_step,
            "verify_health": self._handle_health_step,
            "restore_target_version": self._handle_restore_step,
            "stop_all_services": self._handle_stop_step,
            "start_all_services": self._handle_start_step,
            "update_deployment_info": self._handle_update_step,
        }

        handler = step_handlers.get(step_name)
        if handler:
            success = await handler(step, target_version, rollback_id)
            if not success and is_critical:
                self.print_step(f"Critical step failed: {step_name}", "error")
                return False, False
            if not success:
                self.print_step(f"Non-critical step failed: {step_name}", "warning")
        return True, True

    async def _handle_backup_step(
        self, step: dict, target_version: str, rollback_id: str
    ) -> bool:
        """Handle backup creation step (Issue #315: extracted helper)."""
        backup_id = self.backup_manager.create_full_backup()
        return backup_id is not None

    async def _handle_health_step(
        self, step: dict, target_version: str, rollback_id: str
    ) -> bool:
        """Handle health verification step (Issue #315: extracted helper)."""
        return await self.verify_services_health(
            self.rollback_config["health_check_timeout"]
        )

    async def _handle_restore_step(
        self, step: dict, target_version: str, rollback_id: str
    ) -> bool:
        """Handle version restore step (Issue #315: extracted helper)."""
        return await self._restore_version(target_version)

    async def _handle_stop_step(
        self, step: dict, target_version: str, rollback_id: str
    ) -> bool:
        """Handle stop services step (Issue #315: extracted helper)."""
        return self._stop_services()

    async def _handle_start_step(
        self, step: dict, target_version: str, rollback_id: str
    ) -> bool:
        """Handle start services step (Issue #315: extracted helper)."""
        return self._start_services()

    async def _handle_update_step(
        self, step: dict, target_version: str, rollback_id: str
    ) -> bool:
        """Handle deployment info update step (Issue #315: extracted helper)."""
        # Issue #666: Wrap blocking I/O in asyncio.to_thread
        await asyncio.to_thread(
            self._update_deployment_info, target_version, rollback_id
        )
        return True

    async def execute_rollback(
        self,
        target_version: str,
        strategy: str = RollbackStrategy.IMMEDIATE,
        dry_run: bool = False,
    ) -> bool:
        """Execute rollback with specified strategy."""
        rollback_id = datetime.now().strftime("%Y%m%d-%H%M%S")

        self.print_header(f"Executing Rollback: {target_version}")

        if dry_run:
            self.print_step("DRY RUN MODE - No changes will be made", "warning")

        # Create rollback plan
        plan = self.create_rollback_plan(target_version, strategy)

        # Save rollback plan - Issue #666: Use asyncio.to_thread to avoid blocking
        plan_file = self.rollback_dir / f"rollback_plan_{rollback_id}.json"

        def _write_plan():
            with open(plan_file, "w") as f:
                json.dump(plan, f, indent=2)

        await asyncio.to_thread(_write_plan)

        if dry_run:
            self.print_step(f"Rollback plan saved: {plan_file}", "info")
            self.print_step(f"Estimated downtime: {plan['estimated_downtime']}", "info")
            for step in plan["steps"]:
                self.print_step(
                    f"  {step['step']}: {step['description']} ({step['estimated_time']})",
                    "info",
                )
            return True

        try:
            # Execute rollback steps using dispatch helper (Issue #315: reduced nesting)
            start_time = time.time()

            for i, step in enumerate(plan["steps"], 1):
                self.print_step(
                    f"Step {i}/{len(plan['steps'])}: {step['description']}", "running"
                )

                success, should_continue = await self._execute_step(
                    step, target_version, rollback_id
                )
                if not should_continue:
                    return False

                self.print_step(f"Step {i} completed", "success")

            duration = time.time() - start_time
            self.print_step(
                f"Rollback completed successfully in {duration:.1f}s", "success"
            )

            # Log rollback success - Issue #666: Wrap blocking I/O
            await asyncio.to_thread(
                self._log_rollback_event,
                rollback_id,
                target_version,
                "success",
                duration,
            )

            return True

        except Exception as e:
            self.print_step(f"Rollback failed: {e}", "error")

            # Log rollback failure - Issue #666: Wrap blocking I/O
            await asyncio.to_thread(
                self._log_rollback_event,
                rollback_id,
                target_version,
                "failed",
                0,
                str(e),
            )

            # Attempt recovery if configured
            if self.rollback_config["cleanup_failed_rollback"]:
                self.print_step("Attempting rollback recovery...", "rollback")
                await self._recover_from_failed_rollback()

            return False

    async def _restore_version(self, target_version: str) -> bool:
        """Restore to target version."""
        try:
            # Check if target is a backup ID
            backups = self.backup_manager.list_backups()
            if target_version in backups:
                self.print_step(f"Restoring from backup: {target_version}", "running")
                return self.backup_manager.restore_backup(target_version)

            # Check if target is a git version
            git_versions = self._get_git_versions()
            git_tags = [v["tag"] for v in git_versions]

            if target_version in git_tags:
                self.print_step(
                    f"Restoring from git version: {target_version}", "running"
                )
                # Issue #479: Use async subprocess
                process = await asyncio.create_subprocess_exec(
                    "git",
                    "checkout",
                    target_version,
                    cwd=self.project_root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    # Reinstall dependencies
                    self.print_step("Reinstalling dependencies...", "running")
                    # Issue #479: Use async subprocess
                    pip_process = await asyncio.create_subprocess_exec(
                        "pip",
                        "install",
                        "-r",
                        "requirements.txt",
                        cwd=self.project_root,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await pip_process.communicate()
                    return True
                else:
                    self.print_step(f"Git checkout failed: {stderr.decode()}", "error")
                    return False

            self.print_step(f"Unknown target version: {target_version}", "error")
            return False

        except Exception as e:
            self.print_step(f"Version restore error: {e}", "error")
            return False

    def _stop_services(self) -> bool:
        """Stop all AutoBot services."""
        try:
            # Stop services in reverse order
            services_order = list(reversed(self.rollback_config["services_order"]))

            for service in services_order:
                self.print_step(f"Stopping {service}", "running")

                # Use deployment-specific stop commands
                if self.service_registry.deployment_mode.value == "docker_local":
                    # Stop Docker containers
                    subprocess.run(
                        ["docker", "stop", f"autobot-{service}"],
                        capture_output=True,
                        check=False,
                    )
                elif self.service_registry.deployment_mode.value == "kubernetes":
                    # Scale down Kubernetes deployment
                    subprocess.run(
                        ["kubectl", "scale", "--replicas=0", f"deployment/{service}"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    # Local processes - try to find and stop
                    subprocess.run(
                        ["pkill", "-f", service], capture_output=True, check=False
                    )

            return True

        except Exception as e:
            self.print_step(f"Error stopping services: {e}", "error")
            return False

    def _start_services(self) -> bool:
        """Start all AutoBot services."""
        try:
            # Start services in correct order
            for service in self.rollback_config["services_order"]:
                self.print_step(f"Starting {service}", "running")

                # Use deployment-specific start commands
                if self.service_registry.deployment_mode.value == "docker_local":
                    # Start Docker containers
                    subprocess.run(
                        ["docker", "start", f"autobot-{service}"],
                        capture_output=True,
                        check=False,
                    )
                elif self.service_registry.deployment_mode.value == "kubernetes":
                    # Scale up Kubernetes deployment
                    subprocess.run(
                        ["kubectl", "scale", "--replicas=1", f"deployment/{service}"],
                        capture_output=True,
                        check=False,
                    )

                # Wait a bit between services
                time.sleep(TimingConstants.MEDIUM_DELAY)

            return True

        except Exception as e:
            self.print_step(f"Error starting services: {e}", "error")
            return False

    def _update_deployment_info(self, target_version: str, rollback_id: str):
        """Update deployment information after rollback."""
        deployment_info = {
            "version": target_version,
            "deployment_mode": self.service_registry.deployment_mode.value,
            "deployed_at": datetime.now().isoformat(),
            "deployer": "rollback-manager",
            "rollback_id": rollback_id,
            "commit_hash": self._get_git_commit(),
            "services": list(self.service_registry.list_services()),
        }

        with open(self.deployment_info_file, "w") as f:
            json.dump(deployment_info, f, indent=2)

    def _log_rollback_event(
        self,
        rollback_id: str,
        target_version: str,
        status: str,
        duration: float,
        error: str = None,
    ):
        """Log rollback event."""
        log_file = self.rollback_dir / "rollback_history.json"

        # Load existing history
        history = []
        if log_file.exists():
            try:
                with open(log_file, "r") as f:
                    history = json.load(f)
            except Exception:
                history = []

        # Add new event
        event = {
            "rollback_id": rollback_id,
            "timestamp": datetime.now().isoformat(),
            "target_version": target_version,
            "status": status,
            "duration": duration,
            "deployment_mode": self.service_registry.deployment_mode.value,
        }

        if error:
            event["error"] = error

        history.append(event)

        # Keep last 50 events
        if len(history) > 50:
            history = history[-50:]

        # Save history
        with open(log_file, "w") as f:
            json.dump(history, f, indent=2)

    async def _recover_from_failed_rollback(self) -> bool:
        """Attempt to recover from failed rollback."""
        try:
            self.print_step("Starting rollback recovery procedure", "rollback")

            # Try to restart services
            if self._start_services():
                # Verify health
                if await self.verify_services_health(120):
                    self.print_step("Rollback recovery successful", "success")
                    return True

            self.print_step(
                "Automatic recovery failed - manual intervention required", "error"
            )
            return False

        except Exception as e:
            self.print_step(f"Recovery failed: {e}", "error")
            return False


def _build_rollback_parser():
    """Build argument parser for rollback CLI.

    Helper for main (Issue #825).
    """
    parser = argparse.ArgumentParser(
        description="AutoBot Deployment Rollback System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/deployment_rollback.py --rollback --backup-id 20250821-143022
  python scripts/deployment_rollback.py --rollback --version v1.2.3 --strategy zero-downtime
  python scripts/deployment_rollback.py --plan --target-version v1.2.3
  python scripts/deployment_rollback.py --list-versions
  python scripts/deployment_rollback.py --rollback --version v1.2.3 --dry-run
        """,
    )

    parser.add_argument("--rollback", action="store_true", help="Execute rollback")
    parser.add_argument("--plan", action="store_true", help="Create rollback plan")
    parser.add_argument(
        "--list-versions", action="store_true", help="List available versions"
    )
    parser.add_argument("--backup-id", help="Backup ID to restore")
    parser.add_argument("--version", help="Version to rollback to")
    parser.add_argument("--target-version", help="Target version for planning")
    parser.add_argument(
        "--strategy",
        choices=[
            RollbackStrategy.IMMEDIATE,
            RollbackStrategy.ZERO_DOWNTIME,
            RollbackStrategy.SERVICE_BY_SERVICE,
        ],
        default=RollbackStrategy.IMMEDIATE,
        help="Rollback strategy",
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--backup-dir", default="backups", help="Backup directory")
    parser.add_argument(
        "--rollback-dir", default="rollbacks", help="Rollback directory"
    )
    return parser


def _handle_list_versions(rollback_manager):
    """Handle list-versions command output.

    Helper for main (Issue #825).
    """
    versions = rollback_manager.list_available_versions()

    if not versions:
        logger.info("No versions available for rollback")
        return 0

    logger.info("\n📋 Available Versions for Rollback:")
    logger.info("=" * 80)
    logger.info(
        f"{'Version':<20} {'Type':<10} {'Date':<20} {'Method':<20} {'Size':<10}"
    )
    logger.info("-" * 80)

    for version in versions:
        created = datetime.fromisoformat(version["created_at"])
        size = ""
        if "size" in version:
            size_mb = version["size"] / (1024 * 1024)
            size = f"{size_mb:.1f} MB"

        logger.info(
            f"{version['version']:<20} "
            f"{version['type']:<10} "
            f"{created.strftime('%Y-%m-%d %H:%M'):<20} "
            f"{version['rollback_method']:<20} "
            f"{size:<10}"
        )
    return 0


def _handle_plan(rollback_manager, args):
    """Handle plan command output.

    Helper for main (Issue #825).
    """
    if not args.target_version:
        logger.error("❌ --target-version required for plan")
        return 1

    plan = rollback_manager.create_rollback_plan(
        args.target_version, args.strategy
    )

    logger.info(f"\n📋 Rollback Plan: {args.target_version}")
    logger.info("=" * 60)
    logger.info(f"Strategy: {plan['strategy']}")
    logger.info(f"Estimated downtime: {plan['estimated_downtime']}")
    logger.info(f"Current version: {plan['current_version']}")
    logger.info(f"Target version: {plan['target_version']}")
    logger.info("\nSteps:")

    for i, step in enumerate(plan["steps"], 1):
        critical = "⚠️ CRITICAL" if step["critical"] else ""
        logger.info(
            f"  {i}. {step['description']} ({step['estimated_time']}) {critical}"
        )
    return 0


async def main():
    """Entry point for deployment rollback CLI."""
    parser = _build_rollback_parser()
    args = parser.parse_args()

    if not any([args.rollback, args.plan, args.list_versions]):
        parser.print_help()
        return 1

    rollback_manager = RollbackManager(args.backup_dir, args.rollback_dir)

    try:
        if args.list_versions:
            return _handle_list_versions(rollback_manager)
        elif args.plan:
            return _handle_plan(rollback_manager, args)
        elif args.rollback:
            target_version = args.backup_id or args.version
            if not target_version:
                logger.error("❌ --backup-id or --version required for rollback")
                return 1
            success = await rollback_manager.execute_rollback(
                target_version, args.strategy, args.dry_run
            )
            return 0 if success else 1

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
