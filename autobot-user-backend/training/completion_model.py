# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Completion Model (Issue #904)

LSTM-based model for code completion with attention mechanism.
"""

import logging
from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


class CompletionModel(nn.Module):
    """
    LSTM-based code completion model.

    Architecture:
    - Embedding layer for tokenized code
    - Bidirectional LSTM encoder for context
    - Attention mechanism over pattern database
    - Output layer with confidence scores
    """

    def __init__(
        self,
        vocab_size: int,
        embedding_dim: int = 256,
        hidden_dim: int = 512,
        num_layers: int = 2,
        dropout: float = 0.3,
    ):
        """
        Initialize completion model.

        Args:
            vocab_size: Size of vocabulary (unique tokens)
            embedding_dim: Dimension of token embeddings
            hidden_dim: Hidden dimension for LSTM
            num_layers: Number of LSTM layers
            dropout: Dropout rate for regularization
        """
        super().__init__()

        self.vocab_size = vocab_size
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        # Token embedding layer
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)

        # Bidirectional LSTM encoder
        self.lstm = nn.LSTM(
            embedding_dim,
            hidden_dim,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=True,
        )

        # Attention mechanism
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_dim * 2, num_heads=8, dropout=dropout, batch_first=True
        )

        # Output projection
        self.output_layer = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, vocab_size),
        )

        # Confidence scoring branch
        self.confidence_layer = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),
        )

    def forward(
        self, input_ids: torch.Tensor, pattern_embeddings: torch.Tensor = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.

        Args:
            input_ids: Input token IDs [batch, seq_len]
            pattern_embeddings: Optional pattern database embeddings

        Returns:
            logits: Token prediction logits [batch, seq_len, vocab_size]
            confidence: Confidence scores [batch, seq_len, 1]
        """
        # Embed tokens
        embedded = self.embedding(input_ids)  # [batch, seq_len, embed_dim]

        # LSTM encoding
        lstm_out, _ = self.lstm(embedded)  # [batch, seq_len, hidden_dim*2]

        # Apply attention if pattern embeddings provided
        if pattern_embeddings is not None:
            attended, _ = self.attention(
                lstm_out, pattern_embeddings, pattern_embeddings
            )
            context = attended + lstm_out  # Residual connection
        else:
            context = lstm_out

        # Generate logits and confidence
        logits = self.output_layer(context)  # [batch, seq_len, vocab_size]
        confidence = self.confidence_layer(context)  # [batch, seq_len, 1]

        return logits, confidence

    def predict(
        self, input_ids: torch.Tensor, top_k: int = 5
    ) -> Dict[str, torch.Tensor]:
        """
        Generate top-k predictions with confidence scores.

        Args:
            input_ids: Input token IDs [batch, seq_len]
            top_k: Number of top predictions to return

        Returns:
            Dictionary with 'tokens', 'scores', 'confidence'
        """
        self.eval()
        with torch.no_grad():
            logits, confidence = self(input_ids)

            # Get last position predictions
            last_logits = logits[:, -1, :]  # [batch, vocab_size]
            last_confidence = confidence[:, -1, :]  # [batch, 1]

            # Apply softmax to get probabilities
            probs = F.softmax(last_logits, dim=-1)  # [batch, vocab_size]

            # Get top-k predictions
            top_probs, top_indices = torch.topk(probs, k=top_k, dim=-1)

            return {
                "tokens": top_indices,  # [batch, top_k]
                "scores": top_probs,  # [batch, top_k]
                "confidence": last_confidence,  # [batch, 1]
            }

    def get_config(self) -> Dict:
        """Get model configuration for serialization."""
        return {
            "vocab_size": self.vocab_size,
            "embedding_dim": self.embedding_dim,
            "hidden_dim": self.hidden_dim,
            "num_layers": self.num_layers,
            "model_type": "lstm_completion",
        }

    @classmethod
    def from_config(cls, config: Dict) -> "CompletionModel":
        """Load model from configuration."""
        return cls(
            vocab_size=config["vocab_size"],
            embedding_dim=config.get("embedding_dim", 256),
            hidden_dim=config.get("hidden_dim", 512),
            num_layers=config.get("num_layers", 2),
        )
