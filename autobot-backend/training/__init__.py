# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Training Module (Issue #904)

ML model training infrastructure for code completion.
"""

from autobot_shared.logging_manager import get_logger
from autobot_shared.missing_dep import MissingDep as _MissingDep
from autobot_shared.missing_dep import optional_import

logger = get_logger(__name__)

__all__ = [
    "CompletionModel",
    "CompletionTrainer",
    "PatternDataset",
    "Tokenizer",
    "create_dataloaders",
    "CompletionEvaluator",
]

# optional_import handles ImportError; RuntimeError (e.g. from torch CUDA init on import)
# is caught separately so all six symbols get MissingDep stubs in either case.
try:
    globals().update(optional_import("training.completion_model", ["CompletionModel"]))
    globals().update(optional_import("training.completion_trainer", ["CompletionTrainer"]))
    globals().update(optional_import("training.data_loader", ["PatternDataset", "Tokenizer", "create_dataloaders"]))
    globals().update(optional_import("training.evaluator", ["CompletionEvaluator"]))
except RuntimeError as _e:
    logger.warning("ML training dependencies unavailable: %s", _e)
    for _name in [
        "CompletionModel",
        "CompletionTrainer",
        "PatternDataset",
        "Tokenizer",
        "create_dataloaders",
        "CompletionEvaluator",
    ]:
        globals()[_name] = _MissingDep(_name, _e)
