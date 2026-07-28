# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for canonical chunk_text() — Issue #12736 (fork-convergence D3)."""

from utils.text_chunking import chunk_text


def test_empty_text_default_returns_empty_list() -> None:
    assert chunk_text("") == []


def test_empty_text_with_fallback_returns_original() -> None:
    assert chunk_text("", fallback_to_original=True) == [""]


def test_short_text_single_chunk() -> None:
    assert chunk_text("hello world", max_chars=2000) == ["hello world"]


def test_paragraphs_combine_when_under_limit() -> None:
    text = "Para one.\n\nPara two."
    assert chunk_text(text, max_chars=2000) == ["Para one.\n\nPara two."]


def test_split_oversized_true_hard_splits_long_paragraph() -> None:
    text = "X" * 25
    chunks = chunk_text(text, max_chars=10, split_oversized=True)
    assert chunks == ["XXXXXXXXXX", "XXXXXXXXXX", "XXXXX"]


def test_split_oversized_false_keeps_paragraph_intact() -> None:
    text = "X" * 25
    chunks = chunk_text(text, max_chars=10, split_oversized=False)
    assert chunks == ["X" * 25]


def test_separator_len_affects_flush_threshold() -> None:
    text = "aaaaa\n\nbbbbb"  # each paragraph 5 chars
    # max_chars=10: with separator_len=0, "aaaaa"+"bbbbb" = 10 chars -> fits in one chunk
    assert chunk_text(text, max_chars=10, separator_len=0) == ["aaaaa\n\nbbbbb"]
    # with separator_len=2, 5+2+5=12 > 10 -> must split into two chunks
    assert chunk_text(text, max_chars=10, separator_len=2) == ["aaaaa", "bbbbb"]


def test_file_server_params_reproduce_original_semantics() -> None:
    text = "short intro.\n\n" + ("Y" * 30) + "\n\nshort outro."
    chunks = chunk_text(text, max_chars=10, separator_len=0, split_oversized=True, fallback_to_original=False)
    assert chunks == [
        "short intr",
        "o.",
        "YYYYYYYYYY",
        "YYYYYYYYYY",
        "YYYYYYYYYY",
        "short outr",
        "o.",
    ]


def test_cognition_seeder_params_reproduce_original_semantics() -> None:
    text = "short intro.\n\n" + ("Y" * 30) + "\n\nshort outro."
    chunks = chunk_text(text, max_chars=10, separator_len=2, split_oversized=False, fallback_to_original=True)
    assert chunks == ["short intro.", "Y" * 30, "short outro."]
