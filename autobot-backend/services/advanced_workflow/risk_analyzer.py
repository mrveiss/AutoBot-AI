# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Risk Analyzer

Risk assessment and mitigation strategies for workflows.
"""

import logging
from typing import List

from .models import (
    CRITICAL_RISK_PATTERNS,
    HIGH_RISK_PATTERNS,
    MODERATE_RISK_PATTERNS,
    SmartWorkflowStep,
)

logger = logging.getLogger(__name__)


class RiskAnalyzer:
    """Analyzes and mitigates workflow risks"""

    def assess_step_risk_level(self, command: str) -> str:
        """Assess risk level for a command"""
        command_lower = command.lower()

        if any(pattern in command_lower for pattern in CRITICAL_RISK_PATTERNS):
            return "critical"
        elif any(pattern in command_lower for pattern in HIGH_RISK_PATTERNS):
            return "high"
        elif any(pattern in command_lower for pattern in MODERATE_RISK_PATTERNS):
            return "moderate"
        else:
            return "low"

    async def generate_optimization_suggestions(
        self, steps: List[SmartWorkflowStep]
    ) -> List[str]:
        """Generate AI optimization suggestions"""
        suggestions = []

        # Check for common optimization opportunities
        install_steps = [s for s in steps if "install" in s.command]
        if len(install_steps) > 2:
            suggestions.append(
                "Consider consolidating package installations for faster execution"
            )

        sudo_steps = [s for s in steps if "sudo" in s.command]
        if len(sudo_steps) > len(steps) * 0.7:
            suggestions.append(
                "High privilege usage detected - consider running as elevated user"
            )

        validation_missing = [
            s for s in steps if not s.validation_command and s.requires_confirmation
        ]
        if validation_missing:
            suggestions.append("Add validation commands to verify step success")

        return suggestions

    async def generate_risk_mitigation(
        self, steps: List[SmartWorkflowStep]
    ) -> List[str]:
        """Generate risk mitigation strategies"""
        strategies = []

        high_risk_steps = [s for s in steps if s.requires_confirmation]
        if high_risk_steps:
            strategies.append(
                "Create system backup before executing high-risk operations"
            )
            strategies.append("Test workflow in development environment first")

        if any("rm " in s.command for s in steps):
            strategies.append("Verify file paths before deletion operations")

        if any("firewall" in s.command or "iptables" in s.command for s in steps):
            strategies.append(
                "Ensure remote access recovery method before firewall changes"
            )

        return strategies

    def estimate_workflow_duration(self, steps: List[SmartWorkflowStep]) -> float:
        """Estimate total workflow duration in seconds"""
        total_time = 0.0

        for step in steps:
            if "install" in step.command:
                total_time += 30.0
            elif "systemctl" in step.command:
                total_time += 5.0
            elif "echo" in step.command:
                total_time += 1.0
            else:
                total_time += 10.0

        return total_time

    def calculate_workflow_confidence(self, steps: List[SmartWorkflowStep]) -> float:
        """Calculate overall workflow confidence score"""
        if not steps:
            return 0.0

        total_confidence = sum(step.confidence_score for step in steps)
        return min(total_confidence / len(steps), 1.0)
