# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Semantic Stagnation Fingerprinting

Token-level novelty scorer for agent observation stagnation detection.
Computes what fraction of a tool result's tokens have not appeared in
any prior result within the current task, allowing the caller to decide
whether the agent is exploring genuinely new information.

Implements GH#6627.
"""

import hashlib
import json
import re
from typing import Any


def normalize_content(content: Any) -> str:
    """Return a canonical string for any tool-result value."""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, sort_keys=True, default=str)
    except Exception:
        return repr(content)


def tokenize(text: str) -> list[str]:
    """Split text into lower-cased word/number tokens."""
    return re.findall(r"\b\w+\b", text.lower())


def content_hash(content: Any) -> str:
    """Return a stable SHA-256 hex digest of normalized content."""
    return hashlib.sha256(normalize_content(content).encode()).hexdigest()


def compute_novel_token_ratio(content: Any, seen_tokens: set[str]) -> float:
    """Return the fraction of tokens in *content* absent from *seen_tokens*.

    Mutates *seen_tokens* in place so subsequent calls accumulate the full
    vocabulary seen so far.  Returns 1.0 when *content* has no tokens
    (treated as fully novel) or when *seen_tokens* is empty (first
    observation has nothing to compare against).
    """
    tokens = tokenize(normalize_content(content))
    if not tokens:
        return 1.0
    if not seen_tokens:
        seen_tokens.update(tokens)
        return 1.0
    novel_count = sum(1 for t in tokens if t not in seen_tokens)
    ratio = novel_count / len(tokens)
    seen_tokens.update(tokens)
    return ratio
