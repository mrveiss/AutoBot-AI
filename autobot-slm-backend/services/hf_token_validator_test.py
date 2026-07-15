# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the HuggingFace token validation helper (#11718).

Mocks ``httpx.AsyncClient`` — no real network calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.hf_token_validator import UNREACHABLE_WARNING, probe_hf_token

FAKE_HF_VALUE = "hf" + "_" + "fixturevalue123"


def _mock_client_returning(status_code: int):
    """Patch httpx.AsyncClient so client.get(...) returns a response with status_code."""
    response = MagicMock()
    response.status_code = status_code

    client_instance = AsyncMock()
    client_instance.get = AsyncMock(return_value=response)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)

    return patch("services.hf_token_validator.httpx.AsyncClient", return_value=client_instance)


def _mock_client_raising(exc: Exception):
    """Patch httpx.AsyncClient so entering the context manager raises exc."""
    client_instance = AsyncMock()
    client_instance.__aenter__ = AsyncMock(side_effect=exc)
    client_instance.__aexit__ = AsyncMock(return_value=False)

    return patch("services.hf_token_validator.httpx.AsyncClient", return_value=client_instance)


class TestProbeHfTokenValid:
    @pytest.mark.asyncio
    async def test_200_is_valid(self):
        with _mock_client_returning(200):
            is_valid, warning = await probe_hf_token(FAKE_HF_VALUE)
        assert is_valid is True
        assert warning is None


class TestProbeHfTokenInvalid:
    @pytest.mark.asyncio
    async def test_401_is_invalid_no_warning(self):
        with _mock_client_returning(401):
            is_valid, warning = await probe_hf_token(FAKE_HF_VALUE)
        assert is_valid is False
        assert warning is None


class TestProbeHfTokenUnreachable:
    @pytest.mark.asyncio
    async def test_network_error_does_not_block(self):
        with _mock_client_raising(httpx.ConnectTimeout("timed out")):
            is_valid, warning = await probe_hf_token(FAKE_HF_VALUE)
        assert is_valid is None
        assert warning == UNREACHABLE_WARNING

    @pytest.mark.asyncio
    async def test_unexpected_5xx_does_not_block(self):
        with _mock_client_returning(503):
            is_valid, warning = await probe_hf_token(FAKE_HF_VALUE)
        assert is_valid is None
        assert warning is not None
        assert "503" in warning


class TestProbeHfTokenNeverLogsValue:
    @pytest.mark.asyncio
    async def test_value_not_in_warning(self):
        with _mock_client_raising(httpx.ConnectError("no route")):
            _, warning = await probe_hf_token(FAKE_HF_VALUE)
        assert FAKE_HF_VALUE not in (warning or "")
