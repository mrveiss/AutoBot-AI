# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
    OverseerUpdate,
    StepResult,
    StepStatus,
    StreamChunk,
    TaskPlan,
    TaskStatus,
)

__all__ = [
    # Types
    "TaskStatus",
    "StepStatus",
    "CommandBreakdownPart",
    "CommandExplanation",
    "OutputExplanation",
    "AgentTask",
    "TaskPlan",
    "StepResult",
    "StreamChunk",
    "OverseerUpdate",
    # Agents
    "OverseerAgent",
    "StepExecutorAgent",
    # Services
    "CommandExplanationService",
    "get_command_explanation_service",
]
