# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""_do_sync's re-clone path stops swallowing a failed rmtree (#17036).

The other #17036 site -- source_service.py's delete path -- is tested in
source_service_test.py; this covers the sync/re-clone site named in the
same issue, which had no coverage at all.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics.endpoints import sources as sources_ep
from api.codebase_analytics.source_models import CodeSource, SourceStatus

pytestmark = pytest.mark.asyncio


async def _run_do_sync(source, monkeypatch, *, rmtree_side_effect=None):
    monkeypatch.setattr(sources_ep, "save_source", AsyncMock())
    monkeypatch.setattr(sources_ep, "_resolve_token", AsyncMock(return_value=None))
    monkeypatch.setattr(sources_ep, "_build_clone_url", lambda repo, tok: "https://example.test/repo.git")
    clone_mock = AsyncMock(return_value="")
    monkeypatch.setattr(sources_ep, "_run_git_clone", clone_mock)
    with patch.object(sources_ep.shutil, "rmtree", side_effect=rmtree_side_effect) as rmtree_mock:
        await sources_ep._do_sync(source)
    return rmtree_mock, clone_mock


class TestReCloneStaleDirectoryRemovalFailure:
    async def test_a_failed_rmtree_is_reported_and_skips_the_clone_attempt(self, monkeypatch, tmp_path):
        clone_dir = tmp_path / "stale-clone"
        clone_dir.mkdir()  # exists, but no .git -- takes the re-clone branch
        source = CodeSource(name="x", source_type="github", repo="acme/site", clone_path=str(clone_dir), branch="main")

        rmtree_mock, clone_mock = await _run_do_sync(
            source, monkeypatch, rmtree_side_effect=OSError("permission denied")
        )

        rmtree_mock.assert_called_once()
        clone_mock.assert_not_awaited()
        assert source.status == SourceStatus.ERROR
        assert "permission denied" in source.error_message

    async def test_a_successful_clear_still_clones_as_before(self, monkeypatch, tmp_path):
        """No-failure control: the fix must not change the happy path."""
        clone_dir = tmp_path / "stale-clone"
        clone_dir.mkdir()
        source = CodeSource(name="x", source_type="github", repo="acme/site", clone_path=str(clone_dir), branch="main")

        rmtree_mock, clone_mock = await _run_do_sync(source, monkeypatch, rmtree_side_effect=None)

        rmtree_mock.assert_called_once()
        clone_mock.assert_awaited_once()
        assert source.status == SourceStatus.READY

    async def test_no_stale_directory_still_clones_as_before(self, monkeypatch, tmp_path):
        """No-failure control: a fresh clone target (nothing to remove) is unaffected."""
        clone_dir = tmp_path / "does-not-exist-yet"
        source = CodeSource(name="x", source_type="github", repo="acme/site", clone_path=str(clone_dir), branch="main")

        rmtree_mock, clone_mock = await _run_do_sync(source, monkeypatch, rmtree_side_effect=None)

        rmtree_mock.assert_not_called()
        clone_mock.assert_awaited_once()
        assert source.status == SourceStatus.READY
