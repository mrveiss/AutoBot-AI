# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SearchMixin's basic vector path must not re-enter itself via VectorSearchEngine (#15165).

Traced by hand on #15165: a request whose params resolve to the "basic
vector search path" (``knowledge/search.py``, no ``limit``/``tags``/
``category``/``min_score``/``board_id``) calls ``VectorSearchEngine.search()``,
which dispatches to ``_CPUBackend.search()`` (no GPU/NPU in CI). That backend's
own dependency is ``get_knowledge_base().search(...)`` -- the SAME high-level
``search()`` orchestrator the caller is already inside of. Nothing distinguishes
"called by a real caller" from "called by _CPUBackend re-entering itself", so
the second call takes the exact same basic path again, calls
``VectorSearchEngine`` again, reaches ``_CPUBackend`` again, and so on -- with
no base case found anywhere in this chain.

This drives ``SearchMixin.search()`` down that basic path directly (the exact
parameter shape ``_CPUBackend`` itself uses), with the REAL ``VectorSearchEngine``
and the REAL ``_CPUBackend`` running -- ``_CPUBackend``'s only dependency,
``get_knowledge_base``, is mocked to return this same counting instance, which
is its entire I/O boundary (it has no other external call of its own; see
``knowledge/vector_search_engine.py:204-221``). A capped counter is used
instead of letting the recursion actually exhaust the stack: the count itself
is the evidence, and it stays deterministic and fast either way.

Hardware selection is forced to CPU (matching the CI-default in
``vector_search_engine_test.py::TestHardwareSelection``) so this cannot flake
on a host that happens to report a GPU/NPU.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import knowledge.vector_search_engine as vse
from knowledge.search import SearchMixin

_RECURSION_CAP = 3


class _CountingSearchMixin(SearchMixin):
    """A minimal SearchMixin host: real search() chain, no other collaborators."""

    def __init__(self) -> None:
        super().__init__()
        self.vector_store = MagicMock()  # truthy: _validate_search_inputs must not short-circuit
        self.entry_count = 0

    def ensure_initialized(self) -> None:
        """No-op: the real impl lives in KnowledgeBaseCore, irrelevant to this path."""

    async def _execute_vector_search(self, query, similarity_top_k, filters=None):
        """Stand in for the real ChromaDB/embedding leaf -- irrelevant to this recursion.

        Real once the fix lands: validate/sanitize/dispatch logic all runs for
        real; only the actual network/model call is replaced, the same way a
        unit test always stubs its true I/O boundary.
        """
        return []

    async def search(self, *args, **kwargs):
        self.entry_count += 1
        if self.entry_count > _RECURSION_CAP:
            # Re-entry beyond the cap is itself the finding; stop here rather
            # than actually exhausting the interpreter's call stack.
            return []
        return await super().search(*args, **kwargs)


@pytest.mark.asyncio
async def test_basic_vector_path_reaches_the_engine_exactly_once():
    kb = _CountingSearchMixin()

    with (
        patch.object(vse, "_npu_enabled", return_value=False),
        patch.object(vse, "_gpu_available", return_value=False),
        patch("knowledge.get_knowledge_base", AsyncMock(return_value=kb)),
    ):
        await kb.search("AutoBot system architecture", top_k=5, mode="vector")

    assert kb.entry_count == 1, (
        f"search() was entered {kb.entry_count} times for one basic-path call (capped at "
        f"{_RECURSION_CAP} to stay deterministic) -- VectorSearchEngine._CPUBackend.search() "
        "re-enters the high-level search() orchestrator via get_knowledge_base().search(...) "
        "instead of doing its own vector-store I/O (#15165). A real caller and _CPUBackend's "
        "own re-entry are indistinguishable, so every re-entry takes the same basic path again."
    )
