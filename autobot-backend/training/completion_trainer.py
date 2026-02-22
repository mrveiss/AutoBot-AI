# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Completion Model Trainer (Issue #904)

Training orchestration for code completion model.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import torch
import torch.nn as nn
import torch.optim as optim
from backend.llm_interface_pkg.hardware import HardwareDetector
from backend.training.completion_model import CompletionModel
from backend.training.data_loader import create_dataloaders
from backend.training.evaluator import CompletionEvaluator

logger = logging.getLogger(__name__)


class CompletionTrainer:
    """
    Trainer for code completion model.

    Handles training loop, validation, checkpointing, and metrics.
    """

    def __init__(
        self,
        model_dir: str = "/opt/autobot/models",
        language: Optional[str] = None,
        pattern_type: Optional[str] = None,
        device: Optional[str] = None,
    ):
        """
        Initialize trainer.

        Args:
            model_dir: Directory to save trained models
            language: Filter training data by language
            pattern_type: Filter training data by pattern type
            device: Device for training (auto-detect if None)
        """
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.language = language
        self.pattern_type = pattern_type

        # Detect hardware
        if device is None:
            hardware_detector = HardwareDetector()
            available = hardware_detector.detect_hardware()
            if "cuda" in available:
                self.device = "cuda"
            else:
                self.device = "cpu"
            logger.info(f"Auto-detected device: {self.device}")
        else:
            self.device = device

        # Initialize components
        self.model: Optional[CompletionModel] = None
        self.optimizer: Optional[optim.Optimizer] = None
        self.criterion = nn.CrossEntropyLoss(ignore_index=0)
        self.evaluator = CompletionEvaluator(device=self.device)

        # Training state
        self.current_epoch = 0
        self.best_val_loss = float("inf")
        self.training_history: Dict = {"train_loss": [], "val_loss": [], "metrics": []}

    def prepare_data(self, batch_size: int = 32, train_split: float = 0.8):
        """
        Prepare training and validation data loaders.

        Args:
            batch_size: Batch size for training
            train_split: Fraction of data for training
        """
        logger.info("Preparing data loaders...")
        self.train_loader, self.val_loader, vocab_size = create_dataloaders(
            train_split=train_split,
            batch_size=batch_size,
            language=self.language,
            pattern_type=self.pattern_type,
        )

        # Initialize model with vocabulary size
        self.model = CompletionModel(vocab_size=vocab_size).to(self.device)
        self.optimizer = optim.AdamW(self.model.parameters(), lr=1e-4)

        logger.info(f"Model initialized with vocab_size={vocab_size}")
        logger.info(
            f"Total parameters: " f"{sum(p.numel() for p in self.model.parameters()):,}"
        )

    def train_epoch(self) -> float:
        """
        Train for one epoch.

        Returns:
            Average training loss
        """
        self.model.train()
        total_loss = 0.0
        num_batches = 0

        for batch in self.train_loader:
            input_ids = batch["input_ids"].to(self.device)
            target_ids = batch["target_ids"].to(self.device)

            # Forward pass
            logits, confidence = self.model(input_ids)

            # Reshape for loss calculation
            logits_flat = logits.view(-1, logits.size(-1))
            targets_flat = target_ids.view(-1)

            # Calculate loss
            loss = self.criterion(logits_flat, targets_flat)

            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        avg_loss = total_loss / num_batches
        return avg_loss

    def validate(self) -> Dict[str, float]:
        """
        Validate model on validation set.

        Returns:
            Dictionary with validation loss and metrics
        """
        self.model.eval()
        total_loss = 0.0
        num_batches = 0

        with torch.no_grad():
            for batch in self.val_loader:
                input_ids = batch["input_ids"].to(self.device)
                target_ids = batch["target_ids"].to(self.device)

                # Forward pass
                logits, _ = self.model(input_ids)

                # Calculate loss
                logits_flat = logits.view(-1, logits.size(-1))
                targets_flat = target_ids.view(-1)
                loss = self.criterion(logits_flat, targets_flat)

                total_loss += loss.item()
                num_batches += 1

        avg_loss = total_loss / num_batches

        # Compute evaluation metrics
        metrics = self.evaluator.evaluate_model(self.model, self.val_loader)
        metrics["val_loss"] = avg_loss

        return metrics

    def train(self, num_epochs: int = 10, early_stopping_patience: int = 3):
        """
        Full training loop.

        Args:
            num_epochs: Number of epochs to train
            early_stopping_patience: Stop if no improvement for N epochs
        """
        if self.model is None:
            raise ValueError("Must call prepare_data() before train()")

        logger.info(f"Starting training for {num_epochs} epochs...")

        patience_counter = 0

        for epoch in range(num_epochs):
            self.current_epoch = epoch + 1

            # Train epoch
            train_loss = self.train_epoch()
            logger.info(f"Epoch {self.current_epoch}: train_loss={train_loss:.4f}")

            # Validate
            val_metrics = self.validate()
            val_loss = val_metrics["val_loss"]
            logger.info(
                f"Epoch {self.current_epoch}: val_loss={val_loss:.4f}, "
                f"accuracy={val_metrics['accuracy']:.4f}, "
                f"mrr={val_metrics['mrr']:.4f}"
            )

            # Save training history
            self.training_history["train_loss"].append(train_loss)
            self.training_history["val_loss"].append(val_loss)
            self.training_history["metrics"].append(val_metrics)

            # Checkpoint if improved
            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.save_checkpoint(is_best=True)
                patience_counter = 0
                logger.info("New best model saved!")
            else:
                patience_counter += 1

            # Early stopping
            if patience_counter >= early_stopping_patience:
                logger.info(
                    f"Early stopping triggered after {self.current_epoch} epochs"
                )
                break

        logger.info("Training complete!")
        return self.training_history

    def save_checkpoint(self, is_best: bool = False):
        """
        Save model checkpoint.

        Args:
            is_best: Whether this is the best model so far
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        version = f"v{timestamp}"

        checkpoint = {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "epoch": self.current_epoch,
            "val_loss": self.best_val_loss,
            "model_config": self.model.get_config(),
            "training_history": self.training_history,
            "version": version,
        }

        # Save versioned checkpoint
        checkpoint_path = self.model_dir / f"completion_model_{version}.pt"
        torch.save(checkpoint, checkpoint_path)
        logger.info(f"Saved checkpoint: {checkpoint_path}")

        # Save metadata
        metadata = {
            "version": version,
            "epoch": self.current_epoch,
            "val_loss": self.best_val_loss,
            "language": self.language,
            "pattern_type": self.pattern_type,
            "timestamp": timestamp,
        }
        metadata_path = self.model_dir / f"completion_model_{version}_meta.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # Update best model symlink
        if is_best:
            best_link = self.model_dir / "completion_model_best.pt"
            if best_link.exists():
                best_link.unlink()
            best_link.symlink_to(checkpoint_path.name)

    def load_checkpoint(self, version: str):
        """
        Load model checkpoint.

        Args:
            version: Model version to load (e.g., 'v20260216_123456' or 'best')
        """
        if version == "best":
            checkpoint_path = self.model_dir / "completion_model_best.pt"
        else:
            checkpoint_path = self.model_dir / f"completion_model_{version}.pt"

        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        checkpoint = torch.load(checkpoint_path, map_location=self.device)

        # Restore model
        config = checkpoint["model_config"]
        self.model = CompletionModel.from_config(config).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])

        # Restore optimizer
        self.optimizer = optim.AdamW(self.model.parameters())
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])

        # Restore training state
        self.current_epoch = checkpoint["epoch"]
        self.best_val_loss = checkpoint["val_loss"]
        self.training_history = checkpoint["training_history"]

        logger.info(f"Loaded checkpoint: {checkpoint_path}")
