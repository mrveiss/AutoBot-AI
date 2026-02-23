# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Incremental Trainer Service (Issue #905)

Lightweight model updates based on feedback without full retraining.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import torch
import torch.optim as optim
from backend.models.completion_feedback import CompletionFeedback
from backend.training.completion_trainer import CompletionTrainer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)


class IncrementalTrainer:
    """
    Incremental learning for code completion model.

    Performs lightweight model updates based on user feedback
    without requiring full retraining.
    """

    def __init__(self, model_version: str = "best"):
        """
        Initialize incremental trainer.

        Args:
            model_version: Version of model to update
        """
        # Load existing trainer
        self.trainer = CompletionTrainer()
        self.trainer.load_checkpoint(model_version)

        # Database setup
        DATABASE_URL = (
            f"postgresql://{config.database.user}:{config.database.password}"
            f"@{config.database.host}:{config.database.port}/"
            f"{config.database.name}"
        )
        engine = create_engine(DATABASE_URL)
        self.SessionLocal = sessionmaker(bind=engine)

        # Incremental learning parameters
        self.learning_rate = 1e-5  # Lower LR for fine-tuning
        self.batch_size = 8  # Small batches for online learning

    def _prepare_training_data(self, feedback_events):
        """
        Tokenize feedback into training tensors.

        Helper for update_from_feedback (Issue #905).
        """
        contexts = []
        targets = []

        for feedback in feedback_events:
            context_ids = self.trainer.train_loader.dataset.tokenizer.encode(
                feedback.context, max_length=128
            )
            target_ids = self.trainer.train_loader.dataset.tokenizer.encode(
                feedback.suggestion, max_length=128
            )

            contexts.append(torch.tensor(context_ids, dtype=torch.long))
            targets.append(torch.tensor(target_ids, dtype=torch.long))

        context_batch = torch.stack(contexts).to(self.trainer.device)
        target_batch = torch.stack(targets).to(self.trainer.device)

        return context_batch, target_batch

    def _train_on_batch(self, batch_contexts, batch_targets, optimizer):
        """
        Perform gradient descent on mini-batch.

        Helper for update_from_feedback (Issue #905).
        """
        # Forward pass
        logits, _ = self.trainer.model(batch_contexts)

        # Calculate loss
        logits_flat = logits.view(-1, logits.size(-1))
        targets_flat = batch_targets.view(-1)
        loss = self.trainer.criterion(logits_flat, targets_flat)

        # Backward pass
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.trainer.model.parameters(), max_norm=1.0)
        optimizer.step()

        return loss.item()

    def _run_training_loop(self, context_batch, target_batch):
        """
        Run mini-batch training loop.

        Helper for update_from_feedback (Issue #905).
        """
        self.trainer.model.train()
        optimizer = optim.AdamW(self.trainer.model.parameters(), lr=self.learning_rate)

        total_loss = 0.0
        num_batches = 0

        for i in range(0, context_batch.size(0), self.batch_size):
            end_idx = min(i + self.batch_size, context_batch.size(0))
            batch_contexts = context_batch[i:end_idx]
            batch_targets = target_batch[i:end_idx]

            loss = self._train_on_batch(batch_contexts, batch_targets, optimizer)
            total_loss += loss
            num_batches += 1

        avg_loss = total_loss / num_batches if num_batches > 0 else 0.0
        return avg_loss, num_batches

    def _fetch_recent_feedback(self, db, time_window_hours: int):
        """Helper for update_from_feedback. Ref: #1088."""
        since = datetime.utcnow() - timedelta(hours=time_window_hours)
        return (
            db.query(CompletionFeedback)
            .filter(
                CompletionFeedback.timestamp > since,
                CompletionFeedback.action == "accepted",
            )
            .all()
        )

    def update_from_feedback(
        self, time_window_hours: int = 24, min_feedback: int = 10
    ) -> dict:
        """
        Update model based on recent feedback.

        Args:
            time_window_hours: Hours of feedback to consider
            min_feedback: Minimum feedback events needed for update

        Returns:
            Dictionary with update statistics
        """
        db = self.SessionLocal()
        try:
            feedback_events = self._fetch_recent_feedback(db, time_window_hours)

            if len(feedback_events) < min_feedback:
                logger.info(
                    f"Insufficient feedback for update: {len(feedback_events)} "
                    f"< {min_feedback}"
                )
                return {
                    "status": "skipped",
                    "reason": "insufficient_feedback",
                    "feedback_count": len(feedback_events),
                }

            # Prepare and train
            context_batch, target_batch = self._prepare_training_data(feedback_events)
            avg_loss, num_batches = self._run_training_loop(context_batch, target_batch)

            # Save updated model
            self.trainer.save_checkpoint(is_best=False)

            logger.info(
                f"Incremental update complete: {len(feedback_events)} samples, "
                f"avg_loss={avg_loss:.4f}"
            )

            return {
                "status": "success",
                "feedback_count": len(feedback_events),
                "batches_processed": num_batches,
                "avg_loss": avg_loss,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Incremental training failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
        finally:
            db.close()

    def trigger_full_retrain(
        self, language: Optional[str] = None, num_epochs: int = 5
    ) -> dict:
        """
        Trigger full model retraining.

        Args:
            language: Filter training data by language
            num_epochs: Number of training epochs

        Returns:
            Dictionary with training status
        """
        try:
            logger.info(
                f"Starting full retrain: language={language}, epochs={num_epochs}"
            )

            # Create new trainer
            trainer = CompletionTrainer(language=language)

            # Prepare data
            trainer.prepare_data(batch_size=32)

            # Train
            history = trainer.train(num_epochs=num_epochs, early_stopping_patience=2)

            # Save final model
            trainer.save_checkpoint(is_best=True)

            # Get final metrics
            final_metrics = history["metrics"][-1] if history["metrics"] else {}

            logger.info(
                f"Full retrain complete: "
                f"val_loss={final_metrics.get('val_loss', 0):.4f}"
            )

            return {
                "status": "success",
                "epochs_trained": trainer.current_epoch,
                "final_val_loss": final_metrics.get("val_loss"),
                "final_accuracy": final_metrics.get("accuracy"),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Full retrain failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
