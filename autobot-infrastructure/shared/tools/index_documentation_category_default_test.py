# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``get_collection_stats`` (#14047).

``get_collection_stats`` is a void, log-only script entry point around a real
``ChromaDBIndexer`` — mocked here since it has no return-value seam;
behaviour is asserted via the logged "Chunks by category" breakdown.

Loaded by explicit path (review of #14047): the repo has TWO files named
``index_documentation.py`` (this one, and
``shared/scripts/utilities/index_documentation.py``, which has no
``get_collection_stats``). A bare ``from index_documentation import ...``
resolves whichever directory happens to be first on ``sys.path``, binding to
the wrong module depending on invocation order. Installed into
``sys.modules`` only for the test (removed in the same fixture, matching
``repo_tests/sys_modules_leak_guard.py``'s install/remove-in-same-scope
convention) so ``unittest.mock.patch``'s string target still resolves.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from constants.threshold_constants import CategoryDefaults

_MODULE_PATH = Path(__file__).parent / "index_documentation.py"


@pytest.fixture()
def index_documentation():
    spec = importlib.util.spec_from_file_location("index_documentation", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["index_documentation"] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        del sys.modules["index_documentation"]


def _mock_indexer(metadatas):
    indexer = MagicMock()
    indexer.collection.count.return_value = len(metadatas)
    indexer.collection.get.return_value = {"metadatas": metadatas}
    return indexer


def test_missing_category_defaults_to_unknown(index_documentation, caplog):
    with patch("index_documentation.ChromaDBIndexer", return_value=_mock_indexer([{"file_path": "a.md"}])):
        with caplog.at_level(logging.INFO):
            index_documentation.get_collection_stats()

    assert f"- {CategoryDefaults.UNKNOWN}: 1 chunks" in caplog.text


def test_explicit_category_overrides_default(index_documentation, caplog):
    metadatas = [{"file_path": "a.md", "category": "security"}]
    with patch("index_documentation.ChromaDBIndexer", return_value=_mock_indexer(metadatas)):
        with caplog.at_level(logging.INFO):
            index_documentation.get_collection_stats()

    assert "- security: 1 chunks" in caplog.text
    assert CategoryDefaults.UNKNOWN not in caplog.text
