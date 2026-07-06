# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Round-trip and unit tests for the OKF v0.1 adapter.

Issue #10617: Verifies that export_to_okf -> import_from_okf -> export_to_okf
produces an identical bundle (byte-for-byte at the file level), that every
exported file has the required ``type`` frontmatter field, and that cross-links
round-trip correctly.

All tests are fully self-contained — no live Redis, ChromaDB, or Ollama
connection required.  The adapter's standalone path (OKFAdapter(kb=None))
is used throughout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from knowledge.adapters.okf_adapter import (
    OKFAdapter,
    _parse_okf_file,
    _render_okf_file,
    _slugify,
    _unique_slug,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FACT_A = {
    "fact_id": "aaa-111",
    "content": "Alpha concept with a link to [[bbb-222]].",
    "metadata": {
        "title": "Alpha Concept",
        "category": "theory",
        "type": "concept",
        "tags": ["alpha", "theory"],
        "verification_status": "verified",
    },
    "timestamp": "2026-01-01T00:00:00+00:00",
}

FACT_B = {
    "fact_id": "bbb-222",
    "content": "Beta concept references [[aaa-111]] and self-links to [[bbb-222]].",
    "metadata": {
        "title": "Beta Concept",
        "category": "implementation",
        "source_type": "manual_upload",
        # no explicit 'type' — adapter defaults to 'concept' from source_type path
        "tags": ["beta"],
    },
    "timestamp": "2026-01-02T00:00:00+00:00",
}

FACT_MINIMAL = {
    "fact_id": "ccc-333",
    "content": "Minimal fact with no metadata.",
    "metadata": {},
    "timestamp": "",
}

ALL_FACTS: List[Dict[str, Any]] = [FACT_A, FACT_B, FACT_MINIMAL]


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_unicode_transliteration(self):
        slug = _slugify("Ālpha Bēta")
        assert slug == "lpha-b-ta" or all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug)

    def test_max_length(self):
        long_text = "a" * 200
        assert len(_slugify(long_text)) <= 80

    def test_empty_fallback(self):
        assert _slugify("") == "concept"
        assert _slugify("---") == "concept"

    def test_only_allowed_chars(self):
        slug = _slugify("Python 3.11: Async/Await & Patterns!")
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug)


class TestUniqueSlug:
    def test_no_conflict(self):
        taken: set = set()
        result = _unique_slug("alpha", taken)
        assert result == "alpha"

    def test_single_conflict(self):
        taken = {"alpha"}
        result = _unique_slug("alpha", taken)
        assert result == "alpha-2"

    def test_multiple_conflicts(self):
        taken = {"alpha", "alpha-2", "alpha-3"}
        result = _unique_slug("alpha", taken)
        assert result == "alpha-4"


# ---------------------------------------------------------------------------
# OKF file round-trip helpers
# ---------------------------------------------------------------------------


