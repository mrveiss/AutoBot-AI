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

    def test_none_only_for_service_key_not_other_identityless(self):
        """Only the internal service key ({"service": True}) is unscoped; any other
        identity-less authenticated caller (e.g. a sub-only token) fails closed."""
        from api.codebase_analytics.endpoints.shared import _NO_OWNER_ID, _caller_owner_id

        assert _caller_owner_id(None) is None
        # Real internal-service dict (auth_middleware.py: minted with service=True).
        assert _caller_owner_id({"username": "service:slm", "role": "admin", "service": True}) is None
        # #12375 item c: an SLM-minted token carrying identity only in sub/username
        # (no id/user_id and NOT the service key) must NOT get unscoped see-all.
        assert _caller_owner_id({"sub": "carol", "role": "admin"}) == _NO_OWNER_ID
        assert _caller_owner_id({"username": "dave", "role": "admin"}) == _NO_OWNER_ID


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
        """Internal service key (service=True, no id) keeps unscoped access to any source."""
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            await shared.authorize_source_access(
                src.id, {"username": "service:slm", "role": "admin", "service": True}
            )

    async def test_subonly_token_denied_on_foreign_private(self):
        """#12375 item c: an authenticated admin whose token carries only sub/username
        (no id, not the service key) must be denied a foreign PRIVATE source, not
        granted unscoped see-all. Non-disclosing 404."""
        from api.codebase_analytics.endpoints import shared

        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            with pytest.raises(HTTPException) as exc:
                await shared.authorize_source_access(src.id, {"sub": "mallory", "role": "admin"})
            assert exc.value.status_code == 404
            # But a PUBLIC source is still reachable by the same identity-less caller.
            pub = _source(owner_id="alice", access=SourceAccess.PUBLIC)
        with patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=pub),
        ):
            await shared.authorize_source_access(pub.id, {"sub": "mallory", "role": "admin"})

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


class TestPatternAnalyzeBodyAuthz:
    """#12375 item a: /patterns/analyze takes source_id in the BODY, so the
    router-level require_source_access (path/query only) cannot gate it; the
    handler must authorize it before enqueuing the Celery task."""

    async def _call(self, user, src):
        from api.codebase_analytics.endpoints import pattern_analysis as pa

        req = pa.PatternAnalysisRequest(source_id="s1", path="/tmp/proj")
        delay = _FakeDelay()
        with patch.object(pa.run_pattern_analysis, "delay", delay), patch.object(
            pa, "store_latest_task_id", AsyncMock()
        ), patch(
            "auth_middleware.get_current_user", AsyncMock(return_value=user)
        ), patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=src),
        ):
            result = await pa.start_pattern_analysis(req, _FakeRequest())
        return result, delay

    async def test_foreign_private_source_blocks_before_enqueue(self):
        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        with pytest.raises(HTTPException) as exc:
            await self._call({"id": "bob"}, src)
        assert exc.value.status_code == 404

    async def test_owner_may_enqueue(self):
        src = _source(owner_id="alice", access=SourceAccess.PRIVATE)
        result, delay = await self._call({"id": "alice"}, src)
        assert delay.called
        assert result.status == "pending"


class _FakeDelay:
    called = False

    def __call__(self, *a, **k):
        self.called = True

        class _R:
            id = "task-123"

        return _R()


class _FakeRequest:
    """Minimal stand-in; get_current_user is patched so its internals are unused."""
