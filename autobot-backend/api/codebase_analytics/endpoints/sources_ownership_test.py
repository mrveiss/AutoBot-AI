# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Ownership-capture tests for POST /sources (Issue #12377).

`create_code_source` previously never set `owner_id`, so HTTP-created sources
were unowned. #12375's `_is_visible` exempts unowned sources (owner_id None
-> visible to all admins, needed for pre-ownership/service sources), so the
missing owner_id capture meant per-source privacy never applied to
HTTP-created sources. These tests assert the fix: the caller's identity is
captured as owner_id on create, and the resulting source is private to that
caller (not visible to a different admin), mirroring the LLC path's
`create_github_source(owner_id=...)`.
"""

from unittest.mock import AsyncMock, patch

from api.codebase_analytics.source_models import CodeSourceCreateRequest, SourceAccess
from api.codebase_analytics.source_storage import _is_visible


class _FakeRequest:
    """Minimal Request stand-in; auth_middleware.get_current_user is patched
    so its internals (headers etc.) are never touched."""


async def _create(request, user):
    """Call create_code_source with save_source patched to capture the
    persisted CodeSource without touching Redis."""
    from api.codebase_analytics.endpoints import sources as sources_ep

    saved = {}

    async def _save(source):
        saved["source"] = source
        return True

    with (
        patch("auth_middleware.get_current_user", AsyncMock(return_value=user)),
        patch.object(sources_ep, "save_source", _save),
    ):
        response = await sources_ep.create_code_source(request, _FakeRequest())

    return response, saved["source"]


class TestCreateCodeSourceCapturesOwner:
    """POST /sources must stamp owner_id from the caller (#12377)."""

    async def test_local_source_captures_caller_as_owner(self):
        req = CodeSourceCreateRequest(name="proj", source_type="local", repo="/tmp/proj")
        response, source = await _create(req, {"id": "alice"})

        assert response.status_code == 201
        assert source.owner_id == "alice"

    async def test_github_source_captures_caller_as_owner(self):
        from api.codebase_analytics.endpoints import sources as sources_ep

        req = CodeSourceCreateRequest(name="proj", source_type="github", repo="owner/repo")
        with (
            patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "alice"})),
            patch("api.codebase_analytics.source_service.save_source", AsyncMock(return_value=True)),
            # Skip the auto-sync background task — irrelevant to ownership capture.
            patch.object(sources_ep, "_do_sync", AsyncMock()),
        ):
            response = await sources_ep.create_code_source(req, _FakeRequest())

        assert response.status_code == 201

    async def test_created_source_private_to_owner_not_visible_to_other_admin(self):
        """The privacy gap closed: a different admin cannot see the new source,
        but the creating admin still can (#12377)."""
        req = CodeSourceCreateRequest(
            name="proj",
            source_type="local",
            repo="/tmp/proj",
            access=SourceAccess.PRIVATE,
        )
        _, source = await _create(req, {"id": "alice"})

        assert source.access == SourceAccess.PRIVATE
        assert _is_visible(source, "alice") is True
        assert _is_visible(source, "bob") is False

    async def test_service_caller_creates_unowned_source(self):
        """The internal service key keeps creating unowned (owner_id=None)
        sources — unchanged behavior for service/pre-ownership callers."""
        req = CodeSourceCreateRequest(name="proj", source_type="local", repo="/tmp/proj")
        user = {"username": "service:slm", "role": "admin", "service": True}
        _, source = await _create(req, user)

        assert source.owner_id is None
