# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model Optimization Package

Issue #381: Extracted from model_optimizer.py god class refactoring.
Provides intelligent model selection and performance optimization.

- types.py: Enums, dataclasses (TaskComplexity, ModelInfo, TaskRequest, etc.)
- system_resources.py: System resource analysis for model selection
- performance_tracking.py: Model performance tracking and Redis persistence
- model_selection.py: Model filtering and selection logic
"""

from .model_selection import ModelClassifier, ModelSelector
from .performance_tracking import ModelPerformanceTracker
from .system_resources import SystemResourceAnalyzer
from .types import (
    CODE_COMPLEXITY_KEYWORDS,
    CODE_TASK_TYPES,
    ModelInfo,
    ModelPerformanceLevel,
    SystemResources,
    TaskComplexity,
    TaskRequest,
)

__all__ = [
    # Types and enums
    "TaskComplexity",
    "ModelPerformanceLevel",
    "SystemResources",
    "TaskRequest",
    "ModelInfo",
    # Constants
    "CODE_TASK_TYPES",
    "CODE_COMPLEXITY_KEYWORDS",
    # Analyzers and selectors
    "SystemResourceAnalyzer",
    "ModelPerformanceTracker",
    "ModelSelector",
    "ModelClassifier",
]
