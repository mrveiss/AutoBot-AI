# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Optimizer

AI-driven workflow optimization strategies.
"""

import logging
from typing import List

from type_defs.common import Metadata

from .models import SmartWorkflowStep, WorkflowIntent

logger = logging.getLogger(__name__)


class WorkflowOptimizer:
    """Applies AI-driven optimizations to workflow steps"""

    async def apply_optimizations(
        self, steps: List[SmartWorkflowStep], intent_analysis: Metadata
    ) -> List[SmartWorkflowStep]:
        """Apply AI-driven optimizations to workflow steps"""
        optimized_steps = steps.copy()

        # Optimization 1: Parallel execution opportunities
        optimized_steps = await self._optimize_parallel_execution(optimized_steps)

        # Optimization 2: Redundancy elimination
        optimized_steps = await self._eliminate_redundancies(optimized_steps)

        # Optimization 3: Command consolidation
        optimized_steps = await self._consolidate_commands(optimized_steps)

        # Optimization 4: Risk reduction
        optimized_steps = await self._apply_risk_reduction(optimized_steps)

        return optimized_steps

    async def _optimize_parallel_execution(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Identify steps that can run in parallel"""
        for step in steps:
            if not step.dependencies and "install" not in step.command:
                step.learning_metadata["parallel_safe"] = True

        return steps

    async def _eliminate_redundancies(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Remove redundant steps"""
        seen_commands = set()
        optimized_steps = []

        for step in steps:
            command_signature = step.command.strip().lower()
            if command_signature not in seen_commands:
                seen_commands.add(command_signature)
                optimized_steps.append(step)
            else:
                logger.info("Eliminated redundant step: %s", step.command)

        return optimized_steps

    async def _consolidate_commands(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Consolidate related commands for efficiency"""
        consolidated_steps = []
        apt_installs = []

        for step in steps:
            if "apt install" in step.command and step.command.count("apt install") == 1:
                # Collect apt install commands for consolidation
                package = step.command.split()[-1]
                apt_installs.append((step, package))
            else:
                consolidated_steps.append(step)

        # Create consolidated apt install command
        if apt_installs:
            packages = [pkg for _, pkg in apt_installs]
            consolidated_command = f"sudo apt install -y {' '.join(packages)}"

            consolidated_step = SmartWorkflowStep(
                step_id="consolidated_install",
                command=consolidated_command,
                description=f"Install packages: {', '.join(packages)}",
                explanation="AI-consolidated package installation for efficiency",
                intent=WorkflowIntent.INSTALLATION,
                confidence_score=0.9,
                requires_confirmation=True,
                ai_generated=True,
                learning_metadata={
                    "optimization": "command_consolidation",
                    "original_count": len(apt_installs),
                },
            )

            consolidated_steps.insert(0, consolidated_step)

        return consolidated_steps

    async def _apply_risk_reduction(
        self, steps: List[SmartWorkflowStep]
    ) -> List[SmartWorkflowStep]:
        """Apply risk reduction strategies"""
        for step in steps:
            # Add backup steps for risky operations
            if "rm " in step.command and not step.rollback_command:
                step.rollback_command = "echo 'Backup would be restored here'"

            # Add validation for system changes
            if "systemctl" in step.command and not step.validation_command:
                service = step.command.split()[-1]
                step.validation_command = f"systemctl status {service}"

            # Reduce sudo usage where possible
            if step.command.startswith("sudo echo"):
                step.command = step.command.replace("sudo ", "")
                step.learning_metadata["risk_reduction"] = "removed_unnecessary_sudo"

        return steps
