# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The catalog lookup reads code_source's infrastructure tree, not the stale copy beside the install (#20578)."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

from autobot_shared import paths
from utils import error_catalog
from utils.error_catalog import CATALOG_FILENAME, ErrorCatalog


def _two_copies(tmp_path):
    install = tmp_path / "opt-autobot"
    for root in (install, install / "code_source"):
        (root / paths.INFRASTRUCTURE_DIR_NAME / "shared" / "config").mkdir(parents=True)
    return install, install / "code_source"


def test_candidates_name_code_source_and_never_the_stale_copy(tmp_path, monkeypatch) -> None:
    install, code_source = _two_copies(tmp_path)
    monkeypatch.setenv(paths.CODE_SOURCE_ENV, str(code_source))
    monkeypatch.setenv(paths.BASE_DIR_ENV, str(install))
    monkeypatch.setattr(error_catalog, "PATH", SimpleNamespace(STATIC_DIR=tmp_path / "x", CONFIG_DIR=tmp_path / "y"))
    candidates = ErrorCatalog()._candidate_paths()
    current = code_source / paths.INFRASTRUCTURE_DIR_NAME / "shared" / "config" / CATALOG_FILENAME
    stale = install / paths.INFRASTRUCTURE_DIR_NAME / "shared" / "config" / CATALOG_FILENAME
    assert current in candidates
    assert stale not in candidates


def test_man_page_indexer_is_under_code_source(tmp_path, monkeypatch) -> None:
    from tasks import man_page_indexing

    install, code_source = _two_copies(tmp_path)
    monkeypatch.setenv(paths.CODE_SOURCE_ENV, str(code_source))
    monkeypatch.setenv(paths.BASE_DIR_ENV, str(install))
    try:
        reloaded = importlib.reload(man_page_indexing)
        assert code_source in reloaded.MAN_PAGE_INDEXER.parents
        assert reloaded.MAN_PAGE_INDEXER.name == "index_all_man_pages.py"
    finally:
        monkeypatch.undo()
        importlib.reload(man_page_indexing)
