# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the single-sourced markdown chunking helpers (Issue #12663).

Covers the behaviour shared by doc_indexer.py's ``_chunk_markdown`` (service)
and index_documentation.py's ``chunk_markdown`` (standalone CLI) — both call
into these helpers for H2/H3 section splitting.
"""

from autobot_shared.doc_chunking import (
    chunk_large_content,
    create_chunk,
    estimate_tokens,
    process_h2_sections,
    process_h3_subsections,
)


class TestEstimateTokens:
    def test_empty_string_is_zero(self) -> None:
        assert estimate_tokens("") == 0

    def test_roughly_four_chars_per_token(self) -> None:
        assert estimate_tokens("x" * 400) == 100


class TestCreateChunk:
    def test_returns_expected_metadata_shape(self) -> None:
        chunk = create_chunk(
            content="body text",
            section="Section A",
            subsection="Sub A",
            file_path="docs/example.md",
            doc_type="documentation",
            category="general",
            title="Example Doc",
        )
        assert chunk == {
            "content": "body text",
            "section": "Section A",
            "subsection": "Sub A",
            "file_path": "docs/example.md",
            "doc_type": "documentation",
            "category": "general",
            "title": "Example Doc",
        }

    def test_subsection_may_be_none(self) -> None:
        chunk = create_chunk("c", "S", None, "f.md", "documentation", "general", "T")
        assert chunk["subsection"] is None


class TestChunkLargeContent:
    def test_splits_paragraphs_exceeding_800_tokens(self) -> None:
        # Each paragraph ~840 chars => ~210 tokens; 5 paragraphs > 800 tokens
        # forces at least one split boundary.
        paragraphs = ["word " * 168 for _ in range(5)]
        content = "\n\n".join(paragraphs)
        chunks: list = []
        chunk_large_content(content, "Section", None, "f.md", "documentation", "general", "T", chunks)
        assert len(chunks) >= 2
        # Every emitted chunk carries the section metadata through.
        for chunk in chunks:
            assert chunk["section"] == "Section"
            assert chunk["file_path"] == "f.md"

    def test_small_content_yields_single_chunk(self) -> None:
        chunks: list = []
        chunk_large_content("short paragraph", "Section", "Sub", "f.md", "documentation", "general", "T", chunks)
        assert len(chunks) == 1
        assert chunks[0]["content"] == "short paragraph"
        assert chunks[0]["subsection"] == "Sub"

    def test_empty_content_yields_single_empty_chunk(self) -> None:
        # "".split("\n\n") == [""] — matches the pre-existing (duplicated)
        # behaviour in both original forks: one chunk with empty content.
        chunks: list = []
        chunk_large_content("", "Section", None, "f.md", "documentation", "general", "T", chunks)
        assert len(chunks) == 1
        assert chunks[0]["content"] == ""


class TestProcessH3Subsections:
    def test_substantial_h3_becomes_chunk(self) -> None:
        h3_splits = ["", "### Detail", "word " * 40]  # ~50 tokens > 30 threshold
        chunks: list = []
        process_h3_subsections(h3_splits, "Parent", "f.md", "documentation", "general", "T", chunks)
        assert len(chunks) == 1
        assert chunks[0]["section"] == "Parent"
        assert chunks[0]["subsection"] == "Detail"

    def test_trivial_h3_is_dropped(self) -> None:
        h3_splits = ["", "### Tiny", "one two"]  # well under the 30-token floor
        chunks: list = []
        process_h3_subsections(h3_splits, "Parent", "f.md", "documentation", "general", "T", chunks)
        assert chunks == []

    def test_oversized_h3_is_paragraph_split(self) -> None:
        big_content = "\n\n".join("word " * 168 for _ in range(6))  # > 1000 tokens
        h3_splits = ["", "### Big", big_content]
        chunks: list = []
        process_h3_subsections(h3_splits, "Parent", "f.md", "documentation", "general", "T", chunks)
        assert len(chunks) >= 2

    def test_missing_h3_header_defaults_to_subsection(self) -> None:
        h3_splits = ["", "not a header", "word " * 40]
        chunks: list = []
        process_h3_subsections(h3_splits, "Parent", "f.md", "documentation", "general", "T", chunks)
        assert chunks[0]["subsection"] == "Subsection"


class TestProcessH2Sections:
    def test_intro_and_subsection_both_captured(self) -> None:
        h2_splits = [
            "",
            "## Overview",
            ("word " * 40) + "\n\n### Details\n\n" + ("word " * 40),
        ]
        chunks: list = []
        process_h2_sections(h2_splits, "f.md", "documentation", "general", "T", chunks)
        sections = {(c["section"], c["subsection"]) for c in chunks}
        assert ("Overview", None) in sections
        assert ("Overview", "Details") in sections

    def test_trivial_h2_intro_without_h3_yields_no_chunks(self) -> None:
        h2_splits = ["", "## Empty", "short"]
        chunks: list = []
        process_h2_sections(h2_splits, "f.md", "documentation", "general", "T", chunks)
        assert chunks == []

    def test_missing_h2_header_defaults_to_section(self) -> None:
        h2_splits = ["", "not a header", "word " * 40]
        chunks: list = []
        process_h2_sections(h2_splits, "f.md", "documentation", "general", "T", chunks)
        assert chunks[0]["section"] == "Section"
