# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Training Module (Issue #904)

ML model training infrastructure for code completion.
"""

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
