# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tier, category and dry-run scoping on ``DocIndexerService`` (#18129).

These options were promoted from the two retired standalone indexers so the one
service can serve every documented operator command.
"""

import hashlib
from pathlib import Path

from services.knowledge.doc_taxonomy import detect_category

from .test_doc_indexer import _make_service


def _tree(root: Path) -> None:
    for rel in ("CLAUDE.md", "docs/api/a.md", "docs/features/f.md", "docs/security/s.md"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# T\n\nbody\n", encoding="utf-8")


def test_plan_narrows_by_tier(tmp_path):
    _tree(tmp_path)
    svc = _make_service(root_dir=tmp_path)
    assert {t for _, t in svc.plan(force=True)} == {1, 2, 3}
    assert {Path(p).name for p, _ in svc.plan(force=True, tier=2)} == {"f.md"}


def test_plan_narrows_by_category(tmp_path):
    _tree(tmp_path)
    svc = _make_service(root_dir=tmp_path)
    assert [Path(p).name for p, _ in svc.plan(force=True, category="security")] == ["s.md"]


def test_plan_without_force_honours_the_hash_cache(tmp_path, monkeypatch):
    _tree(tmp_path)
    svc = _make_service(root_dir=tmp_path)
    monkeypatch.setattr("services.knowledge.doc_indexer._load_hash_cache", lambda: {})
    assert len(svc.plan()) == 3
    cached = {"docs/security/s.md": hashlib.sha256(b"# T\n\nbody\n").hexdigest()}
    monkeypatch.setattr("services.knowledge.doc_indexer._load_hash_cache", lambda: cached)
    assert "s.md" not in {Path(p).name for p, _ in svc.plan()}


def test_resolve_tier_defaults_to_three_outside_discovery(tmp_path):
    _tree(tmp_path)
    svc = _make_service(root_dir=tmp_path)
    assert svc.resolve_tier(tmp_path / "CLAUDE.md") == 1
    assert svc.resolve_tier(tmp_path / "elsewhere.md") == 3


def test_taxonomy_detects_the_directory_before_the_filename():
    assert detect_category(Path("docs/api/x.md")) == "api"
    assert detect_category(Path("docs/misc/DOCKER_NOTES.md")) == "deployment"
    assert detect_category(Path("nothing.md")) == "general"


def test_the_indexer_chunks_with_the_shared_primitives_the_kb_chunker_is_built_on():
    """The indexer owns no packing logic: its fallback is the very function ``chunk_plain_text`` reuses."""
    from autobot_shared import doc_chunking
    from services.knowledge import doc_indexer

    assert doc_indexer._chunk_large_content is doc_chunking.chunk_large_content
    assert doc_indexer._process_h2_sections is doc_chunking.process_h2_sections
    # A header-less document is all intro: it is cut by chunk_plain_text, not kept as one chunk
    # (before, it stayed one over-budget chunk and relied on the embedder rejecting it).
    body = "\n\n".join(f"paragraph {i} " + "word " * 300 for i in range(6))
    markdown_chunks = doc_indexer._chunk_markdown(body, "docs/x.md")
    plain_chunks = doc_chunking.chunk_plain_text(body)
    assert len(markdown_chunks) == len(plain_chunks) > 1
