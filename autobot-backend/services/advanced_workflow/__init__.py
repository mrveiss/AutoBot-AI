# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Workflow Module

AI-driven workflow orchestration with intelligent step generation,
optimization, and learning capabilities.
"""

from .intent_analyzer import IntentAnalyzer
from .learning_engine import WorkflowLearningEngine
from .models import (
    AdaptiveMode,
    SmartWorkflowStep,
    WorkflowComplexity,
    WorkflowIntelligence,
    WorkflowIntent,
    WorkflowTemplate,
)
from .optimizer import WorkflowOptimizer
from .orchestrator import AdvancedWorkflowOrchestrator
from .risk_analyzer import RiskAnalyzer
from .routes import get_orchestrator_instance, router
from .step_generator import StepGenerator
from .templates import TemplateManager

__all__ = [
    # Main orchestrator
    "AdvancedWorkflowOrchestrator",
    # Models
    "WorkflowComplexity",
    "AdaptiveMode",
    "WorkflowIntent",
    "WorkflowIntelligence",
    "SmartWorkflowStep",
    "WorkflowTemplate",
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
