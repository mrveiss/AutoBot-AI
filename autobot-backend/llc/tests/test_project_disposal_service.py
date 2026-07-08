# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Disposal cascade: work-items→sprints→project→linked non-shared source (#11129 P2).

Patch strategy: project_disposal lazy-imports get_source / delete_source_and_cleanup
inside _dispose_source. The llc/tests/conftest.py ``_shield_codebase_analytics_package``
hook registers a package stub whose __path__ points at the real directory, so
``patch("api.codebase_analytics.source_storage.get_source")`` loads the REAL submodule
(without running the heavy __init__.py) and auto-restores at the end of each ``with`` —
no module-level sys.modules surgery, so nothing leaks into sibling analytics suites.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from llc.services.project_disposal import dispose


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
