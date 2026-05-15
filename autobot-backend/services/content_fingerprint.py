#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Content Fingerprinting Service — SHA-256 hash-based KB cache invalidation.

Computes and validates content fingerprints for knowledge base entries to
detect source document changes and trigger cache invalidation.

Issue: #1375
"""

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_fingerprint(content: str) -> str:
    """Compute SHA-256 fingerprint of content after whitespace normalization.

    Normalizes whitespace before hashing so trivial formatting changes
    (extra spaces, trailing newlines) don't produce false mismatches.

    Args:
        content: Raw text content to fingerprint.

    Returns:
        Full 64-character hex SHA-256 digest.
    """
    normalized = " ".join(content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_fingerprint(content: str, stored_fingerprint: str) -> bool:
    """Check whether content still matches its stored fingerprint.

    Args:
        content: Current content text.
        stored_fingerprint: Previously stored SHA-256 hex digest.

    Returns:
        True if fingerprints match, False if content has changed.
    """
    return compute_fingerprint(content) == stored_fingerprint


def compute_content_hash_key(content: str) -> str:
    """Compute the 16-char truncated hash used for Redis dedup keys.

    Kept for backward compatibility with the existing ``content_hash:``
    key scheme in facts.py. Ref: #1375.

    Args:
        content: Raw text content.

    Returns:
        First 16 hex characters of SHA-256 digest (no normalization).
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def extract_fingerprint(metadata: dict) -> Optional[str]:
    """Extract stored content fingerprint from fact metadata.

    Args:
        metadata: Fact metadata dictionary.

    Returns:
        The stored fingerprint string, or None if absent.
    """
    return metadata.get("content_fingerprint")
