# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fallback stubs for optional orchestrator dependencies.

Extracted from orchestrator.py (#5060).  Import this module and use the
availability flags instead of duplicating try/except blocks in the main
orchestrator.
"""

from dataclasses import dataclass

try:
    from agents.gemma_classification_agent import GemmaClassificationAgent

    CLASSIFICATION_AVAILABLE = True
except ImportError:
    CLASSIFICATION_AVAILABLE = False

try:
    from agents.agent_manager import AgentManager

    AGENT_MANAGER_AVAILABLE = True
except ImportError:
    AGENT_MANAGER_AVAILABLE = False

    class AgentManager:  # type: ignore[no-redef]
        async def initialize(self):
            """Initialize placeholder — no-op when unavailable."""

        async def cleanup(self):
            """Cleanup placeholder — no-op when unavailable."""

        async def execute_agent_task(self, agent_name, task, context=None):
            return {"error": "Agent manager not available", "agent_name": agent_name}


try:
    from workflow_templates import WorkflowStep

    WORKFLOW_TYPES_AVAILABLE = True
except ImportError:
    WORKFLOW_TYPES_AVAILABLE = False

    @dataclass
    class WorkflowStep:  # type: ignore[no-redef]
        id: str
        agent_type: str
        action: str
        description: str


__all__ = [
    "AgentManager",
    "AGENT_MANAGER_AVAILABLE",
    "GemmaClassificationAgent",
    "CLASSIFICATION_AVAILABLE",
    "WorkflowStep",
    "WORKFLOW_TYPES_AVAILABLE",
]
