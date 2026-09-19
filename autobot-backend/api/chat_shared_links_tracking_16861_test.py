# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""View tracking and login enforcement for shared chat links (#16861).

GH#8996 shipped shareable links but never landed view_count/last_accessed_at
tracking or a require_login gate -- both left as "nice to haves" when #8996
closed. These test the two real behaviours directly against the actual
helpers (``_enforce_require_login``, ``_record_access``), the same pattern
``chat_shared_links_message_schema_test.py`` uses for ``_load_session_data``,
since standing up the full FastAPI app + DB session for this router is not
needed to prove either behaviour.
"""

import asyncio
import types

import pytest
from fastapi import HTTPException

import api.chat_shared_links as shared_links


def _link(require_login: bool = False, view_count: int = 0, last_accessed_at=None) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        require_login=require_login,
        view_count=view_count,
        last_accessed_at=last_accessed_at,
    )


class _FakeAuthMiddleware:
    def __init__(self, user: dict | None) -> None:
        self._user = user

    def get_user_from_request(self, request) -> dict | None:
        return self._user


class _FakeDB:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def test_enforce_require_login_is_a_noop_when_not_required() -> None:
    link = _link(require_login=False)
    shared_links._enforce_require_login(link, request=None)  # must not raise


def test_enforce_require_login_allows_an_authenticated_visitor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shared_links, "get_auth_middleware", lambda: _FakeAuthMiddleware({"username": "alice"}))
    link = _link(require_login=True)
    shared_links._enforce_require_login(link, request=None)  # must not raise


def test_enforce_require_login_rejects_an_anonymous_visitor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shared_links, "get_auth_middleware", lambda: _FakeAuthMiddleware(None))
    link = _link(require_login=True)

    with pytest.raises(HTTPException) as exc_info:
        shared_links._enforce_require_login(link, request=None)

    assert exc_info.value.status_code == 401


def test_record_access_increments_view_count_and_stamps_last_accessed() -> None:
    link = _link(view_count=3, last_accessed_at=None)
    db = _FakeDB()

    asyncio.run(shared_links._record_access(link, db))

    assert link.view_count == 4
    assert link.last_accessed_at is not None
    assert db.committed is True


def test_record_access_is_cumulative_across_repeated_visits() -> None:
    link = _link(view_count=0)
    db = _FakeDB()

    asyncio.run(shared_links._record_access(link, db))
    asyncio.run(shared_links._record_access(link, db))
    asyncio.run(shared_links._record_access(link, db))

    assert link.view_count == 3


def test_model_declares_the_three_tracking_columns() -> None:
    """Precondition: the ORM model must actually carry these columns (#16861)."""
    from models.chat_shared_link import ChatSharedLink

    columns = ChatSharedLink.__table__.columns
    assert columns["view_count"].nullable is False
    assert columns["require_login"].nullable is False
    assert columns["last_accessed_at"].nullable is True


def _load_migration_module():
    """Alembic loads version files by path, not by a valid Python module name
    (they start with a digit) -- mirror that here instead of importing."""
    import importlib.util
    import os

    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "migrations",
        "versions",
        "20260919_094_shared_link_tracking.py",
    )
    spec = importlib.util.spec_from_file_location("shared_link_tracking_20260919_094", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_head_matches_the_current_chain_not_the_stale_stash_draft() -> None:
    """The rescued stash draft pointed its down_revision at ``20260531_050``,
    which already has a different direct successor on ``main`` -- this pins
    the rebased value instead of letting it silently drift again."""
    migration = _load_migration_module()
    assert migration.down_revision == "20260916_093"
    assert migration.revision == "20260919_094"
