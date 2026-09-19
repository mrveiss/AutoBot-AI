# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import shutil

import pytest

from api.codebase_analytics import source_paths, source_service, source_storage
from api.codebase_analytics.source_models import CodeSource, SourceStatus, SourceType


@pytest.mark.asyncio
async def test_create_github_source_builds_and_saves(monkeypatch):
    saved = {}

    async def fake_save(src):
        saved["src"] = src
        return True

    monkeypatch.setattr(source_service, "save_source", fake_save)
    src = await source_service.create_github_source(
        name="acme/site", repo="acme/site", credential_id="cred1", branch="main", auto_sync=False
    )
    assert src.source_type == SourceType.GITHUB
    assert src.repo == "acme/site"
    assert src.credential_id == "cred1"
    assert saved["src"].id == src.id


class TestDeleteSourceAndCleanupReportsAFailedRemoval:
    """#17036: a failed clone removal must be reported, never swallowed."""

    @pytest.mark.asyncio
    async def test_a_failed_rmtree_keeps_the_record_marked_cleanup_failed(self, monkeypatch, tmp_path):
        clone_dir = tmp_path / "clone-1"
        clone_dir.mkdir()
        source = CodeSource(name="x", clone_path=str(clone_dir))

        monkeypatch.setattr(source_paths, "CODE_SOURCES_BASE", tmp_path)

        def _boom(path):
            raise OSError("permission denied")

        monkeypatch.setattr(shutil, "rmtree", _boom)

        saved = {}

        async def fake_save(src):
            saved["src"] = src
            return True

        monkeypatch.setattr(source_service, "save_source", fake_save)

        delete_called = {"value": False}

        async def fake_delete_source(_source_id):
            delete_called["value"] = True
            return True

        monkeypatch.setattr(source_storage, "delete_source", fake_delete_source)
        monkeypatch.setattr(source_storage, "get_source", lambda _sid: None)

        result = await source_service.delete_source_and_cleanup("src-1", source=source)

        assert result is False
        assert delete_called["value"] is False, "the record must not be dropped while the directory survives"
        assert saved["src"].status == SourceStatus.CLEANUP_FAILED
        # Fixed, non-exception-derived message (#17133 CodeQL information-
        # exposure review) -- error_message is stored on the record and
        # echoed by both the DELETE response and a later GET.
        assert saved["src"].error_message == "Clone directory removal failed; see server logs for the reason."
        assert clone_dir.exists(), "a failed rmtree must not be treated as if the directory were gone"

    @pytest.mark.asyncio
    async def test_a_successful_removal_still_deletes_the_record(self, monkeypatch, tmp_path):
        clone_dir = tmp_path / "clone-2"
        clone_dir.mkdir()
        source = CodeSource(name="y", clone_path=str(clone_dir))

        monkeypatch.setattr(source_paths, "CODE_SOURCES_BASE", tmp_path)

        async def fake_delete_source(_source_id):
            return True

        monkeypatch.setattr(source_storage, "delete_source", fake_delete_source)

        result = await source_service.delete_source_and_cleanup("src-2", source=source)

        assert result is True
        assert not clone_dir.exists()
