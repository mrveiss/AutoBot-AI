# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for knowledge.search.map_kb_result_to_dict. Issue #10740.

Verifies:
  - All four keys present in the output (content, source, score, metadata)
  - node_id used as source when present
  - doc_id used as source fallback when node_id absent
  - Empty string source when neither node_id nor doc_id present
  - Score and metadata defaults on missing keys
  - Empty input dict produces all-default values (no crash)
"""

import pytest

from knowledge.search import map_kb_result_to_dict


class TestMapKbResultToDict:
    """Tests for the canonical single-row KB result mapper."""

    def test_all_keys_present_in_output(self):
        raw = {"content": "hello", "node_id": "n1", "score": 0.8, "metadata": {"k": "v"}}
        result = map_kb_result_to_dict(raw)
        assert set(result.keys()) == {"content", "source", "score", "metadata"}

    def test_content_mapped(self):
        result = map_kb_result_to_dict({"content": "fact text", "node_id": "n1", "score": 0.5, "metadata": {}})
        assert result["content"] == "fact text"

    def test_source_prefers_node_id(self):
        raw = {"content": "x", "node_id": "node-abc", "doc_id": "doc-xyz", "score": 0.7, "metadata": {}}
        assert map_kb_result_to_dict(raw)["source"] == "node-abc"

    def test_source_falls_back_to_doc_id_when_no_node_id(self):
        raw = {"content": "x", "doc_id": "doc-xyz", "score": 0.7, "metadata": {}}
        assert map_kb_result_to_dict(raw)["source"] == "doc-xyz"

    def test_source_empty_string_when_neither_id_present(self):
        raw = {"content": "x", "score": 0.5, "metadata": {}}
        assert map_kb_result_to_dict(raw)["source"] == ""

    def test_score_mapped(self):
        result = map_kb_result_to_dict({"content": "", "node_id": "n", "score": 0.92, "metadata": {}})
        assert result["score"] == pytest.approx(0.92)

    def test_metadata_mapped(self):
        meta = {"fact_id": "abc", "source": "readme"}
        result = map_kb_result_to_dict({"content": "", "node_id": "n", "score": 0.1, "metadata": meta})
        assert result["metadata"] == meta

    def test_empty_dict_returns_all_defaults(self):
        result = map_kb_result_to_dict({})
        assert result == {"content": "", "source": "", "score": 0.0, "metadata": {}}

    def test_score_default_zero_when_missing(self):
        result = map_kb_result_to_dict({"content": "c", "node_id": "n"})
        assert result["score"] == 0.0

    def test_metadata_default_empty_dict_when_missing(self):
        result = map_kb_result_to_dict({"content": "c", "node_id": "n", "score": 0.5})
        assert result["metadata"] == {}

    def test_content_default_empty_string_when_missing(self):
        result = map_kb_result_to_dict({"node_id": "n", "score": 0.5, "metadata": {}})
        assert result["content"] == ""

    def test_list_comprehension_maps_multiple_rows(self):
        rows = [
            {"content": f"doc {i}", "node_id": f"node-{i}", "score": 0.9 - i * 0.1, "metadata": {}} for i in range(3)
        ]
        results = [map_kb_result_to_dict(r) for r in rows]
        assert len(results) == 3
        for i, r in enumerate(results):
            assert r["content"] == f"doc {i}"
            assert r["source"] == f"node-{i}"
