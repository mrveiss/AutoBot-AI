# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``get_collection_stats`` (#14047).

``get_collection_stats`` is a void, log-only script entry point around a real
``ChromaDBIndexer`` — mocked here since it has no return-value seam;
behaviour is asserted via the logged "Chunks by category" breakdown.
"""

import logging
from unittest.mock import MagicMock, patch

from index_documentation import get_collection_stats

from constants.threshold_constants import CategoryDefaults


def _mock_indexer(metadatas):
    indexer = MagicMock()
    indexer.collection.count.return_value = len(metadatas)
    indexer.collection.get.return_value = {"metadatas": metadatas}
    return indexer


def test_missing_category_defaults_to_unknown(caplog):
    with patch("index_documentation.ChromaDBIndexer", return_value=_mock_indexer([{"file_path": "a.md"}])):
        with caplog.at_level(logging.INFO):
            get_collection_stats()

    assert f"- {CategoryDefaults.UNKNOWN}: 1 chunks" in caplog.text


def test_explicit_category_overrides_default(caplog):
    metadatas = [{"file_path": "a.md", "category": "security"}]
    with patch("index_documentation.ChromaDBIndexer", return_value=_mock_indexer(metadatas)):
        with caplog.at_level(logging.INFO):
            get_collection_stats()

    assert "- security: 1 chunks" in caplog.text
    assert CategoryDefaults.UNKNOWN not in caplog.text
