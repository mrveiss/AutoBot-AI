# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward-compatibility shim for services.slm.deployment_orchestrator.

Issue #5040: Module renamed to deployment_bridge.py.
All names re-exported here so existing imports continue to work.
"""

from .deployment_bridge import (  # noqa: F401
    DeploymentContext,
    DeploymentCoordinator as DeploymentOrchestrator,
    DeploymentCoordinator,
    DeploymentStatus,
    DeploymentStep,
    DeploymentStepType,
    SLMDeploymentBridge as SLMDeploymentOrchestrator,
    SLMDeploymentBridge,
    get_orchestrator,
    init_orchestrator,
)
