# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Advanced Workflow Module

AI-driven workflow orchestration with intelligent step generation,
optimization, and learning capabilities.
"""

from .coordinator import WorkflowCoordinator
from .intent_analyzer import IntentAnalyzer
from .learning_engine import WorkflowLearningEngine
from .models import (
    AdaptiveMode,
    SmartWorkflowStep,
    SmartWorkflowTemplate,
    WorkflowComplexity,
    WorkflowIntelligence,
    WorkflowIntent,
)
from .optimizer import WorkflowOptimizer
from .risk_analyzer import RiskAnalyzer
from .routes import get_orchestrator_instance, router
from .step_generator import StepGenerator
from .templates import TemplateManager

__all__ = [
    # Main coordinator
    "WorkflowCoordinator",
    # Models
    "WorkflowComplexity",
    "AdaptiveMode",
    "WorkflowIntent",
    "WorkflowIntelligence",
    "SmartWorkflowStep",
    "SmartWorkflowTemplate",
    # Components
    "TemplateManager",
    "IntentAnalyzer",
    "StepGenerator",
    "WorkflowOptimizer",
    "RiskAnalyzer",
    "WorkflowLearningEngine",
    # Routes
    "router",
    "get_orchestrator_instance",
]
