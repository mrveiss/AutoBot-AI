# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Automation Module

Refactored from backend/api/workflow_automation.py (Issue #290)
Original: 1,225 lines, 21+ methods in single WorkflowAutomationManager class
Refactored: 8 focused modules following Single Responsibility Principle

Module Structure:
- models.py: Enums, dataclasses, Pydantic models (100 lines)
- templates.py: Pre-defined workflow templates (150 lines)
- step_evaluator.py: LLM judge integration (180 lines)
- messaging.py: WebSocket communication (50 lines)
- executor.py: Step execution and processing (280 lines)
- controller.py: Workflow control actions (110 lines)
- manager.py: Main coordinator using composition (180 lines)
- routes.py: FastAPI endpoints (230 lines)

Total: ~1,280 lines (slight increase for proper separation)
"""

from .concurrent_limiter import (
    ConcurrencyLimitError,
    ConcurrentWorkflowLimiter,
    OverflowPolicy,
    get_concurrent_limiter,
)
from .controller import WorkflowController
from .executor import WorkflowExecutor
from .manager import WorkflowAutomationManager
from .messaging import WorkflowMessenger
from .models import (
    ActiveWorkflow,
    AutomatedWorkflowRequest,
    AutomationMode,
    WorkflowControlRequest,
    WorkflowStep,
    WorkflowStepRequest,
    WorkflowStepStatus,
)
from .routes import get_workflow_manager, router
from .safety_limits import (
    CostTracker,
    StepTimeoutEnforcer,
    StepTimeoutError,
    WorkflowLimits,
)
from .step_evaluator import WorkflowStepEvaluator
from .templates import WorkflowTemplateManager

__all__ = [
    # Main Manager
    "WorkflowAutomationManager",
    "get_workflow_manager",
    # Router
    "router",
    # Models
    "WorkflowStepStatus",
    "AutomationMode",
    "WorkflowStep",
    "ActiveWorkflow",
    "WorkflowStepRequest",
    "AutomatedWorkflowRequest",
    "WorkflowControlRequest",
    # Components
    "WorkflowMessenger",
    "WorkflowExecutor",
    "WorkflowController",
    "WorkflowStepEvaluator",
    "WorkflowTemplateManager",
    # Issue #2159: Safety limits
    "WorkflowLimits",
    "CostTracker",
    "StepTimeoutEnforcer",
    "StepTimeoutError",
    # Issue #2159: Concurrent limiter
    "ConcurrentWorkflowLimiter",
    "ConcurrencyLimitError",
    "OverflowPolicy",
    "get_concurrent_limiter",
]
