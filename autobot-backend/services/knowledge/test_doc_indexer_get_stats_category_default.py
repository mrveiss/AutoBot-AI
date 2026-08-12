# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``DocIndexerService.get_stats`` (#14047)."""

from unittest.mock import patch

import pytest

from constants.threshold_constants import CategoryDefaults

from .test_doc_indexer import _make_service


@pytest.mark.asyncio
async def test_missing_category_defaults_to_unknown():
    svc = _make_service(initialized=True, collection_count=1)

    with patch(
        "utils.chromadb_client.get_all_paginated",
        return_value={"metadatas": [{"file_path": "a.md"}]},
    ):
        result = await svc.get_stats()

    assert result["categories"] == {CategoryDefaults.UNKNOWN: 1}


@pytest.mark.asyncio
async def test_explicit_category_overrides_default():
    svc = _make_service(initialized=True, collection_count=1)

    with patch(
        "utils.chromadb_client.get_all_paginated",
        return_value={"metadatas": [{"file_path": "a.md", "category": "security"}]},
    ):
        result = await svc.get_stats()

    assert result["categories"] == {"security": 1}
