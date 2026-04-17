# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward-compatibility shim for services.advanced_workflow.orchestrator.

Issue #5040: Module renamed to coordinator.py.
All names re-exported here so existing imports continue to work.
"""

from .coordinator import WorkflowCoordinator as AdvancedWorkflowOrchestrator  # noqa: F401
from .coordinator import WorkflowCoordinator  # noqa: F401
