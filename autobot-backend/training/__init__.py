# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Training Module (Issue #904)

ML model training infrastructure for code completion.
"""

from autobot_shared.logging_manager import get_logger
from autobot_shared.missing_dep import MissingDep as _MissingDep

logger = get_logger(__name__)

__all__ = [
    "CompletionModel",
    "CompletionTrainer",
    "PatternDataset",
    "Tokenizer",
    "create_dataloaders",
    "CompletionEvaluator",
]

try:
    from training.completion_model import CompletionModel
    from training.completion_trainer import CompletionTrainer
    from training.data_loader import PatternDataset, Tokenizer, create_dataloaders
    from training.evaluator import CompletionEvaluator
except (ImportError, RuntimeError) as e:
    logger.warning("ML training dependencies unavailable: %s", e)
    CompletionModel = _MissingDep("CompletionModel", e)  # type: ignore[assignment]
    CompletionTrainer = _MissingDep("CompletionTrainer", e)  # type: ignore[assignment]
    PatternDataset = _MissingDep("PatternDataset", e)  # type: ignore[assignment]
    Tokenizer = _MissingDep("Tokenizer", e)  # type: ignore[assignment]
    create_dataloaders = _MissingDep("create_dataloaders", e)  # type: ignore[assignment]
    CompletionEvaluator = _MissingDep("CompletionEvaluator", e)  # type: ignore[assignment]
