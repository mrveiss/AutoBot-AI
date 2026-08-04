# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the screenshot temp-file leak (#13208).

``desktop_screenshot_mcp`` created its PNG with ``delete=False`` and unlinked it
only on the success path, so every failed capture left a file in the system temp
directory forever. In production that is one orphan PNG per failure; in CI the
rc=1 tests in ``test_vnc_mcp_async.py`` hit it twice per run.

Strategy: redirect ``tempfile.tempdir`` at an empty pytest ``tmp_path`` and
assert the directory is empty *after* a capture that fails. Counting files
rather than mocking the unlink is what makes the assertion real — a leak shows
up as a leftover file no matter which code path dropped it.

The harness from ``test_vnc_mcp_async.py`` is reused so vnc_mcp.py can be loaded
without its full dependency tree.
"""

from __future__ import annotations

import subprocess
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_vnc_mcp_async import vnc_mcp_module  # noqa: F401  (pytest fixture)


@pytest.fixture
def isolated_tempdir(tmp_path, monkeypatch):
    """Point tempfile at an empty directory so leaks are countable."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def _files_in(directory) -> list:
    return sorted(p.name for p in directory.iterdir())


class TestScreenshotTempFileCleanup:
    """Every exit path of desktop_screenshot_mcp must remove its temp file."""

    @pytest.mark.asyncio
    async def test_no_leak_when_both_capture_commands_fail(self, vnc_mcp_module, isolated_tempdir):  # noqa: F811
        """rc=1 from scrot AND import must still remove the temp PNG (#13208)."""
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=fail):
            response = await vnc_mcp_module.desktop_screenshot_mcp()

        assert response["success"] is False
        assert _files_in(isolated_tempdir) == [], "failed capture leaked a temp file: " f"{_files_in(isolated_tempdir)}"

    @pytest.mark.asyncio
    async def test_no_leak_when_capture_raises(self, vnc_mcp_module, isolated_tempdir):  # noqa: F811
        """An exception mid-capture must still remove the temp PNG (#13208)."""
        with patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=OSError("boom")):
            response = await vnc_mcp_module.desktop_screenshot_mcp()

        assert response["success"] is False
        assert _files_in(isolated_tempdir) == [], (
            "raising capture leaked a temp file: " f"{_files_in(isolated_tempdir)}"
        )

    @pytest.mark.asyncio
    async def test_no_leak_when_reading_the_png_fails(self, vnc_mcp_module, isolated_tempdir):  # noqa: F811
        """Capture succeeds but the read raises — the temp PNG must still go (#13208)."""
        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with (
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=ok),
            patch("builtins.open", side_effect=OSError("unreadable")),
        ):
            response = await vnc_mcp_module.desktop_screenshot_mcp()

        assert response["success"] is False
        assert _files_in(isolated_tempdir) == [], (
            "unreadable capture leaked a temp file: " f"{_files_in(isolated_tempdir)}"
        )

    @pytest.mark.asyncio
    async def test_no_leak_on_the_success_path(self, vnc_mcp_module, isolated_tempdir):  # noqa: F811
        """The already-working success path keeps working (#13208 guard)."""
        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=ok):
            response = await vnc_mcp_module.desktop_screenshot_mcp()

        assert response["success"] is True
        assert _files_in(isolated_tempdir) == []


class TestTemporaryFilePathHelper:
    """The shared helper that carries the guarantee."""

    def test_path_exists_inside_block_and_is_gone_after(self, isolated_tempdir):
        from autobot_shared.temp_files import temporary_file_path

        with temporary_file_path(suffix=".png") as path:
            assert path.endswith(".png")
            assert _files_in(isolated_tempdir) != []

        assert _files_in(isolated_tempdir) == []

    def test_removed_when_the_block_raises(self, isolated_tempdir):
        from autobot_shared.temp_files import temporary_file_path

        with pytest.raises(RuntimeError):
            with temporary_file_path(suffix=".png"):
                raise RuntimeError("caller failed")

        assert _files_in(isolated_tempdir) == []

    def test_tolerates_the_file_already_being_gone(self, isolated_tempdir):
        from pathlib import Path

        from autobot_shared.temp_files import temporary_file_path

        with temporary_file_path(suffix=".png") as path:
            Path(path).unlink()

        assert _files_in(isolated_tempdir) == []
