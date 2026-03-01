# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Automation — Backward Compatibility Shim

Issue #1285: Consolidated into services/workflow_automation/ (8-module architecture).
This shim re-exports public symbols so existing imports continue to work.
New code should import directly from services.workflow_automation.
"""

# Re-export all public symbols from the services/ implementation
from services.workflow_automation.manager import WorkflowAutomationManager
from services.workflow_automation.models import (
    ActiveWorkflow,
    AutomatedWorkflowRequest,
    AutomationMode,
    WorkflowControlRequest,
    WorkflowStep,
    WorkflowStepRequest,
    WorkflowStepStatus,
)
from services.workflow_automation.routes import get_workflow_manager, router

# Backward compatibility: some callers expect module-level `workflow_manager`
workflow_manager = get_workflow_manager()

__all__ = [
    "WorkflowAutomationManager",
    "WorkflowStepStatus",
    "AutomationMode",
    "WorkflowStep",
    "ActiveWorkflow",
    "WorkflowStepRequest",
    "AutomatedWorkflowRequest",
    "WorkflowControlRequest",
    "workflow_manager",
    "get_workflow_manager",
    "router",
]
