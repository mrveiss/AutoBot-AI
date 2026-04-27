# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Training Module (Issue #904)

ML model training infrastructure for code completion.
"""

import logging

logger = logging.getLogger(__name__)

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
    CompletionModel = None  # type: ignore
    CompletionTrainer = None  # type: ignore
    PatternDataset = None  # type: ignore
    Tokenizer = None  # type: ignore
    create_dataloaders = None  # type: ignore
    CompletionEvaluator = None  # type: ignore

    __all__ = [
        "CompletionModel",
        "CompletionTrainer",
        "PatternDataset",
        "Tokenizer",
        "create_dataloaders",
        "CompletionEvaluator",
    ]
