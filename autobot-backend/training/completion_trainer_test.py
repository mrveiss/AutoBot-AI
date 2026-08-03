# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Completion Trainer Tests (Issue #904)

Tests for ML model training infrastructure.
"""

import pickle
import tempfile
from pathlib import Path

import pytest

# Optional ML training stack. Skip cleanly when absent; run for real when it IS
# installed (e.g. a GPU CI image or a local dev box with the full backend reqs).
#
# BOTH imports must be guarded (#13086). `training/evaluator.py` — pulled in
# below — imports `torchmetrics` at module level, and the `python-suite` CI
# environment installs torch TRANSITIVELY via sentence-transformers while never
# installing torchmetrics. That combination let the torch guard pass and then
# blew up on torchmetrics, turning this module into a hard collection ERROR on
# every shard. torchmetrics is deliberately NOT added to requirements-ci.txt:
# the repo already treats this subsystem as optional (`training/__init__.py`
# wraps every symbol in `optional_import`), and the CI install resolves torch
# against the CPU-only index specifically to keep the CUDA-adjacent closure out.
pytest.importorskip("torch.nn.functional", reason="torch not installed — optional ML dep")
pytest.importorskip("torchmetrics", reason="torchmetrics not installed — optional ML dep (training/evaluator.py)")

import torch  # noqa: E402 — after importorskip by design

from training.completion_model import CompletionModel  # noqa: E402
from training.data_loader import Tokenizer  # noqa: E402
from training.evaluator import CompletionEvaluator  # noqa: E402

# Module-level marker used by the malicious-pickle test below. A crafted
# checkpoint whose __reduce__ targets this function would flip the flag if the
# payload were ever executed during deserialization.
_PICKLE_PAYLOAD = {"executed": False}


def _record_payload_execution():
    """Reduce target for the malicious-pickle gadget (harmless side effect)."""
    _PICKLE_PAYLOAD["executed"] = True
    return {}


class _MaliciousCheckpoint:
    """Object whose unpickling would invoke ``_record_payload_execution``."""

    def __reduce__(self):
        return (_record_payload_execution, ())


def test_load_checkpoint_rejects_malicious_pickle():
    """torch.load(weights_only=True) must refuse code-executing checkpoints (CodeQL #983).

    Proves the py/unsafe-deserialization mitigation: the restricted unpickler
    rejects a crafted checkpoint before any embedded reduce gadget can run.
    """
    _PICKLE_PAYLOAD["executed"] = False
    with tempfile.TemporaryDirectory() as tmpdir:
        malicious_path = Path(tmpdir) / "malicious.pt"
        with open(malicious_path, "wb") as f:
            pickle.dump(_MaliciousCheckpoint(), f)

        # weights_only=True (the sink used in CompletionTrainer.load_checkpoint)
        # must raise rather than execute the embedded gadget.
        with pytest.raises(Exception):
            torch.load(malicious_path, map_location="cpu", weights_only=True)

        assert _PICKLE_PAYLOAD["executed"] is False, "malicious payload was executed"


def test_tokenizer_initialization():
    """Test tokenizer initialization."""
    tokenizer = Tokenizer()
    assert tokenizer.vocab_size == 3  # PAD, UNK, SEP
    assert tokenizer.token_to_id["<PAD>"] == 0
    assert tokenizer.token_to_id["<UNK>"] == 1


def test_tokenizer_encode():
    """Test tokenizer encoding."""
    tokenizer = Tokenizer()
    text = "def hello_world():"
    ids = tokenizer.encode(text, max_length=10)

    assert len(ids) == 10
    assert all(isinstance(id_, int) for id_ in ids)
    assert ids[-1] == 0  # Padded


def test_tokenizer_decode():
    """Test tokenizer decoding."""
    tokenizer = Tokenizer()

    # Encode then decode
    text = "def hello():"
    ids = tokenizer.encode(text, max_length=10)
    decoded = tokenizer.decode(ids)

    # Should preserve main tokens (may have extra spaces)
    assert "def" in decoded
    assert "hello" in decoded


def test_tokenizer_vocab_growth():
    """Test tokenizer vocabulary growth."""
    tokenizer = Tokenizer()
    initial_size = tokenizer.vocab_size

    tokenizer.encode("def function_name():", max_length=20)
    assert tokenizer.vocab_size > initial_size


def test_completion_model_initialization():
    """Test completion model initialization."""
    model = CompletionModel(vocab_size=1000, embedding_dim=128, hidden_dim=256)

    assert model.vocab_size == 1000
    assert model.embedding_dim == 128
    assert model.hidden_dim == 256


def test_completion_model_forward():
    """Test completion model forward pass."""
    model = CompletionModel(vocab_size=1000, embedding_dim=128, hidden_dim=256)

    # Create sample input
    batch_size = 2
    seq_len = 10
    input_ids = torch.randint(0, 1000, (batch_size, seq_len))

    # Forward pass
    logits, confidence = model(input_ids)

    # Check output shapes
    assert logits.shape == (batch_size, seq_len, 1000)
    assert confidence.shape == (batch_size, seq_len, 1)
    assert torch.all((confidence >= 0) & (confidence <= 1))


def test_completion_model_predict():
    """Test completion model prediction."""
    model = CompletionModel(vocab_size=1000, embedding_dim=128, hidden_dim=256)
    model.eval()

    input_ids = torch.randint(0, 1000, (1, 10))
    predictions = model.predict(input_ids, top_k=5)

    assert "tokens" in predictions
    assert "scores" in predictions
    assert "confidence" in predictions
    assert predictions["tokens"].shape == (1, 5)


def test_completion_model_config():
    """Test model configuration serialization."""
    model = CompletionModel(vocab_size=1000, embedding_dim=128, hidden_dim=256)
    config = model.get_config()

    assert config["vocab_size"] == 1000
    assert config["embedding_dim"] == 128
    assert config["hidden_dim"] == 256
    assert config["model_type"] == "lstm_completion"

    # Test loading from config
    loaded_model = CompletionModel.from_config(config)
    assert loaded_model.vocab_size == 1000


def test_evaluator_initialization():
    """Test evaluator initialization."""
    evaluator = CompletionEvaluator(device="cpu")

    assert evaluator.device == "cpu"
    assert evaluator.accuracy is not None
    assert evaluator.mrr is not None


def test_evaluator_update():
    """Test evaluator metric updates."""
    evaluator = CompletionEvaluator(device="cpu")

    # Create dummy predictions and targets
    logits = torch.randn(2, 10, 100)  # [batch, seq_len, vocab]
    targets = torch.randint(0, 100, (2, 10))  # [batch, seq_len]

    # Update metrics
    evaluator.update(logits, targets)

    # Compute metrics
    metrics = evaluator.compute()
    assert "accuracy" in metrics
    assert "mrr" in metrics
    assert "hit@1" in metrics
    assert "hit@5" in metrics


def test_evaluator_reset():
    """Test evaluator reset."""
    evaluator = CompletionEvaluator(device="cpu")

    # Update with dummy data
    logits = torch.randn(2, 10, 100)
    targets = torch.randint(0, 100, (2, 10))
    evaluator.update(logits, targets)

    # Reset
    evaluator.reset()

    # Metrics should be zero after reset
    metrics = evaluator.compute()
    assert metrics["accuracy"] == 0.0


def test_model_save_load():
    """Test model checkpoint save/load."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create and save model
        model = CompletionModel(vocab_size=1000, embedding_dim=128, hidden_dim=256)
        checkpoint = {
            "model_state_dict": model.state_dict(),
            "model_config": model.get_config(),
        }

        checkpoint_path = Path(tmpdir) / "test_model.pt"
        torch.save(checkpoint, checkpoint_path)

        # Load model
        loaded = torch.load(checkpoint_path, weights_only=True)
        config = loaded["model_config"]
        new_model = CompletionModel.from_config(config)
        new_model.load_state_dict(loaded["model_state_dict"])

        # Verify same architecture
        assert new_model.vocab_size == model.vocab_size
        assert new_model.embedding_dim == model.embedding_dim


def test_model_training_mode():
    """Test model training/eval mode switching."""
    model = CompletionModel(vocab_size=1000)

    # Training mode
    model.train()
    assert model.training is True

    # Eval mode
    model.eval()
    assert model.training is False


def test_model_gradient_flow():
    """Test gradient flow through model."""
    model = CompletionModel(vocab_size=1000, embedding_dim=128, hidden_dim=256)
    model.train()

    input_ids = torch.randint(0, 1000, (2, 10))
    targets = torch.randint(0, 1000, (2, 10))

    # Forward pass
    logits, _ = model(input_ids)

    # Calculate loss
    criterion = torch.nn.CrossEntropyLoss()
    loss = criterion(logits.view(-1, 1000), targets.view(-1))

    # Backward pass
    loss.backward()

    # Check gradients exist
    for param in model.parameters():
        assert param.grad is not None


def test_mrr_metric():
    """Test Mean Reciprocal Rank metric."""
    from training.evaluator import MeanReciprocalRank

    mrr = MeanReciprocalRank()

    # Predictions: [[5, 3, 2], [1, 2, 3]]
    # Targets: [3, 1]
    # Ranks: [2, 1] -> RR: [1/2, 1/1]
    # MRR: (0.5 + 1.0) / 2 = 0.75

    preds = torch.tensor([[5, 3, 2], [1, 2, 3]])
    targets = torch.tensor([3, 1])

    mrr.update(preds, targets)
    result = mrr.compute()

    assert result > 0.7  # Should be 0.75


def test_hit_at_k_metric():
    """Test Hit@K metric."""
    from training.evaluator import HitAtK

    hit5 = HitAtK(k=5)

    # First 3 in top-5: 100%
    preds = torch.tensor([[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]])
    targets = torch.tensor([3, 8])

    hit5.update(preds, targets)
    result = hit5.compute()

    assert result == 1.0  # Both in top-5
