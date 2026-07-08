# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Disposal cascade: work-items→sprints→project→linked non-shared source (#11129 P2).

Patch strategy: lazy imports inside _dispose_source → patch at source modules.
The source modules are pre-imported so patch() can resolve the attribute path.
"""
import sys
import types
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# Pre-stub the codebase_analytics modules so patch() can resolve them
# without triggering their heavy optional dependencies (Redis, ChromaDB).
import api as _api_pkg  # noqa: E402 — must precede sys.modules surgery

_analytics_pkg = types.ModuleType("api.codebase_analytics")
sys.modules["api.codebase_analytics"] = _analytics_pkg
_api_pkg.codebase_analytics = _analytics_pkg  # type: ignore[attr-defined]

_storage_mod = types.ModuleType("api.codebase_analytics.source_storage")
_storage_mod.get_source = AsyncMock()  # type: ignore[attr-defined]
sys.modules["api.codebase_analytics.source_storage"] = _storage_mod

_service_mod = types.ModuleType("api.codebase_analytics.source_service")
_service_mod.delete_source_and_cleanup = AsyncMock()  # type: ignore[attr-defined]
sys.modules["api.codebase_analytics.source_service"] = _service_mod

# Attach as attributes on the parent so dotted patch targets resolve.
_analytics_pkg.source_storage = _storage_mod  # type: ignore[attr-defined]
_analytics_pkg.source_service = _service_mod  # type: ignore[attr-defined]

from llc.services.project_disposal import dispose  # noqa: E402


def _project(code_source_id=None):
    return SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), code_source_id=code_source_id)


@pytest.mark.asyncio
async def test_dispose_deletes_children_then_project_and_source():
    project = _project(code_source_id="src-1")
    session = AsyncMock()
    session.execute = AsyncMock()
    non_shared_source = SimpleNamespace(id="src-1", shared_with=[])
    with patch(
        "api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=non_shared_source)
    ), patch(
        "api.codebase_analytics.source_service.delete_source_and_cleanup", AsyncMock(return_value=True)
    ) as del_src:
        await dispose(project, session)
    del_src.assert_awaited_once_with("src-1")
    # work-items + sprints deleted via bulk delete statements, then project.
    assert session.execute.await_count >= 2


@pytest.mark.asyncio
async def test_dispose_keeps_shared_source():
    project = _project(code_source_id="src-2")
    session = AsyncMock()
    session.execute = AsyncMock()
    shared = SimpleNamespace(id="src-2", shared_with=["someone-else"])
    with patch(
        "api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=shared)
    ), patch(
        "api.codebase_analytics.source_service.delete_source_and_cleanup", AsyncMock()
    ) as del_src:
        await dispose(project, session)
    del_src.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispose_no_source_is_noop_on_source():
    project = _project(code_source_id=None)
    session = AsyncMock()
    session.execute = AsyncMock()
    with patch(
        "api.codebase_analytics.source_service.delete_source_and_cleanup", AsyncMock()
    ) as del_src:
        await dispose(project, session)
    del_src.assert_not_awaited()
