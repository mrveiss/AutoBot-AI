# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the VNC OCR path (#13208 review item H).

``vnc_ocr_text`` called ``Image.open(tmp_path, encoding="utf-8")``. PIL's
``Image.open`` accepts no ``encoding`` kwarg, so every call raised TypeError and
the endpoint returned its generic error branch — 100% dead, and silently so,
because the exception handler reported "Operation failed" either way.

These tests drive the real helper with a real 1x1 PNG so the decode has to
actually succeed; only ``pytesseract`` is stubbed.
"""

import base64
import io
from unittest.mock import MagicMock, patch

import pytest

from api.vnc_manager import _crop_to_region, _ocr_png_file
from autobot_shared.temp_files import temporary_file_path

Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")


def _png_bytes(width: int = 4, height: int = 4) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


class TestOcrDecodesTheImage:
    def test_real_png_is_decoded_and_passed_to_tesseract(self):
        """The bug: this raised TypeError before Image.open lost its kwarg."""
        fake_tesseract = MagicMock()
        fake_tesseract.image_to_string.return_value = "hello world"

        with patch.dict("sys.modules", {"pytesseract": fake_tesseract}):
            with temporary_file_path(suffix=".png") as tmp_path:
                text = _ocr_png_file(tmp_path, _png_bytes(), None)

        assert text == "hello world"
        assert fake_tesseract.image_to_string.called
        image_arg = fake_tesseract.image_to_string.call_args.args[0]
        assert image_arg.size == (4, 4)

    def test_image_open_is_called_with_one_positional_arg_and_no_encoding(self):
        """Pins the exact defect: no stray kwarg may come back."""
        fake_tesseract = MagicMock()
        fake_tesseract.image_to_string.return_value = ""

        with patch.dict("sys.modules", {"pytesseract": fake_tesseract}):
            with patch("PIL.Image.open", wraps=Image.open) as opener:
                with temporary_file_path(suffix=".png") as tmp_path:
                    _ocr_png_file(tmp_path, _png_bytes(), None)

        assert opener.call_count == 1
        assert len(opener.call_args.args) == 1
        assert "encoding" not in opener.call_args.kwargs

    def test_base64_round_trip_matches_the_endpoint_flow(self):
        """vnc_ocr_text decodes base64 from the screenshot before calling us."""
        fake_tesseract = MagicMock()
        fake_tesseract.image_to_string.return_value = "decoded"
        encoded = base64.b64encode(_png_bytes(8, 8)).decode("utf-8")

        with patch.dict("sys.modules", {"pytesseract": fake_tesseract}):
            with temporary_file_path(suffix=".png") as tmp_path:
                text = _ocr_png_file(tmp_path, base64.b64decode(encoded), None)

        assert text == "decoded"
        assert fake_tesseract.image_to_string.call_args.args[0].size == (8, 8)


class TestRegionCropping:
    def test_complete_region_crops(self):
        image = Image.new("RGB", (10, 10))

        cropped = _crop_to_region(image, {"x": 1, "y": 2, "width": 4, "height": 3})

        assert cropped.size == (4, 3)

    @pytest.mark.parametrize("region", [None, {}, {"x": 1, "y": 2}, {"x": 1, "y": 2, "width": 4}])
    def test_absent_or_partial_region_is_ignored(self, region):
        image = Image.new("RGB", (10, 10))

        assert _crop_to_region(image, region).size == (10, 10)

    def test_cropping_happens_before_ocr(self):
        fake_tesseract = MagicMock()
        fake_tesseract.image_to_string.return_value = ""

        with patch.dict("sys.modules", {"pytesseract": fake_tesseract}):
            with temporary_file_path(suffix=".png") as tmp_path:
                _ocr_png_file(tmp_path, _png_bytes(10, 10), {"x": 0, "y": 0, "width": 5, "height": 5})

        assert fake_tesseract.image_to_string.call_args.args[0].size == (5, 5)


class TestTempFileStillCleanedUp:
    def test_ocr_helper_leaves_no_file_behind(self, tmp_path, monkeypatch):
        import tempfile

        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        fake_tesseract = MagicMock()
        fake_tesseract.image_to_string.side_effect = RuntimeError("tesseract died")

        with patch.dict("sys.modules", {"pytesseract": fake_tesseract}):
            with pytest.raises(RuntimeError):
                with temporary_file_path(suffix=".png") as tmp_file:
                    _ocr_png_file(tmp_file, _png_bytes(), None)

        assert list(tmp_path.iterdir()) == []


class TestScreenshotDoesNotBlockTheEventLoop:
    """Review item G: two 10s subprocess timeouts ran inline on the loop."""

    @pytest.mark.asyncio
    async def test_capture_dispatches_subprocess_via_to_thread(self):
        import subprocess
        from unittest.mock import AsyncMock

        from api import vnc_manager

        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fail) as to_thread:
            captured = await vnc_manager._capture_screenshot_to("/tmp/does-not-matter.png")

        assert captured is False
        assert to_thread.call_count == 2, "scrot and the import fallback must both be dispatched"
        assert all(call.args[0] is subprocess.run for call in to_thread.call_args_list)
        assert to_thread.call_args_list[0].args[1][0] == "scrot"
        assert to_thread.call_args_list[1].args[1][0] == "import"

    @pytest.mark.asyncio
    async def test_capture_stops_after_the_first_success(self):
        import subprocess
        from unittest.mock import AsyncMock

        from api import vnc_manager

        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=ok) as to_thread:
            captured = await vnc_manager._capture_screenshot_to("/tmp/does-not-matter.png")

        assert captured is True
        assert to_thread.call_count == 1

    def test_capture_helpers_are_coroutines(self):
        import inspect

        from api import vnc_manager

        assert inspect.iscoroutinefunction(vnc_manager._capture_screenshot_to)
        assert inspect.iscoroutinefunction(vnc_manager._run_screenshot_capture)
