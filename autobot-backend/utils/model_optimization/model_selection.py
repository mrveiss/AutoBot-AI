# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model Selection Module

Issue #381: Extracted from model_optimizer.py god class refactoring.
Contains model filtering and selection logic.
"""

import logging
from typing import List

from .types import (ModelInfo, ModelPerformanceLevel, SystemResources,
                    TaskComplexity, TaskRequest)

logger = logging.getLogger(__name__)


class ModelSelector:
    """Handles model filtering and selection logic (Tell Don't Ask)."""

    def __init__(self, min_samples: int):
        """Initialize selector with minimum sample threshold."""
        self._min_samples = min_samples

    def filter_by_complexity(
        self, models: List[ModelInfo], complexity: TaskComplexity
    ) -> List[ModelInfo]:
        """Filter models based on task complexity requirements."""
        filtered = [m for m in models if m.meets_complexity_requirement(complexity)]

        # For SPECIALIZED complexity, prefer advanced models but fall back
        if complexity == TaskComplexity.SPECIALIZED and not filtered:
            return models

        return filtered if filtered else models

    def filter_by_resources(
        self, models: List[ModelInfo], resources: SystemResources
    ) -> List[ModelInfo]:
        """Filter models based on available system resources."""
        return [m for m in models if m.fits_resource_constraints(resources)]

    def rank_by_performance(
        self, models: List[ModelInfo], task_request: TaskRequest
    ) -> List[ModelInfo]:
        """Rank models by expected performance for the task."""
        # Let each model calculate its own score
        scored_models = [
            (model, model.calculate_score(task_request, self._min_samples))
            for model in models
        ]

        # Sort by score (descending)
        scored_models.sort(key=lambda x: x[1], reverse=True)

        return [model for model, score in scored_models]


class ModelClassifier:
    """Handles model classification by performance level."""

    def __init__(self, classifications: dict):
        """Initialize with model classifications mapping."""
        self._classifications = classifications

    def classify_by_explicit_name(self, name: str) -> ModelPerformanceLevel | None:
        """Classify model by explicit name match (Issue #315 - extracted helper)."""
        for level, models in self._classifications.items():
            if any(model_name in name for model_name in models):
                return level
        return None

    def classify_by_parameter_size(
        self, parameter_size: str
    ) -> ModelPerformanceLevel | None:
        """Classify model by parameter size (Issue #315 - extracted helper)."""
        try:
            if "M" in parameter_size:
                param_num = float(parameter_size.replace("M", ""))
                if param_num < 2000:
                    return ModelPerformanceLevel.LIGHTWEIGHT
            elif "B" in parameter_size:
                param_num = float(parameter_size.replace("B", ""))
                if param_num < 2:
                    return ModelPerformanceLevel.LIGHTWEIGHT
                if param_num < 8:
                    return ModelPerformanceLevel.STANDARD
                return ModelPerformanceLevel.ADVANCED
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)
        return None

    def classify_model_performance(
        self, name: str, parameter_size: str
    ) -> ModelPerformanceLevel:
        """Classify model performance level (Issue #315 - refactored)."""
        level = self.classify_by_explicit_name(name)
        if level:
            return level

        level = self.classify_by_parameter_size(parameter_size)
        if level:
            return level

        return ModelPerformanceLevel.STANDARD
