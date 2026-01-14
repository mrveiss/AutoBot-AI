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

__all__ = [
    "SLMStateMachine",
    "InvalidStateTransition",
    "VALID_TRANSITIONS",
]
