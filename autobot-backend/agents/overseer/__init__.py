# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Overseer Agent Package

Provides task decomposition, step-by-step execution, and automatic
command explanations for terminal operations in chat.
"""

from .command_explanation_service import (
    CommandExplanationService,
    get_command_explanation_service,
)
from .overseer_agent import OverseerAgent
from .step_executor_agent import StepExecutorAgent
from .types import (
    AgentTask,
    CommandBreakdownPart,
    CommandExplanation,
    OutputExplanation,
    OverseerStepStatus,
    OverseerTaskStatus,
    OverseerUpdate,
    StepChunk,
    StepRunResult,
    TaskPlan,
)

__all__ = [
    # Types
    "OverseerTaskStatus",
    "OverseerStepStatus",
    "CommandBreakdownPart",
    "CommandExplanation",
    "OutputExplanation",
    "AgentTask",
    "TaskPlan",
    "StepRunResult",
    "StepChunk",
    "OverseerUpdate",
    # Agents
    "OverseerAgent",
    "StepExecutorAgent",
    # Services
    "CommandExplanationService",
    "get_command_explanation_service",
]
