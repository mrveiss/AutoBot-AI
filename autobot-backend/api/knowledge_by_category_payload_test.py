#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Issue #12370: the ``GET /api/knowledge_base/facts/by_category`` browse list
must ship only a snippet (``content``), never the entire document
(``full_content``). The full text is lazy-loaded per fact via
``GET /api/knowledge_base/fact/{fact_key}``.

These tests pin the payload contract:
    * the list-item builder omits ``full_content`` and truncates ``content``;
    * the list response model no longer declares ``full_content``;
    * the detail endpoint's content extractor still returns the full text.
"""

import json

import pytest


@pytest.fixture
def large_fact_data():
    """Redis ``hgetall`` shape (bytes keys/values) for a >500-char document."""
    content = "x" * 1200
    return content, {
        b"content": content.encode("utf-8"),
        b"metadata": json.dumps({"title": "Big Doc", "type": "note"}).encode("utf-8"),
    }


class TestBrowseListOmitsFullContent:
    """The browse list ships a snippet only — never full_content."""

    def test_process_fact_data_omits_full_content(self, large_fact_data):
        from api.knowledge import _process_fact_data

        content, fact_data = large_fact_data
        result = _process_fact_data(fact_data, "tools", "fact:abc")

        assert result is not None
        # Issue #12370: the entire document must NOT be in the list item.
        assert "full_content" not in result
        # Snippet is truncated to 500 chars + ellipsis.
        assert result["content"].endswith("...")
        assert len(result["content"]) == 503
        assert result["content"][:-3] == content[:500]
        # The fields a browse list actually needs are present.
        assert result["key"] == "fact:abc"
        assert result["title"] == "Big Doc"
        assert result["category"] == "tools"
        assert result["type"] == "note"
        assert isinstance(result["metadata"], dict)

    def test_short_fact_content_not_ellipsised(self):
        from api.knowledge import _process_fact_data

        short = "nmap is a network scanner"
        fact_data = {
            b"content": short.encode("utf-8"),
            b"metadata": json.dumps({"title": "nmap"}).encode("utf-8"),
        }
        result = _process_fact_data(fact_data, "tools", "fact:xyz")

        assert result is not None
        assert "full_content" not in result
        # Short facts arrive whole (no trailing ellipsis) so the client
        # renders them without a detail round-trip.
        assert result["content"] == short

    def test_response_model_no_longer_declares_full_content(self):
        from knowledge.schemas.entries import FactByCategoryEntry

        # Issue #12370: contract (OpenAPI/api.ts) must not advertise the field.
        assert "full_content" not in FactByCategoryEntry.model_fields
        assert "content" in FactByCategoryEntry.model_fields


class TestDetailEndpointCarriesFullContent:
    """The per-fact detail endpoint remains the lazy-load source of truth."""

    def test_extract_fact_content_returns_full_untruncated_text(self, large_fact_data):
        from api.knowledge import _extract_fact_content

        content, _ = large_fact_data
        # Detail endpoint returns the whole document, untruncated, in `content`.
        extracted = _extract_fact_content({"content": content})

        assert extracted == content
        assert len(extracted) == 1200
        assert not extracted.endswith("...")

    def test_detail_response_model_exposes_content(self):
        from knowledge.schemas.entries import FactByKeyResponse

        # The detail response carries the full document under `content`.
        assert "content" in FactByKeyResponse.model_fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
