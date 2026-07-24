# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Authorization tests for source-scoped codebase analytics (Issue #12358).

The codebase-analytics router is admin-gated, but ``resolve_scan_root`` /
``get_source`` previously scoped to ANY ``source_id`` with no owner check, so one
admin could read another admin's PRIVATE source analytics. These tests assert the
per-source authorization layer: a caller may only reach a source they OWN, one
SHARED with them, a PUBLIC source, or an unowned/legacy source. An owned PRIVATE
source belonging to someone else returns 404 (non-disclosing), never the data.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.codebase_analytics.source_models import CodeSource, SourceAccess


def _source(**kwargs) -> CodeSource:
    defaults = {"name": "proj", "clone_path": "/tmp/proj"}
    defaults.update(kwargs)
    return CodeSource(**defaults)


class TestCallerOwnerId:
    """The caller identity must match how owner_id is written on create."""

    def test_prefers_id_then_user_id(self):
        from api.codebase_analytics.endpoints.shared import _caller_owner_id

        assert _caller_owner_id({"id": "alice", "user_id": "ignored"}) == "alice"
        assert _caller_owner_id({"user_id": "bob"}) == "bob"

    def test_none_for_identityless_caller(self):
        """Internal service key yields a synthetic admin with no id -> unscoped."""
        from api.codebase_analytics.endpoints.shared import _caller_owner_id

        assert _caller_owner_id(None) is None
        assert _caller_owner_id({"username": "service:slm", "role": "admin"}) is None


class TestAuthorizeSourceAccess:
    """authorize_source_access enforces _is_visible for the calling user."""

    async def test_owner_allowed(self):
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            # Owner reaching their own PRIVATE source: no exception raised.
            await shared.authorize_source_access(src.id, {"id": "alice"})

    async def test_shared_with_allowed(self):
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.SHARED, shared_with=["bob"])
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            await shared.authorize_source_access(src.id, {"id": "bob"})

    async def test_public_allowed(self):
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PUBLIC)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            await shared.authorize_source_access(src.id, {"id": "bob"})

    async def test_unowned_source_allowed(self):
        """Legacy/service-created source (owner_id None) stays admin-accessible."""
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id=None, access=SourceAccess.PRIVATE)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            await shared.authorize_source_access(src.id, {"id": "bob"})

    async def test_service_caller_allowed(self):
        """Internal service key (no id) keeps unscoped access to any source."""
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            await shared.authorize_source_access(src.id, {"username": "service:slm", "role": "admin"})

    async def test_foreign_private_source_returns_404(self):
        """The bug: another admin's PRIVATE source must 404, not return data."""
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            with pytest.raises(HTTPException) as exc:
                await shared.authorize_source_access(src.id, {"id": "bob"})
        assert exc.value.status_code == 404

    async def test_shared_source_but_not_shared_with_caller_returns_404(self):
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.SHARED, shared_with=["carol"])
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            with pytest.raises(HTTPException) as exc:
                await shared.authorize_source_access(src.id, {"id": "bob"})
        assert exc.value.status_code == 404

    async def test_unknown_source_returns_404(self):
        """A source_id that does not exist is non-disclosing (404)."""
        from api.codebase_analytics.endpoints import shared

        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                await shared.authorize_source_access("ghost", {"id": "bob"})
        assert exc.value.status_code == 404

    async def test_falsy_source_id_is_noop(self):
        """No source_id -> scan falls back to default/project root; no authz call."""
        from api.codebase_analytics.endpoints import shared

        get_source = AsyncMock(return_value=None)
        with patch("api.codebase_analytics.source_storage.get_source", get_source):
            await shared.authorize_source_access(None, {"id": "bob"})
            await shared.authorize_source_access("", {"id": "bob"})
        get_source.assert_not_called()


class TestRequireSourceAccessDependency:
    """The router dependency reads source_id from path/query and enforces authz."""

    def _request(self, *, path_params=None, query_params=None):
        from starlette.datastructures import QueryParams

        class _Req:
            pass

        req = _Req()
        req.path_params = path_params or {}
        req.query_params = QueryParams(query_params or {})
        return req

    async def test_query_source_id_authorized(self):
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        req = self._request(query_params={"source_id": src.id})
        with (
            patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "bob"})),
            patch(
                "api.codebase_analytics.source_storage.get_source",
                AsyncMock(return_value=src),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await shared.require_source_access(req)
        assert exc.value.status_code == 404

    async def test_path_source_id_authorized(self):
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        req = self._request(path_params={"source_id": src.id})
        with (
            patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "alice"})),
            patch(
                "api.codebase_analytics.source_storage.get_source",
                AsyncMock(return_value=src),
            ),
        ):
            # Owner via path param: allowed, no exception.
            await shared.require_source_access(req)

    async def test_no_source_id_is_noop(self):
        from api.codebase_analytics.endpoints import shared

        req = self._request()
        get_source = AsyncMock(return_value=None)
        with (
            patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "bob"})),
            patch("api.codebase_analytics.source_storage.get_source", get_source),
        ):
            await shared.require_source_access(req)
        get_source.assert_not_called()
