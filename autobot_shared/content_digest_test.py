# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`content_digest` reproduces every stored form byte-for-byte (#15722).

The expectations are the literal expressions each site used before the merge, evaluated here
over a corpus. A stored dedup key, change-detection hash or Chroma metadata value therefore
cannot have moved.
"""

import hashlib

import pytest

from autobot_shared.content_digest import FACT_DEDUP_WIDTH, content_digest, fact_dedup_key

CORPUS = ["", "a", "hello world", "  padded\n\ttext  ", "unicode: é中文\U0001f600", "x" * 10_000, "line1\r\nline2"]


@pytest.mark.parametrize("text", CORPUS)
def test_full_digest_matches_the_former_full_sites(text: str) -> None:
    # connectors.content_extraction.content_hash, knowledge_sync_incremental, document_version
    assert content_digest(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    # sites that wrote `.encode()` with the default codec
    assert content_digest(text) == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize("text", CORPUS)
def test_fact_dedup_key_matches_the_former_16_char_sites(text: str) -> None:
    # fact_store.content_hash, fact_projection, facts.py x4, content_fingerprint.compute_content_hash_key
    assert fact_dedup_key(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    assert FACT_DEDUP_WIDTH == 16


@pytest.mark.parametrize("width", [8, 12, 16, 32])
@pytest.mark.parametrize("text", CORPUS)
def test_a_named_width_is_a_prefix_of_the_full_digest(text: str, width: int) -> None:
    # analytics_code_generation [:12], ide_integration / pattern_analysis.storage [:16]
    assert content_digest(text, width=width) == hashlib.sha256(text.encode()).hexdigest()[:width]


def test_bytes_hash_as_themselves() -> None:
    assert content_digest(b"abc") == hashlib.sha256(b"abc").hexdigest()
