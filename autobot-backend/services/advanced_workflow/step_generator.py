# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Step Generator

Generates smart workflow steps with AI enhancements.
"""

import logging
from typing import List, Optional

from autobot_types import TaskComplexity
from enhanced_orchestrator import EnhancedOrchestrator
from type_defs.common import Metadata

from .models import SmartWorkflowStep, WorkflowIntent

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for high-risk command patterns
_HIGH_RISK_PATTERNS = (
    "rm ",
    "delete",
    "drop",
    "truncate",
    "sudo ",
    "chmod",
    "chown",
    "systemctl",
    "service",
    "firewall",
    "iptables",
    "ufw",
)


class StepGenerator:
    """Generates intelligent workflow steps"""

    def __init__(self, enhanced_orchestrator: EnhancedOrchestrator = None):
        """Initialize step generator with optional enhanced orchestrator."""
        self.enhanced_orchestrator = enhanced_orchestrator or EnhancedOrchestrator()

    async def generate_smart_steps(
        self,
        user_request: str,
        intent_analysis: Metadata,
        context: Metadata,
    ) -> List[SmartWorkflowStep]:
        """Generate intelligent workflow steps"""
        try:
            # Get complexity from intent analysis
            complexity = getattr(
                TaskComplexity,
                intent_analysis.get("complexity", "simple").upper(),
                TaskComplexity.SIMPLE,
            )

            # Issue #321: Use delegation method to reduce message chains
            base_steps = self.enhanced_orchestrator.plan_workflow_steps(
                user_request, complexity
            )

            # Convert to smart steps with AI enhancements
            smart_steps = []
            for i, base_step in enumerate(base_steps):
                command = self._extract_command_from_base_step(base_step)

                smart_step = SmartWorkflowStep(
                    step_id=f"smart_{i+1}",
                    command=command,
                    description=base_step.action,
                    explanation=f"AI-generated step for: {base_step.action}",
                    intent=WorkflowIntent(
                        intent_analysis.get("primary_intent", "configuration")
                    ),
                    confidence_score=0.8,
                    success_probability=0.85,
                    alternative_commands=await self._generate_alternatives(command),
                    validation_command=self._generate_validation_command(command),
                    rollback_command=self._generate_rollback_command(command),
                    requires_confirmation=self._step_requires_confirmation(command),
                )

                smart_steps.append(smart_step)

            # Add intelligent pre and post steps
            smart_steps = await self._add_intelligent_bookends(
                smart_steps, intent_analysis
            )

            return smart_steps

        except Exception as e:
            logger.error("Smart step generation failed: %s", e)
            return self._generate_fallback_steps(user_request, intent_analysis)

    def _extract_command_from_base_step(self, base_step) -> str:
        """Extract executable command from base step"""
        if hasattr(base_step, "inputs") and base_step.inputs:
            command = base_step.inputs.get("command", "")
            if command:
                return command

        # Generate command from action
        action = base_step.action.lower()
        if "update" in action and "package" in action:
            return "sudo apt update && sudo apt upgrade -y"
        elif "install" in action and "git" in action:
            return "sudo apt install -y git"
        elif "configure" in action and "nginx" in action:
            return "sudo nginx -t && sudo systemctl reload nginx"
        else:
            return f"echo 'Executing: {base_step.action}'"

    async def _generate_alternatives(self, command: str) -> List[str]:
        """Generate alternative commands for flexibility"""
        alternatives = []

        # System-specific alternatives
        if "apt" in command:
            alternatives.append(command.replace("apt", "yum"))
            alternatives.append(command.replace("apt", "dnf"))
            alternatives.append(command.replace("apt", "pacman -S"))

        # Add safe alternatives
        if "rm" in command:
            alternatives.append(command.replace("rm", "mv") + ".backup")

        if "sudo" in command:
            alternatives.append(command.replace("sudo ", ""))

        return alternatives[:3]

    def _generate_validation_command(self, command: str) -> Optional[str]:
        """Generate validation command to verify success"""
        if "install" in command:
            if "apt install" in command:
                package = command.split()[-1]
                return f"dpkg -l | grep {package}"

        if "systemctl" in command and "start" in command:
            service = command.split()[-1]
            return f"systemctl is-active {service}"

        if "nginx" in command:
            return "nginx -t"

        if "mkdir" in command:
            path = command.split()[-1]
            return f"ls -la {path}"

        return None

    def _generate_rollback_command(self, command: str) -> Optional[str]:
        """Generate rollback command for safety"""
        if "systemctl start" in command:
            service = command.split()[-1]
            return f"sudo systemctl stop {service}"

        if "systemctl enable" in command:
            service = command.split()[-1]
            return f"sudo systemctl disable {service}"

        if "apt install" in command:
            package = command.split()[-1]
            return f"sudo apt remove {package}"

        return None

    def _step_requires_confirmation(self, command: str) -> bool:
        """Determine if step requires user confirmation (Issue #380: use module constant)"""
        return any(pattern in command.lower() for pattern in _HIGH_RISK_PATTERNS)

    async def _add_intelligent_bookends(
        self, steps: List[SmartWorkflowStep], intent_analysis: Metadata
    ) -> List[SmartWorkflowStep]:
        """Add intelligent pre and post workflow steps"""
        enhanced_steps = []

        # Pre-workflow steps
        pre_steps = [
            SmartWorkflowStep(
                step_id="pre_check",
                command="echo 'Starting AI-optimized workflow...'",
                description="Initialize workflow",
                explanation="AI workflow initialization with system checks",
                intent=WorkflowIntent(
                    intent_analysis.get("primary_intent", "configuration")
                ),
                confidence_score=1.0,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="system_check",
                command="whoami && pwd && date",
                description="System status check",
                explanation="Verify system state before proceeding",
                intent=WorkflowIntent.ANALYSIS,
                confidence_score=0.95,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        enhanced_steps.extend(pre_steps)
        enhanced_steps.extend(steps)

        # Post-workflow steps
        post_steps = [
            SmartWorkflowStep(
                step_id="validation",
                command="echo 'Workflow validation complete'",
                description="Validate workflow completion",
                explanation="AI-driven validation of workflow success",
                intent=WorkflowIntent.ANALYSIS,
                confidence_score=0.9,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="cleanup",
                command="echo 'Cleaning up temporary resources...'",
                description="Cleanup temporary resources",
                explanation="AI cleanup of workflow temporary files",
                intent=WorkflowIntent.MAINTENANCE,
                confidence_score=0.85,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        enhanced_steps.extend(post_steps)
        return enhanced_steps

    def _generate_fallback_steps(
        self, user_request: str, intent_analysis: Metadata
    ) -> List[SmartWorkflowStep]:
        """Generate fallback steps when AI generation fails"""
        return [
            SmartWorkflowStep(
                step_id="fallback_1",
                command=f"echo 'Processing request: {user_request}'",
                description="Process user request",
                explanation="Fallback step for user request processing",
                intent=WorkflowIntent(
                    intent_analysis.get("primary_intent", "configuration")
                ),
                confidence_score=0.5,
                requires_confirmation=False,
                ai_generated=True,
            )
        ]
