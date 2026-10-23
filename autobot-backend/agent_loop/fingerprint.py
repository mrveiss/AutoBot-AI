# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Semantic Stagnation Fingerprinting

Token-level novelty scorer for agent observation stagnation detection.
Computes what fraction of a tool result's tokens have not appeared in
any prior result within the current task, allowing the caller to decide
whether the agent is exploring genuinely new information.

Implements GH#6627.
"""

import json
from typing import Any

from autobot_shared.content_digest import content_digest
from autobot_shared.text_tokens import word_token_list


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
    return word_token_list(text, split_underscore=False)


def normalized_content_hash(content: Any) -> str:
    """Return a stable SHA-256 hex digest of normalized content."""
    return content_digest(normalize_content(content))


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
