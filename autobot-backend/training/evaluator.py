# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Model Evaluator (Issue #904)

Evaluation metrics for code completion model.
"""

from typing import Dict

import torch
from torchmetrics import Accuracy, Metric

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class MeanReciprocalRank(Metric):
    """
    Mean Reciprocal Rank (MRR) metric.

    Measures how highly the correct answer is ranked.
    """

    def __init__(self):
        super().__init__()
        self.add_state("sum_rr", default=torch.tensor(0.0), dist_reduce_fx="sum")
        self.add_state("total", default=torch.tensor(0), dist_reduce_fx="sum")

    def update(self, preds: torch.Tensor, targets: torch.Tensor):
        """
        Update metric state.

        Args:
            preds: Predicted token IDs [batch, k]
            targets: Target token IDs [batch]
        """
        batch_size = targets.size(0)
        targets = targets.view(-1, 1)  # [batch, 1]

        # Find rank of correct answer
        matches = (preds == targets).float()  # [batch, k]
        ranks = torch.arange(1, preds.size(1) + 1, device=preds.device).float()

        # Get reciprocal rank (0 if not found)
        rr = (matches / ranks).max(dim=1)[0]  # [batch]

        self.sum_rr += rr.sum()
        self.total += batch_size

    def compute(self) -> torch.Tensor:
        """Compute final MRR."""
        return self.sum_rr / self.total


class HitAtK(Metric):
    """
    Hit@K metric.

    Measures if correct answer is in top-k predictions.
    """

    def __init__(self, k: int = 5):
        super().__init__()
        self.k = k
        self.add_state("hits", default=torch.tensor(0), dist_reduce_fx="sum")
        self.add_state("total", default=torch.tensor(0), dist_reduce_fx="sum")

    def update(self, preds: torch.Tensor, targets: torch.Tensor):
        """
        Update metric state.

        Args:
            preds: Predicted token IDs [batch, k]
            targets: Target token IDs [batch]
        """
        batch_size = targets.size(0)
        targets = targets.view(-1, 1)  # [batch, 1]

        # Check if target in top-k
        matches = (preds[:, : self.k] == targets).any(dim=1)  # [batch]

        self.hits += matches.sum()
        self.total += batch_size

    def compute(self) -> torch.Tensor:
        """Compute final Hit@K."""
        return self.hits.float() / self.total


class CompletionEvaluator:
    """
    Evaluator for code completion model.

    Computes accuracy, MRR, Hit@K metrics on validation set.
    """

    def __init__(self, vocab_size: int, device: str = "cpu"):
        """
        Initialize evaluator.

        Args:
            vocab_size: Size of the evaluated model's vocabulary. Must equal the
                model's ``vocab_size``; torchmetrics rejects a logits tensor whose
                class dimension differs from ``num_classes``.
            device: Device for computation (cpu/cuda)

        Raises:
            ValueError: If vocab_size is not positive.
        """
        if vocab_size <= 0:
            raise ValueError(f"vocab_size must be positive, got {vocab_size}")

        self.device = device
        self.vocab_size = vocab_size

        # Initialize metrics
        # Issue #13162: num_classes was hardcoded to 10000 while the model's vocab
        # size comes from the tokenizer, so validate() raised ValueError on every
        # run whose vocabulary was not exactly 10000 tokens.
        self.accuracy = Accuracy(task="multiclass", num_classes=vocab_size).to(device)
        self.mrr = MeanReciprocalRank().to(device)
        self.hit_at_1 = HitAtK(k=1).to(device)
        self.hit_at_5 = HitAtK(k=5).to(device)
        self.hit_at_10 = HitAtK(k=10).to(device)

    def reset(self):
        """Reset all metrics."""
        self.accuracy.reset()
        self.mrr.reset()
        self.hit_at_1.reset()
        self.hit_at_5.reset()
        self.hit_at_10.reset()

    def update(self, logits: torch.Tensor, targets: torch.Tensor):
        """
        Update metrics with batch predictions.

        Args:
            logits: Model output logits [batch, seq_len, vocab_size]
            targets: Target token IDs [batch, seq_len]
        """
        # Get predictions for last position
        last_logits = logits[:, -1, :]  # [batch, vocab_size]
        last_targets = targets[:, -1]  # [batch]

        # Get top-k predictions. torch.topk raises when k exceeds the class
        # dimension, so a vocabulary smaller than 10 tokens must not be a crash.
        top_k = min(10, last_logits.size(-1))
        _, top_preds = torch.topk(last_logits, k=top_k, dim=-1)  # [batch, top_k]

        # Update accuracy (top-1)
        self.accuracy.update(last_logits, last_targets)

        # Update MRR
        self.mrr.update(top_preds, last_targets)

        # Update Hit@K
        self.hit_at_1.update(top_preds, last_targets)
        self.hit_at_5.update(top_preds, last_targets)
        self.hit_at_10.update(top_preds, last_targets)

    def compute(self) -> Dict[str, float]:
        """
        Compute final metrics.

        Returns:
            Dictionary of metric values
        """
        return {
            "accuracy": self.accuracy.compute().item(),
            "mrr": self.mrr.compute().item(),
            "hit@1": self.hit_at_1.compute().item(),
            "hit@5": self.hit_at_5.compute().item(),
            "hit@10": self.hit_at_10.compute().item(),
        }

    def evaluate_model(self, model, data_loader) -> Dict[str, float]:
        """
        Evaluate model on full dataset.

        Args:
            model: CompletionModel to evaluate
            data_loader: DataLoader with validation data

        Returns:
            Dictionary of metric values
        """
        model.eval()
        self.reset()

        with torch.no_grad():
            for batch in data_loader:
                input_ids = batch["input_ids"].to(self.device)
                target_ids = batch["target_ids"].to(self.device)

                # Forward pass
                logits, _ = model(input_ids)

                # Update metrics
                self.update(logits, target_ids)

        metrics = self.compute()
        logger.info(f"Evaluation metrics: {metrics}")

        return metrics
