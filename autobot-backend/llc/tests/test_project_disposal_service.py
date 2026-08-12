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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.project_disposal import dispose


def _project(code_source_id=None):
    return SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), code_source_id=code_source_id)


@pytest.mark.asyncio
async def test_dispose_deletes_children_then_project_and_source():
    project = _project(code_source_id="src-1")
    session = AsyncMock()
    # #13920: dispose() now SELECTs the child work-item and sprint ids before
    # deleting them, so their KB collections can be dropped. A bare AsyncMock
    # makes result.scalars() a coroutine; shape the result so `.scalars().all()`
    # returns a real (empty) list.
    _result = MagicMock()
    _result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=_result)
    non_shared_source = SimpleNamespace(id="src-1", shared_with=[])
    with (
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=non_shared_source)),
        patch(
            "api.codebase_analytics.source_service.delete_source_and_cleanup", AsyncMock(return_value=True)
        ) as del_src,
    ):
        await dispose(project, session)
    del_src.assert_awaited_once_with("src-1")
    # Exactly three bulk-delete statements: work-items, sprints, then project.
    # 3 deletes + the 2 id SELECTs added by #13920
    assert session.execute.await_count == 5


@pytest.mark.asyncio
async def test_dispose_keeps_shared_source():
    project = _project(code_source_id="src-2")
    session = AsyncMock()
    # #13920: dispose() now SELECTs the child work-item and sprint ids before
    # deleting them, so their KB collections can be dropped. A bare AsyncMock
    # makes result.scalars() a coroutine; shape the result so `.scalars().all()`
    # returns a real (empty) list.
    _result = MagicMock()
    _result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=_result)
    shared = SimpleNamespace(id="src-2", shared_with=["someone-else"])
    with (
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=shared)),
        patch("api.codebase_analytics.source_service.delete_source_and_cleanup", AsyncMock()) as del_src,
    ):
        await dispose(project, session)
    del_src.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispose_no_source_is_noop_on_source():
    project = _project(code_source_id=None)
    session = AsyncMock()
    # #13920: dispose() now SELECTs the child work-item and sprint ids before
    # deleting them, so their KB collections can be dropped. A bare AsyncMock
    # makes result.scalars() a coroutine; shape the result so `.scalars().all()`
    # returns a real (empty) list.
    _result = MagicMock()
    _result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=_result)
    with patch("api.codebase_analytics.source_service.delete_source_and_cleanup", AsyncMock()) as del_src:
        await dispose(project, session)
    del_src.assert_not_awaited()