class TestRenderAndParse:
    def test_round_trip_frontmatter(self):
        fm = {"type": "concept", "id": "x-1", "title": "X One"}
        body = "Some content here."
        rendered = _render_okf_file(fm, body)
        parsed_fm, parsed_body = _parse_file_from_string(rendered)
        assert parsed_fm["type"] == "concept"
        assert parsed_body.strip() == body.strip()

    def test_required_type_field_present(self):
        fm = {"type": "guide", "id": "g-1"}
        body = "Guide body."
        rendered = _render_okf_file(fm, body)
        assert "type: guide" in rendered

    def test_missing_type_raises(self, tmp_path):
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("---\nid: x\n---\n\nBody.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required 'type'"):
            _parse_okf_file(bad_file)

    def test_no_fence_raises(self, tmp_path):
        bad_file = tmp_path / "bad2.md"
        bad_file.write_text("No frontmatter at all.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="does not start with"):
            _parse_okf_file(bad_file)


def _parse_file_from_string(content: str):
    """Parse an OKF file from a string (test helper)."""
    tmp = Path("/tmp/_okf_test_parse.md")
    tmp.write_text(content, encoding="utf-8")
    return _parse_okf_file(tmp)


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


class TestExportToOKF:
    @pytest.mark.asyncio
    async def test_creates_md_files(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        result = await adapter.export_to_okf(ALL_FACTS, str(tmp_path / "bundle"))
        assert result["status"] == "success"
        assert result["exported_count"] == 3
        md_files = list((tmp_path / "bundle").glob("*.md"))
        assert len(md_files) == 3

    @pytest.mark.asyncio
    async def test_type_field_in_all_files(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf(ALL_FACTS, str(bundle))
        for md_file in bundle.glob("*.md"):
            fm, _ = _parse_okf_file(md_file)
            assert "type" in fm, "type missing in %s" % md_file.name

    @pytest.mark.asyncio
    async def test_cross_links_rewritten(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A, FACT_B], str(bundle))
        alpha_file = bundle / "alpha-concept.md"
        assert alpha_file.exists()
        content = alpha_file.read_text(encoding="utf-8")
        # The [[bbb-222]] link should be rewritten to [beta-concept](beta-concept.md)
        assert "(beta-concept.md)" in content
        assert "[[bbb-222]]" not in content

    @pytest.mark.asyncio
    async def test_deterministic_output(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle1 = tmp_path / "b1"
        bundle2 = tmp_path / "b2"
        await adapter.export_to_okf(ALL_FACTS, str(bundle1))
        # Reverse fact order — output should still be identical
        await adapter.export_to_okf(list(reversed(ALL_FACTS)), str(bundle2))

        files1 = sorted(f.name for f in bundle1.glob("*.md"))
        files2 = sorted(f.name for f in bundle2.glob("*.md"))
        assert files1 == files2

        for fname in files1:
            c1 = (bundle1 / fname).read_text(encoding="utf-8")
            c2 = (bundle2 / fname).read_text(encoding="utf-8")
            assert c1 == c2, "Non-deterministic output for %s" % fname

    @pytest.mark.asyncio
    async def test_minimal_fact_gets_default_type(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_MINIMAL], str(bundle))
        md_files = list(bundle.glob("*.md"))
        assert len(md_files) == 1
        fm, _ = _parse_okf_file(md_files[0])
        assert fm["type"] == "concept"

    @pytest.mark.asyncio
    async def test_empty_facts_list(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        result = await adapter.export_to_okf([], str(tmp_path / "empty"))
        assert result["status"] == "success"
        assert result["exported_count"] == 0

    @pytest.mark.asyncio
    async def test_slug_title_based(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A], str(bundle))
        assert (bundle / "alpha-concept.md").exists()

    @pytest.mark.asyncio
    async def test_slug_fallback_to_fact_id(self, tmp_path):
        fact_no_title = {
            "fact_id": "xyz-9999",
            "content": "No title here.",
            "metadata": {"type": "note"},
            "timestamp": "",
        }
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([fact_no_title], str(bundle))
        # slug based on first 8 chars of fact_id "xyz-9999" -> "xyz-9999"
        assert (bundle / "xyz-9999.md").exists()

    @pytest.mark.asyncio
    async def test_tags_sorted_in_output(self, tmp_path):
        fact = {
            "fact_id": "t-001",
            "content": "Tagged.",
            "metadata": {"type": "note", "tags": ["zebra", "alpha", "mango"]},
            "timestamp": "",
        }
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([fact], str(bundle))
        md_files = list(bundle.glob("*.md"))
        fm, _ = _parse_okf_file(md_files[0])
        assert fm["tags"] == ["alpha", "mango", "zebra"]


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


class TestImportFromOKF:
    @pytest.mark.asyncio
    async def test_basic_import(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A, FACT_B], str(bundle))

        result = await adapter.import_from_okf(str(bundle))
        assert result["status"] == "success"
        assert result["imported_count"] == 2
        assert "facts" in result

    @pytest.mark.asyncio
    async def test_type_field_preserved(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A], str(bundle))
        result = await adapter.import_from_okf(str(bundle))
        fact = result["facts"][0]
        assert fact["metadata"]["type"] == "concept"

    @pytest.mark.asyncio
    async def test_cross_links_resolved(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A, FACT_B], str(bundle))
        result = await adapter.import_from_okf(str(bundle))
        facts_by_id = {f["fact_id"]: f for f in result["facts"]}
        # The alpha content should have [[bbb-222]] restored
        alpha = facts_by_id.get("aaa-111")
        assert alpha is not None
        assert "[[bbb-222]]" in alpha["content"]

    @pytest.mark.asyncio
    async def test_nonexistent_dir(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        result = await adapter.import_from_okf(str(tmp_path / "nonexistent"))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_bad_file_reported_in_errors(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        (bundle / "bad.md").write_text("No frontmatter\n", encoding="utf-8")
        result = await adapter.import_from_okf(str(bundle))
        # Should report error but not crash
        assert result.get("errors") or result["imported_count"] == 0


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_export_import_export_identical(self, tmp_path):
        """Core round-trip guarantee: export -> import -> export == first export."""
        adapter = OKFAdapter(kb=None)
        bundle1 = tmp_path / "b1"
        bundle2 = tmp_path / "b2"

        # First export
        export1 = await adapter.export_to_okf(ALL_FACTS, str(bundle1))
        assert export1["status"] == "success"

        # Import
        import_result = await adapter.import_from_okf(str(bundle1))
        assert import_result["status"] == "success"

        # Second export from imported facts
        export2 = await adapter.export_to_okf(import_result["facts"], str(bundle2))
        assert export2["status"] == "success"

        # Compare file sets
        files1 = sorted(f.name for f in bundle1.glob("*.md"))
        files2 = sorted(f.name for f in bundle2.glob("*.md"))
        assert files1 == files2, "File sets differ after round-trip"

        # Compare file contents
        for fname in files1:
            c1 = (bundle1 / fname).read_text(encoding="utf-8")
            c2 = (bundle2 / fname).read_text(encoding="utf-8")
            assert c1 == c2, "Content differs for %s after round-trip" % fname

    @pytest.mark.asyncio
    async def test_fact_id_preserved_through_round_trip(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A, FACT_B], str(bundle))
        result = await adapter.import_from_okf(str(bundle))
        imported_ids = {f["fact_id"] for f in result["facts"]}
        assert "aaa-111" in imported_ids
        assert "bbb-222" in imported_ids

    @pytest.mark.asyncio
    async def test_category_preserved_through_round_trip(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A], str(bundle))
        result = await adapter.import_from_okf(str(bundle))
        alpha = result["facts"][0]
        assert alpha["metadata"].get("category") == "theory"

    @pytest.mark.asyncio
    async def test_tags_preserved_through_round_trip(self, tmp_path):
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([FACT_A], str(bundle))
        result = await adapter.import_from_okf(str(bundle))
        alpha = result["facts"][0]
        tags = alpha["metadata"].get("tags", [])
        assert "alpha" in tags
        assert "theory" in tags

    @pytest.mark.asyncio
    async def test_content_body_preserved_through_round_trip(self, tmp_path):
        """Content (excluding link syntax transform) is preserved losslessly."""
        fact_plain = {
            "fact_id": "plain-001",
            "content": "This is plain content with no links.",
            "metadata": {"type": "note"},
            "timestamp": "",
        }
        adapter = OKFAdapter(kb=None)
        bundle = tmp_path / "bundle"
        await adapter.export_to_okf([fact_plain], str(bundle))
        result = await adapter.import_from_okf(str(bundle))
        assert result["facts"][0]["content"].strip() == fact_plain["content"].strip()

    @pytest.mark.asyncio
    async def test_slug_collision_resolution_stable(self, tmp_path):
        """Two facts with identical titles get distinct slugs, stable across runs."""
        fact1 = {
            "fact_id": "dup-001",
            "content": "First dup.",
            "metadata": {"type": "note", "title": "Duplicate Title"},
            "timestamp": "",
        }
        fact2 = {
            "fact_id": "dup-002",
            "content": "Second dup.",
            "metadata": {"type": "note", "title": "Duplicate Title"},
            "timestamp": "",
        }
        adapter = OKFAdapter(kb=None)
        bundle1 = tmp_path / "b1"
        bundle2 = tmp_path / "b2"
        await adapter.export_to_okf([fact1, fact2], str(bundle1))
        await adapter.export_to_okf([fact1, fact2], str(bundle2))

        files1 = sorted(f.name for f in bundle1.glob("*.md"))
        files2 = sorted(f.name for f in bundle2.glob("*.md"))
        assert files1 == files2
        assert len(files1) == 2
        assert files1[0] != files1[1]
