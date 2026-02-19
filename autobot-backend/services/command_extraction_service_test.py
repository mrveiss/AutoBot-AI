# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for command_extraction_service SLM API proxying (Issue #933)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.command_extraction_service import (
    ExtractedCommand,
    _extract_command_descriptions,
    _extract_command_list,
    _slm_exec,
    extract_host_commands,
)


def _patch_slm_exec(return_value):
    """Helper to patch _slm_exec with a fixed return value."""
    return patch(
        "services.command_extraction_service._slm_exec",
        new_callable=AsyncMock,
        return_value=return_value,
    )


class TestSlmExec:
    """Tests for _slm_exec (Issue #933)."""

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(
            return_value={"success": True, "stdout": "output", "stderr": ""}
        )
        resp_cm = MagicMock()
        resp_cm.__aenter__ = AsyncMock(return_value=resp)
        resp_cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=resp_cm)
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.command_extraction_service.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            ok, stdout, stderr = await _slm_exec(
                "04-Databases", "ls -la", slm_url="https://slm.test"
            )

        assert ok is True
        assert stdout == "output"
        called_url = session.post.call_args[0][0]
        assert "04-Databases/exec" in called_url

    @pytest.mark.asyncio
    async def test_returns_false_when_no_slm_url(self):
        ok, stdout, stderr = await _slm_exec("node1", "cmd", slm_url="")
        assert ok is False
        assert "SLM_URL not configured" in stderr

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        session = MagicMock()
        session.post.side_effect = Exception("network error")
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "services.command_extraction_service.aiohttp.ClientSession",
            return_value=session_cm,
        ):
            ok, stdout, stderr = await _slm_exec(
                "node1", "cmd", slm_url="https://slm.test"
            )
        assert ok is False
        assert "network error" in stderr


class TestExtractCommandList:
    """Tests for _extract_command_list (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_set_of_commands(self):
        with _patch_slm_exec((True, "ls\ncat\npwd\n", "")):
            cmds = await _extract_command_list("node1", "https://slm", "token")
        assert "ls" in cmds
        assert "cat" in cmds

    @pytest.mark.asyncio
    async def test_filters_short_names(self):
        with _patch_slm_exec((True, "ls\na\npwd\n", "")):
            cmds = await _extract_command_list("node1", "https://slm", "token")
        assert "a" not in cmds  # too short

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self):
        with _patch_slm_exec((False, "", "error")):
            cmds = await _extract_command_list("node1", "https://slm", "token")
        assert cmds == set()


class TestExtractCommandDescriptions:
    """Tests for _extract_command_descriptions (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_descriptions_dict(self):
        whatis_output = "ls (1) - list directory contents\ncat (1) - concatenate files"
        with _patch_slm_exec((True, whatis_output, "")):
            descs = await _extract_command_descriptions(
                "node1", {"ls", "cat"}, "https://slm", "token"
            )
        assert "ls" in descs
        assert "list directory" in descs["ls"]

    @pytest.mark.asyncio
    async def test_handles_batch_failure_gracefully(self):
        with _patch_slm_exec((False, "", "whatis error")):
            descs = await _extract_command_descriptions(
                "node1", {"ls"}, "https://slm", "token"
            )
        assert descs == {}


class TestExtractHostCommands:
    """Tests for extract_host_commands (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_extracted_commands(self):
        whatis_output = "ls (1) - list directory contents"
        side_effects = [
            (True, "ls\npwd\n", ""),  # compgen -c
            (True, whatis_output, ""),  # whatis ls pwd
        ]

        async def fake_exec(*args, **kwargs):
            return side_effects.pop(0)

        with patch(
            "services.command_extraction_service._slm_exec",
            side_effect=fake_exec,
        ):
            result = await extract_host_commands("04-Databases")

        assert "ls" in result
        assert isinstance(result["ls"], ExtractedCommand)
        assert result["ls"].source_hosts == ["04-Databases"]

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_commands(self):
        with _patch_slm_exec((False, "", "error")):
            result = await extract_host_commands("04-Databases")
        assert result == {}

    @pytest.mark.asyncio
    async def test_assigns_category(self):
        with patch(
            "services.command_extraction_service._slm_exec",
            new_callable=AsyncMock,
            side_effect=[
                (True, "ping\nls\n", ""),
                (True, "ping (8) - send ICMP\nls (1) - list files", ""),
            ],
        ):
            result = await extract_host_commands("node1")
        assert result["ping"].category == "network"
        assert result["ls"].category == "file_management"
