# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#14751 and #14754: bound the OCR knobs, and stop blocking the event loop.

Both are the document ingest path taking arbitrary uploads, so they travel
together. The knobs had a floor and no ceiling, so a sane-looking config change
removed the protection it configures; the rasterizer had no pixel budget, so a
declared page size could allocate gigabytes before any timeout applied; and the
extraction that feeds all of it ran synchronously inside async handlers.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from media.document import ocr as ocr_mod


class TestTheKnobsHaveACeilingAndNotJustAFloor:
    """#14751.1: `value <= 0` was the only rejection, so upward was unbounded."""

    @pytest.mark.parametrize(
        "asked,ceiling,expected",
        [
            pytest.param(10_000, 600, 600, id="dpi-clamped"),
            pytest.param(600, 600, 600, id="dpi-at-ceiling"),
            pytest.param(150, 600, 150, id="dpi-below-ceiling"),
        ],
    )
    def test_a_value_above_the_ceiling_is_clamped_not_rejected(self, asked, ceiling, expected):
        """Clamped rather than dropped to the default.

        An operator who asked for more than the ceiling wants as much as they
        can have; falling back to the default would quietly give them *less*
        than they asked for.
        """
        assert ocr_mod._positive_int_setting(str(asked), 300, "X", ceiling) == expected

    def test_every_knob_carries_a_ceiling(self):
        """A knob added later without one reopens the hole this closes."""
        import inspect

        src = inspect.getsource(ocr_mod)
        for resolver in ("ocr_dpi", "ocr_page_timeout", "max_ocr_pages", "ocr_timeout"):
            body = src.split(f"def {resolver}(")[1].split("\ndef ")[0]
            assert "MAX_" in body, f"{resolver} resolves without a ceiling (#14751)"

    def test_a_non_integer_or_negative_still_falls_back(self):
        """The ceiling must not have displaced the existing floor behaviour."""
        assert ocr_mod._positive_int_setting("abc", 300, "X", 600) == 300
        assert ocr_mod._positive_int_setting("-5", 300, "X", 600) == 300
        assert ocr_mod._positive_int_setting(None, 300, "X", 600) == 300


class TestTheRasterizerHasAPixelBudget:
    """#14751.1b: the page ceiling bounds count, the timeout bounds duration.

    Neither bounds SIZE — a declared MediaBox could allocate gigabytes before
    any timeout applied, and an OS-level OOM kill lands before Python raises.
    """

    def test_an_ordinary_page_keeps_the_requested_scale(self):
        page = SimpleNamespace(get_size=lambda: (612, 792))  # US Letter, points
        assert ocr_mod._bounded_scale(page, 300, 1) == pytest.approx(300 / 72)

    def test_an_enormous_page_is_downscaled_to_fit(self):
        page = SimpleNamespace(get_size=lambda: (20_000, 20_000))
        scale = ocr_mod._bounded_scale(page, 300, 1)
        assert scale < 300 / 72, "an oversized page must not keep the full scale"
        assert (20_000 * scale) * (20_000 * scale) <= ocr_mod.MAX_OCR_PAGE_PIXELS + 1

    def test_downscaling_is_preferred_to_skipping(self):
        """A large page is still read, just at a lower effective DPI."""
        page = SimpleNamespace(get_size=lambda: (20_000, 20_000))
        assert ocr_mod._bounded_scale(page, 300, 1) > 0

    def test_an_unmeasurable_page_keeps_the_requested_scale(self):
        """Behaviour that predates the bound, for a page that will not report size."""

        def boom():
            raise RuntimeError("no size")

        page = SimpleNamespace(get_size=boom)
        assert ocr_mod._bounded_scale(page, 300, 1) == pytest.approx(300 / 72)


class TestTesseractCmdActuallyApplies:
    """#14751.3: the report displayed it and nothing ever assigned it."""

    def test_a_configured_path_is_assigned(self, monkeypatch):
        monkeypatch.setenv("TESSERACT_CMD", "/opt/custom/tesseract")
        fake = SimpleNamespace(pytesseract=SimpleNamespace(tesseract_cmd="original"))
        ocr_mod._apply_tesseract_cmd(fake)
        assert (
            fake.pytesseract.tesseract_cmd == "/opt/custom/tesseract"
        ), "setting TESSERACT_CMD must change which binary runs, not just what is reported"

    def test_an_unset_path_leaves_the_default_alone(self, monkeypatch):
        monkeypatch.delenv("TESSERACT_CMD", raising=False)
        fake = SimpleNamespace(pytesseract=SimpleNamespace(tesseract_cmd="original"))
        ocr_mod._apply_tesseract_cmd(fake)
        assert fake.pytesseract.tesseract_cmd == "original"

    def test_the_report_shows_the_value_that_is_applied(self, monkeypatch):
        monkeypatch.setenv("TESSERACT_CMD", "/opt/custom/tesseract")
        assert ocr_mod.tesseract_cmd() == "/opt/custom/tesseract"


class TestExtractionDoesNotHoldTheEventLoop:
    """#14754: blocking CPU work called synchronously from async handlers."""

    @pytest.mark.asyncio
    async def test_the_pipeline_offloads_extraction(self):
        from media.core.types import MediaInput, MediaType, ProcessingIntent
        from media.document.extraction import ExtractedDocument
        from media.document.pipeline import DocumentPipeline

        extracted = ExtractedDocument(format="pdf", text="hello", tables=(), info={})
        seen: list = []

        real_to_thread = asyncio.to_thread

        async def recording(fn, *args, **kwargs):
            seen.append(getattr(fn, "__name__", type(fn).__name__))
            return await real_to_thread(fn, *args, **kwargs)

        with (
            patch("media.document.pipeline.extract_document", return_value=extracted),
            patch("media.document.pipeline.asyncio.to_thread", recording),
        ):
            await DocumentPipeline()._process_impl(
                MediaInput(
                    media_id="test-doc",
                    media_type=MediaType.DOCUMENT,
                    intent=ProcessingIntent.EXTRACTION,
                    data=b"%PDF-1.4 x",
                    mime_type="application/pdf",
                    metadata={},
                )
            )

        assert seen, (
            "extraction ran inline — one large document holds the worker's event "
            "loop for the whole parse, stalling every other coroutine on it"
        )
