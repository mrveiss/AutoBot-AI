# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for auto-index-on-registration for local sources (Issue #12364).

GitHub sources already auto-index on creation (create_github_source ->
auto_sync=True -> _do_sync -> _trigger_indexing). Local sources had no
equivalent: registering one left the indexed-store panels blank ("Run
indexing first") until someone manually called POST /sources/{id}/sync.
These tests assert local-source creation now triggers indexing itself
whenever the given path actually exists.
"""

from unittest.mock import AsyncMock, patch

from api.codebase_analytics.endpoints import sources as sources_ep
from api.codebase_analytics.source_models import CodeSource, SourceStatus


class TestAutoIndexLocalSource:
    async def test_valid_local_path_triggers_indexing(self, tmp_path):
        clone_dir = tmp_path / "local_repo"
        clone_dir.mkdir()
        source = CodeSource(name="local-proj", source_type="local", clone_path=str(clone_dir))

        with (
            patch.object(sources_ep, "save_source", AsyncMock()) as save_mock,
            patch.object(sources_ep, "_trigger_indexing", AsyncMock()) as trigger_mock,
        ):
            await sources_ep._auto_index_local_source(source)

        trigger_mock.assert_awaited_once_with(source)
        assert source.status == SourceStatus.READY
        assert source.last_synced is not None
        save_mock.assert_awaited_once()

    async def test_nonexistent_path_is_a_noop(self, tmp_path):
        source = CodeSource(
            name="local-proj", source_type="local", clone_path=str(tmp_path / "does-not-exist")
        )

        with (
            patch.object(sources_ep, "save_source", AsyncMock()) as save_mock,
            patch.object(sources_ep, "_trigger_indexing", AsyncMock()) as trigger_mock,
        ):
            await sources_ep._auto_index_local_source(source)

        trigger_mock.assert_not_called()
        save_mock.assert_not_called()

    async def test_github_source_is_a_noop(self, tmp_path):
        clone_dir = tmp_path / "gh_repo"
        clone_dir.mkdir()
        source = CodeSource(
            name="gh-proj", source_type="github", repo="org/repo", clone_path=str(clone_dir)
        )

        with (
            patch.object(sources_ep, "save_source", AsyncMock()) as save_mock,
            patch.object(sources_ep, "_trigger_indexing", AsyncMock()) as trigger_mock,
        ):
            await sources_ep._auto_index_local_source(source)

        trigger_mock.assert_not_called()
        save_mock.assert_not_called()

    async def test_missing_clone_path_is_a_noop(self):
        source = CodeSource(name="local-proj", source_type="local", clone_path=None)

        with (
            patch.object(sources_ep, "save_source", AsyncMock()) as save_mock,
            patch.object(sources_ep, "_trigger_indexing", AsyncMock()) as trigger_mock,
        ):
            await sources_ep._auto_index_local_source(source)

        trigger_mock.assert_not_called()
        save_mock.assert_not_called()

    async def test_create_code_source_wires_auto_index_for_local(self, tmp_path):
        """End-to-end through create_code_source: registering a local source
        with a real, existing path triggers indexing without a separate
        manual sync call."""
        from api.codebase_analytics.source_models import CodeSourceCreateRequest

        clone_dir = tmp_path / "repo"
        clone_dir.mkdir()
        request = CodeSourceCreateRequest(name="proj", source_type="local", repo=str(clone_dir))

        with (
            patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "alice"})),
            patch.object(sources_ep, "save_source", AsyncMock()),
            patch.object(sources_ep, "_trigger_indexing", AsyncMock()) as trigger_mock,
        ):
            response = await sources_ep.create_code_source(request, http_request=object())

        assert response.status_code == 201
        trigger_mock.assert_awaited_once()
