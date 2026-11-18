# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19156 review: a failed NPU engine initialize must not be cached as the module singleton."""

from types import SimpleNamespace
from unittest import mock

import pytest

import npu_semantic_search as mod
from npu_semantic_search import NPUSemanticSearch


def _patch_engine_deps(accessor):
    """Patch the globals `initialize` reads (resolved via __globals__, immune to module reloads)."""
    g = NPUSemanticSearch.initialize.__globals__
    return mock.patch.dict(
        g,
        {
            "get_knowledge_base_async": accessor,
            "get_ai_accelerator": mock.AsyncMock(return_value=object()),
        },
    )


@pytest.mark.asyncio
async def test_failed_initialize_is_not_cached_and_next_call_retries():
    getter_globals = mod.get_npu_search_engine.__globals__
    kb = SimpleNamespace(vector_store=object())
    accessor = mock.AsyncMock(side_effect=[None, kb])

    with (
        mock.patch.dict(getter_globals, {"_npu_search_engine": None}),
        _patch_engine_deps(accessor),
        mock.patch.object(NPUSemanticSearch, "__init__", lambda self: setattr(self, "use_gpu_search", False)),
        mock.patch.object(NPUSemanticSearch, "_initialize_chromadb", mock.AsyncMock()),
        mock.patch.object(NPUSemanticSearch, "_test_npu_connectivity", mock.AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="unavailable"):
            await mod.get_npu_search_engine()
        assert getter_globals["_npu_search_engine"] is None

        engine = await mod.get_npu_search_engine()
        assert engine.knowledge_base is kb
        assert getter_globals["_npu_search_engine"] is engine
        assert await mod.get_npu_search_engine() is engine

    assert accessor.await_count == 2
