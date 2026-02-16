# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Training Module (Issue #904)

ML model training infrastructure for code completion.
"""

from backend.training.completion_model import CompletionModel
from backend.training.completion_trainer import CompletionTrainer
from backend.training.data_loader import PatternDataset, Tokenizer, create_dataloaders
from backend.training.evaluator import CompletionEvaluator

__all__ = [
    "CompletionModel",
    "CompletionTrainer",
    "PatternDataset",
    "Tokenizer",
    "create_dataloaders",
    "CompletionEvaluator",
]
