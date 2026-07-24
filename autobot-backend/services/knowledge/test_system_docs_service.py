# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the System Docs filesystem service (Issue #12314)."""

from __future__ import annotations

from pathlib import Path

import pytest

import services.knowledge.system_docs_service as svc


@pytest.fixture()
def docs_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a small on-disk docs tree and point the service at it."""
    root = tmp_path / "docs"
    (root / "developer").mkdir(parents=True)
    (root / "api").mkdir()
    (root / "README.md").write_text("# Read Me\n\nTop-level doc.\n", encoding="utf-8")
    (root / "developer" / "setup.md").write_text("# Dev Setup\n\nSteps.\n", encoding="utf-8")
    (root / "developer" / "nested" / "deep.md").parent.mkdir()
    (root / "developer" / "nested" / "deep.md").write_text("no heading here\n", encoding="utf-8")
    (root / "api" / "routes.md").write_text("# Routes\n", encoding="utf-8")
    monkeypatch.setattr(svc, "_docs_root", lambda: root)
    return root


def test_list_categories_counts_and_general_bucket(docs_tree: Path) -> None:
    cats = {c["id"]: c for c in svc.list_categories()}
    assert cats["general"]["docCount"] == 1  # README.md
    assert cats["developer"]["docCount"] == 2  # setup.md + nested/deep.md
    assert cats["api"]["docCount"] == 1
    assert cats["developer"]["name"] == "Developer"
    assert cats["general"]["path"] == "general"


def test_list_category_docs_metadata_only(docs_tree: Path) -> None:
    docs = svc.list_category_docs("developer")
    assert len(docs) == 2
    for doc in docs:
        assert doc["content"] == ""  # list responses omit content
        assert doc["category"] == "developer"
        assert doc["type"] == "markdown"
    titles = {d["title"] for d in docs}
    assert "Dev Setup" in titles  # H1 extracted
    assert "Deep" in titles  # humanized stem fallback (no H1)


def test_general_category_lists_loose_docs(docs_tree: Path) -> None:
    docs = svc.list_category_docs("general")
    assert [d["path"] for d in docs] == ["README.md"]


def test_get_doc_returns_full_content(docs_tree: Path) -> None:
    doc_id = svc.list_category_docs("api")[0]["id"]
    full = svc.get_doc(doc_id)
    assert full is not None
    assert full["path"] == "api/routes.md"
    assert full["content"] == "# Routes\n"
    assert full["title"] == "Routes"


def test_get_doc_unknown_id_returns_none(docs_tree: Path) -> None:
    assert svc.get_doc("deadbeef") is None


def test_unknown_category_is_empty(docs_tree: Path) -> None:
    assert svc.list_category_docs("does-not-exist") == []


def test_traversal_category_rejected(docs_tree: Path) -> None:
    assert svc.list_category_docs("../../etc") == []


def test_missing_root_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_docs_root", lambda: tmp_path / "nope")
    assert svc.list_categories() == []
    assert svc.list_category_docs("general") == []
    assert svc.get_doc("anything") is None
