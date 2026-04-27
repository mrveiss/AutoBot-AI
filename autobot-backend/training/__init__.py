# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Training Module (Issue #904)

ML model training infrastructure for code completion.
"""

import logging

logger = logging.getLogger(__name__)


class _MissingDep:
    """Sentinel for optional ML dependencies that are not installed.

    Raises a clear ImportError (instead of a misleading TypeError) when the
    missing symbol is called or attribute-accessed at runtime.
    """

    def __init__(self, name: str, error: Exception) -> None:
        self._name = name
        self._error = error

    def __call__(self, *args: object, **kwargs: object) -> None:
        raise ImportError(
            f"{self._name} is not available — install the optional ML dependencies "
            f"(original error: {self._error})"
        )

    def __getattr__(self, item: str) -> None:  # type: ignore[override]
        raise ImportError(
            f"{self._name} is not available — install the optional ML dependencies "
            f"(original error: {self._error})"
        )


try:
    from training.completion_model import CompletionModel
    from training.completion_trainer import CompletionTrainer
    from training.data_loader import PatternDataset, Tokenizer, create_dataloaders
    from training.evaluator import CompletionEvaluator

    __all__ = [
        "CompletionModel",
        "CompletionTrainer",
        "PatternDataset",
        "Tokenizer",
        "create_dataloaders",
        "CompletionEvaluator",
    ]
except (ImportError, RuntimeError) as e:
    logger.warning("ML training dependencies unavailable: %s", e)
    CompletionModel = _MissingDep("CompletionModel", e)  # type: ignore[assignment]
    CompletionTrainer = _MissingDep("CompletionTrainer", e)  # type: ignore[assignment]
    PatternDataset = _MissingDep("PatternDataset", e)  # type: ignore[assignment]
    Tokenizer = _MissingDep("Tokenizer", e)  # type: ignore[assignment]
    create_dataloaders = _MissingDep("create_dataloaders", e)  # type: ignore[assignment]
    CompletionEvaluator = _MissingDep("CompletionEvaluator", e)  # type: ignore[assignment]

    __all__ = [
        "CompletionModel",
        "CompletionTrainer",
        "PatternDataset",
        "Tokenizer",
        "create_dataloaders",
        "CompletionEvaluator",
    ]
