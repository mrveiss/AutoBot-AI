# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Lifecycle Manager (SLM) Package

Provides orchestration for AutoBot's distributed VM fleet including:
- Node state machine management
- Health monitoring and reconciliation
- Deployment orchestration
- Maintenance scheduling
"""

from backend.services.slm.state_machine import (
    SLMStateMachine,
    InvalidStateTransition,
    VALID_TRANSITIONS,
)
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.reconciler import (
    SLMReconciler,
    get_reconciler,
    start_reconciler,
    stop_reconciler,
)
from backend.services.slm.remediator import (
    SLMRemediator,
    SSHExecutor,
    RemediationAction,
    RemediationResult,
    get_remediator,
)

__all__ = [
    "SLMStateMachine",
    "InvalidStateTransition",
    "VALID_TRANSITIONS",
    "SLMDatabaseService",
    "SLMReconciler",
    "get_reconciler",
    "start_reconciler",
    "stop_reconciler",
    "SLMRemediator",
    "SSHExecutor",
    "RemediationAction",
    "RemediationResult",
    "get_remediator",
]
