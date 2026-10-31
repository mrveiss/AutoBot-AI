# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Test helper: a GraphRAGService whose graph reads default to the unscoped sentinel (#18825).

Existing service tests exercise traversal, blending and timeouts, not scoping, so they read
across owners on purpose. Owner scoping itself is proved in ``test_owner_scope_18825.py``.
"""

import inspect
from typing import Any, Callable

from autobot_memory_graph.owner_scope import UNSCOPED_ALL_USERS
from services.graph_rag_service import GraphRAGService as _BaseGraphRAGService

_OWNER_SCOPED_METHODS = (
    "graph_aware_search",
    "find_connection_path",
    "_fetch_related_entities_parallel",
    "_expand_via_graph",
    "_extract_entities_from_results",
)


def _with_default_owner(method: Callable) -> Callable:
    """Supply ``owner=UNSCOPED_ALL_USERS`` only when the caller (a test or an internal call) gave none."""
    signature = inspect.signature(method)

    async def call(*args: Any, **kwargs: Any) -> Any:
        if "owner" not in signature.bind_partial(*args, **kwargs).arguments:
            kwargs["owner"] = UNSCOPED_ALL_USERS
        return await method(*args, **kwargs)

    return call


def unscoped(service: Any) -> Any:
    """Default the service's owner-scoped methods to the unscoped sentinel; an explicit or positional owner wins."""
    for name in _OWNER_SCOPED_METHODS:
        setattr(service, name, _with_default_owner(getattr(service, name)))
    return service


class UnscopedGraphRAGService(_BaseGraphRAGService):
    """GraphRAGService whose owner-scoped methods default to the unscoped sentinel (test double)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        unscoped(self)


#: Tests import this name so they exercise the real service API without repeating ``owner=`` everywhere.
GraphRAGService = UnscopedGraphRAGService
