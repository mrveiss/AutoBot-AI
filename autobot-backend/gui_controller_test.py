# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test suite for GUIController canonical-display convergence (#11579).

Verifies GUIController attaches to the SAME shared canonical desktop display
(NetworkConstants.DESKTOP_DISPLAY) that api.vnc_manager owns, instead of
starting a private, competing Xvfb on :99 — and that read_text_from_region
(OCR), the one capability with no xdotool/vnc_manager equivalent, keeps
working after the retirement of :99.

pyautogui is an optional GUI-automation dependency not installed in CI (no
X display in the test environment), so it is stubbed via sys.modules before
importing gui_controller, mirroring the pattern used in
tests/test_vnc_mcp_async.py for scrot/xdotool.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _make_pyautogui_stub() -> types.ModuleType:
    """Build a minimal pyautogui stand-in exposing the API gui_controller uses."""
    mod = types.ModuleType("pyautogui")
    mod.FAILSAFE = False
    mod.PAUSE = 0
    mod.size = MagicMock(return_value=(1920, 1080))
    mod.screenshot = MagicMock(return_value="FAKE_IMAGE")
    mod.click = MagicMock()
    mod.write = MagicMock()
    mod.moveTo = MagicMock()
    mod.position = MagicMock(return_value=(0, 0))
    mod.locateCenterOnScreen = MagicMock(return_value=None)
    return mod


@pytest.fixture
def gui_controller_module(monkeypatch):
    """Import gui_controller with a stubbed pyautogui (unavailable in CI)."""
    monkeypatch.setitem(sys.modules, "pyautogui", _make_pyautogui_stub())
    sys.modules.pop("gui_controller", None)
    import gui_controller as mod

    yield mod
    sys.modules.pop("gui_controller", None)


@pytest.fixture
def display_inactive():
    """Patch subprocess.run so the canonical display probe reports 'not running'."""
    with patch("gui_controller.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        yield mock_run


@pytest.fixture
def display_active():
    """Patch subprocess.run so the canonical display probe reports 'running'."""
    with patch("gui_controller.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        yield mock_run


class TestCanonicalDisplayConvergence:
    """GUIController must target the single shared display, never :99."""

    def test_canonical_display_matches_shared_network_constant(self, gui_controller_module):
        from autobot_shared.network_constants import NetworkConstants

        assert gui_controller_module.CANONICAL_DISPLAY == NetworkConstants.DESKTOP_DISPLAY

    def test_canonical_display_is_not_99(self, gui_controller_module):
        assert gui_controller_module.CANONICAL_DISPLAY != ":99"

    def test_init_sets_display_env_to_canonical(self, gui_controller_module, monkeypatch, display_inactive):
        monkeypatch.delenv("DISPLAY", raising=False)
        gui_controller_module.GUIController()
        assert os.environ["DISPLAY"] == gui_controller_module.CANONICAL_DISPLAY

    def test_init_overrides_stale_display_env(self, gui_controller_module, monkeypatch, display_active):
        monkeypatch.setenv("DISPLAY", ":0")
        gui_controller_module.GUIController()
        assert os.environ["DISPLAY"] == gui_controller_module.CANONICAL_DISPLAY
        assert os.environ["DISPLAY"] != ":0"

    def test_init_never_spawns_a_private_xvfb(self, gui_controller_module, display_active):
        with patch("gui_controller.subprocess.Popen") as mock_popen:
            controller = gui_controller_module.GUIController()

        mock_popen.assert_not_called()
        assert controller.xvfb_process is None

    def test_start_virtual_display_alias_also_attaches_canonical(self, gui_controller_module, display_active):
        with patch("gui_controller.subprocess.Popen") as mock_popen:
            controller = gui_controller_module.GUIController()
            controller.start_virtual_display()

        mock_popen.assert_not_called()
        assert os.environ["DISPLAY"] == gui_controller_module.CANONICAL_DISPLAY

    def test_probes_canonical_display_not_99(self, gui_controller_module, display_active):
        gui_controller_module.GUIController()

        probed_argvs = [call.args[0] for call in display_active.call_args_list]
        for argv in probed_argvs:
            joined = " ".join(argv)
            assert ":99" not in joined
            assert gui_controller_module.CANONICAL_DISPLAY in joined


class TestScreenSizeStartupRaceGuarded:
    """pyautogui.size() can hard-raise if the canonical display isn't up yet (startup race)."""

    def test_size_failure_does_not_crash_construction(self, gui_controller_module, display_inactive):
        gui_controller_module.pyautogui.size.side_effect = Exception("no X connection")
        try:
            controller = gui_controller_module.GUIController()
        finally:
            gui_controller_module.pyautogui.size.side_effect = None

        assert controller.screen_width is None
        assert controller.screen_height is None

    def test_size_success_still_sets_dimensions(self, gui_controller_module, display_active):
        gui_controller_module.pyautogui.size.return_value = (1920, 1080)
        controller = gui_controller_module.GUIController()

        assert controller.screen_width == 1920
        assert controller.screen_height == 1080


class TestReadTextFromRegionPreserved:
    """OCR region-read has no xdotool/vnc_manager equivalent — must keep working."""

    @pytest.mark.asyncio
    async def test_read_text_from_region_success(self, gui_controller_module, display_active):
        pytesseract_stub = types.ModuleType("pytesseract")
        pytesseract_stub.image_to_string = MagicMock(return_value="Hello AutoBot")

        controller = gui_controller_module.GUIController()

        with patch.dict(sys.modules, {"pytesseract": pytesseract_stub}):
            result = await controller.read_text_from_region(10, 20, 100, 50)

        assert result["status"] == "success"
        assert result["text"] == "Hello AutoBot"
        gui_controller_module.pyautogui.screenshot.assert_called_with(region=(10, 20, 100, 50))
        # Must run against the canonical (human-observed) display, not :99.
        assert os.environ["DISPLAY"] == gui_controller_module.CANONICAL_DISPLAY

    @pytest.mark.asyncio
    async def test_read_text_from_region_missing_pytesseract(self, gui_controller_module, display_active):
        controller = gui_controller_module.GUIController()

        with patch.dict(sys.modules, {"pytesseract": None}):
            result = await controller.read_text_from_region(0, 0, 10, 10)

        assert result["status"] == "error"
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_read_text_from_region_screenshot_failure_handled(self, gui_controller_module, display_active):
        pytesseract_stub = types.ModuleType("pytesseract")
        pytesseract_stub.image_to_string = MagicMock(return_value="unused")

        controller = gui_controller_module.GUIController()
        gui_controller_module.pyautogui.screenshot.side_effect = RuntimeError("no X connection")

        with patch.dict(sys.modules, {"pytesseract": pytesseract_stub}):
            result = await controller.read_text_from_region(0, 0, 10, 10)

        assert result["status"] == "error"
        assert result["text"] == ""

        gui_controller_module.pyautogui.screenshot.side_effect = None
