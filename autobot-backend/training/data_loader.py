# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern Data Loader (Issue #904)

Loads code patterns from database and prepares training data.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

import torch
from models.code_pattern import CodePattern
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from torch.utils.data import Dataset

from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)


class Tokenizer:
    """Simple tokenizer for code completion."""

    def __init__(self):
        self.token_to_id: Dict[str, int] = {"<PAD>": 0, "<UNK>": 1, "<SEP>": 2}
        self.id_to_token: Dict[int, str] = {0: "<PAD>", 1: "<UNK>", 2: "<SEP>"}
        self.next_id = 3

    def tokenize(self, text: str) -> List[str]:
        """Tokenize code text."""
        # Split on whitespace and punctuation
        tokens = re.findall(r"\b\w+\b|[^\w\s]", text, re.UNICODE)
        return tokens

    def encode(self, text: str, max_length: int = 128) -> List[int]:
        """Encode text to token IDs."""
        tokens = self.tokenize(text)
        ids = []

        for token in tokens[:max_length]:
            if token not in self.token_to_id:
                self.token_to_id[token] = self.next_id
                self.id_to_token[self.next_id] = token
                self.next_id += 1
            ids.append(self.token_to_id[token])

        # Pad to max_length
        while len(ids) < max_length:
            ids.append(0)  # PAD token

        return ids

    def decode(self, ids: List[int]) -> str:
        """Decode token IDs to text."""
        tokens = [self.id_to_token.get(id_, "<UNK>") for id_ in ids]
        return " ".join(t for t in tokens if t not in ["<PAD>", "<SEP>"])

    @property
    def vocab_size(self) -> int:
        """Get vocabulary size."""
        return len(self.token_to_id)


class PatternDataset(Dataset):
    """
    Dataset for code completion patterns.

    Loads patterns from database and provides training samples.
    """

    def __init__(
        self,
        language: Optional[str] = None,
        pattern_type: Optional[str] = None,
        context_window: int = 5,
        max_length: int = 128,
        min_frequency: int = 1,
    ):
        """
        Initialize pattern dataset.

        Args:
            language: Filter by language (python, typescript, vue)
            pattern_type: Filter by pattern type
            context_window: Number of lines of context before pattern
            max_length: Maximum token sequence length
            min_frequency: Minimum pattern frequency to include
        """
        self.language = language
        self.pattern_type = pattern_type
        self.context_window = context_window
        self.max_length = max_length
        self.min_frequency = min_frequency

        # Initialize tokenizer
        self.tokenizer = Tokenizer()

        # Load patterns from database
        self.patterns = self._load_patterns()

        logger.info(
            f"Loaded {len(self.patterns)} patterns "
            f"(language={language}, type={pattern_type})"
        )

    def _load_patterns(self) -> List[CodePattern]:
        """Load patterns from database."""
        DATABASE_URL = (
            f"postgresql://{config.database.user}:{config.database.password}"
            f"@{config.database.host}:{config.database.port}"
            f"/{config.database.name}"
        )
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        try:
            query = db.query(CodePattern).filter(
                CodePattern.frequency >= self.min_frequency
            )

            if self.language:
                query = query.filter(CodePattern.language == self.language)
            if self.pattern_type:
                query = query.filter(CodePattern.pattern_type == self.pattern_type)

            patterns = query.all()
            return patterns
        finally:
            db.close()

    def __len__(self) -> int:
        """Dataset length."""
        return len(self.patterns)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """
        Get training sample.

        Returns:
            Dictionary with 'input_ids', 'target_ids', 'pattern_id'
        """
        pattern = self.patterns[idx]

        # Use signature as context, body as target
        context = pattern.signature
        target = pattern.body if pattern.body else pattern.signature

        # Tokenize
        context_ids = self.tokenizer.encode(context, self.max_length)
        target_ids = self.tokenizer.encode(target, self.max_length)

        return {
            "input_ids": torch.tensor(context_ids, dtype=torch.long),
            "target_ids": torch.tensor(target_ids, dtype=torch.long),
            "pattern_id": pattern.id,
            "language": pattern.language,
        }

    def get_vocab_size(self) -> int:
        """Get vocabulary size after loading data."""
        return self.tokenizer.vocab_size


def create_dataloaders(
    train_split: float = 0.8,
    batch_size: int = 32,
    language: Optional[str] = None,
    pattern_type: Optional[str] = None,
) -> Tuple:
    """
    Create train and validation data loaders.

    Args:
        train_split: Fraction of data for training
        batch_size: Batch size for data loaders
        language: Filter by language
        pattern_type: Filter by pattern type

    Returns:
        Tuple of (train_loader, val_loader, vocab_size)
    """
    from torch.utils.data import DataLoader, random_split

    # Load full dataset
    dataset = PatternDataset(language=language, pattern_type=pattern_type)

    if len(dataset) == 0:
        raise ValueError("No patterns found in database")

    # Split into train/val
    train_size = int(train_split * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

    # Create data loaders
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    vocab_size = dataset.get_vocab_size()

    logger.info(
        f"Created dataloaders: train={train_size}, val={val_size}, "
        f"vocab={vocab_size}"
    )

    return train_loader, val_loader, vocab_size
