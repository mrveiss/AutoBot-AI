# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import pytest

from api.codebase_analytics import source_service
from api.codebase_analytics.source_models import SourceType


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
