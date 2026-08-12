# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``_convert_results_to_documents`` (#14047)."""

from api.knowledge_search import _convert_results_to_documents
from constants.threshold_constants import CategoryDefaults


def test_missing_category_defaults_to_general():
    docs = _convert_results_to_documents([{"content": "hi", "metadata": {}}], "query")

    assert docs[0]["metadata"]["category"] == CategoryDefaults.GENERAL


def test_explicit_category_overrides_default():
    docs = _convert_results_to_documents([{"content": "hi", "metadata": {"category": "security"}}], "query")

    assert docs[0]["metadata"]["category"] == "security"
