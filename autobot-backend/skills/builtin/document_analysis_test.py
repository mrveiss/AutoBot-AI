# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DocumentAnalysisSkill guards (#13897).

Every handler used to return ``{"success": True, "status": "queued"}`` against no
queue, no worker and no consumer. The skill is **registered and reachable** —
``discover_builtin_skills()`` finds it by module scan, so it is routable with no
textual reference anywhere to grep for — which made the fabricated success worse
than dead code: a live surface reporting work it never did.

The invariant these tests exist to hold is therefore not "the handlers call the
extractor" but the stricter one: **no handler reports success for work that did
not happen.**
"""

import io

import pytest

from skills.builtin.document_analysis import DocumentAnalysisSkill


def _write_pdf(tmp_path, pages: list, name: str = "doc.pdf"):
    """Write a real PDF; ``None`` draws an image-only (scanned) page.

    Each text page is padded to comfortably clear ``DEFAULT_MIN_CHARS_PER_PAGE``
    (50). A page carrying three characters is, correctly, treated as a
    page-number stamp rather than content (#13884) — fixtures that ignore that
    would be testing against documents the extractor is designed to reject.
    """
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    from reportlab.pdfgen import canvas

    filler = " Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor."

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for entry in pages:
        if entry is None:
            from PIL import Image
            from reportlab.lib.utils import ImageReader

            pdf.drawImage(ImageReader(Image.new("RGB", (600, 800), "white")), 0, 0, width=400, height=500)
        else:
            pdf.drawString(72, 720, entry)
            pdf.drawString(72, 700, filler)
        pdf.showPage()
    pdf.save()

    path = tmp_path / name
    path.write_bytes(buffer.getvalue())
    return path


@pytest.fixture
def skill():
    return DocumentAnalysisSkill()


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["analyze_document", "extract_text", "summarize_document"])
async def test_no_handler_fabricates_a_queued_success(skill, tmp_path, action):
    """The exact regression: success:True with status:queued against no queue."""
    path = _write_pdf(tmp_path, ["real content"])
    result = await skill.execute(action, {"file_path": str(path)})

    assert result.get("status") != "queued", "no queue exists; claiming one is a fabricated success"
    if result.get("success"):
        assert "message" not in result or "queued" not in result["message"].lower()


@pytest.mark.asyncio
async def test_missing_file_reports_failure_not_success(skill, tmp_path):
    result = await skill.execute("extract_text", {"file_path": str(tmp_path / "absent.pdf")})
    assert result["success"] is False
    assert "Cannot read file" in result["error"]


@pytest.mark.asyncio
async def test_missing_file_path_is_rejected(skill):
    result = await skill.execute("analyze_document", {})
    assert result["success"] is False
    assert "file_path is required" in result["error"]


@pytest.mark.asyncio
async def test_unknown_action_is_rejected(skill):
    result = await skill.execute("not_a_tool", {"file_path": "/tmp/x.pdf"})
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Real extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_text_returns_the_document_body(skill, tmp_path):
    path = _write_pdf(tmp_path, ["alpha content", "beta content"])
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is True
    assert "alpha content" in result["content"]
    assert "beta content" in result["content"]
    assert result["pages_read"] == 2


@pytest.mark.asyncio
async def test_analyze_reports_real_structure(skill, tmp_path):
    path = _write_pdf(tmp_path, ["one", "two", "three"])
    result = await skill.execute("analyze_document", {"file_path": str(path)})

    assert result["success"] is True
    assert result["format"] == "pdf"
    assert result["page_count"] == 3
    assert result["char_count"] > 0


# ---------------------------------------------------------------------------
# Config that previously changed nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_pages_actually_truncates(skill, tmp_path):
    path = _write_pdf(tmp_path, ["page one", "page two", "page three"])
    skill.apply_config({"max_pages": 2})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["pages_read"] == 2
    assert result["truncated"] is True
    assert "page three" not in result["content"]


@pytest.mark.asyncio
async def test_max_pages_does_not_truncate_when_it_need_not(skill, tmp_path):
    path = _write_pdf(tmp_path, ["only page"])
    skill.apply_config({"max_pages": 100})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["truncated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_format,expect_markers",
    [("markdown", True), ("plain", False)],
)
async def test_output_format_changes_the_rendering(skill, tmp_path, output_format, expect_markers):
    path = _write_pdf(tmp_path, ["body text"])
    skill.apply_config({"output_format": output_format})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert ("## Page" in result["content"]) is expect_markers
    assert "body text" in result["content"]


@pytest.mark.asyncio
async def test_json_output_format_returns_structured_pages(skill, tmp_path):
    path = _write_pdf(tmp_path, ["first", "second"])
    skill.apply_config({"output_format": "json"})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    pages = result["content"]["pages"]
    assert [p["page"] for p in pages] == [1, 2]
    assert "first" in pages[0]["text"]


# ---------------------------------------------------------------------------
# Scanned documents and the OCR flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanned_document_fails_rather_than_returning_empty_success(skill, tmp_path):
    pytest.importorskip("PIL", reason="Pillow needed for image-only pages")
    path = _write_pdf(tmp_path, [None])
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is False
    assert "scanned" in result["error"].lower() or "OCR" in result["error"]
    assert result["empty_pages"] == [1]


@pytest.mark.asyncio
async def test_ocr_enabled_changes_the_reported_reason(skill, tmp_path):
    """The flag defaulted True while no OCR existed; now it must mean something."""
    pytest.importorskip("PIL", reason="Pillow needed for image-only pages")
    path = _write_pdf(tmp_path, [None])

    skill.apply_config({"ocr_enabled": False})
    without = await skill.execute("extract_text", {"file_path": str(path)})

    skill.apply_config({"ocr_enabled": True})
    with_ocr = await skill.execute("extract_text", {"file_path": str(path)})

    assert without["error"] != with_ocr["error"]
    assert "not available" in with_ocr["error"]


def test_ocr_enabled_no_longer_defaults_to_true():
    """Advertising OCR-on while no OCR backend exists is the false claim."""
    manifest = DocumentAnalysisSkill.get_manifest()
    assert manifest.config["ocr_enabled"].default is False


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_traversal_is_rejected_before_any_read(skill):
    result = await skill.execute("extract_text", {"file_path": "../../etc/passwd"})
    assert result["success"] is False
    assert "traversal" in result["error"]


@pytest.mark.asyncio
async def test_unsupported_extension_is_rejected(skill, tmp_path):
    path = tmp_path / "binary.exe"
    path.write_bytes(b"\x00\x01")
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is False
    assert "Unsupported format" in result["error"]


@pytest.mark.asyncio
async def test_plain_text_documents_are_supported(skill, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# heading\n\nbody", encoding="utf-8")
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is True
    assert "body" in result["content"]
    assert result["pages_read"] is None, "unpaginated formats have no page count"


# ---------------------------------------------------------------------------
# Summarization: honest failure, not a fabricated success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_reports_that_it_is_not_backed(skill, tmp_path):
    path = _write_pdf(tmp_path, ["document body"])
    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is False
    assert "not wired" in result["error"]
    # ...but the extraction it *did* do is handed back rather than discarded.
    assert "document body" in result["extracted_text"]


@pytest.mark.asyncio
async def test_summarize_does_not_pass_extracted_text_off_as_a_summary(skill, tmp_path):
    path = _write_pdf(tmp_path, ["document body"])
    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert "summary" not in result, "returning the raw text under a 'summary' key would be a lie"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_skill_is_discoverable_by_the_registry():
    """Registration is by module scan — there is no reference to grep for."""
    from skills.registry import SkillRegistry

    registry = SkillRegistry()
    registry.discover_builtin_skills()
    assert "document-analysis" in registry._skills
