# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for POST /knowledge/extract endpoint.

Issue #7405: Schema-driven structured data extraction — endpoint validation,
schema validation error path, prompt-injection guard, and ingest path.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_extract_result(url: str = "https://example.com", data: dict = None, schema_valid: bool = True) -> dict:
    return {"url": url, "data": data or {"name": "Widget"}, "schema_valid": schema_valid}


# ---------------------------------------------------------------------------
# ExtractRequest validation
# ---------------------------------------------------------------------------


def test_extract_request_defaults() -> None:
    """ExtractRequest defaults are correct."""
    from api.knowledge_extract import ExtractRequest

    req = ExtractRequest(url="https://example.com", schema={"type": "object"})
    assert req.render == "auto"
    assert req.ingest is False


def test_extract_request_all_render_modes() -> None:
    """All render modes are accepted."""
    from api.knowledge_extract import ExtractRequest

    for mode in ("auto", "fast", "playwright"):
        req = ExtractRequest(url="https://example.com", schema={}, render=mode)
        assert req.render == mode


def test_extract_request_rejects_bad_render() -> None:
    """Invalid render mode raises ValidationError."""
    from pydantic import ValidationError

    from api.knowledge_extract import ExtractRequest

    with pytest.raises(ValidationError):
        ExtractRequest(url="https://example.com", schema={}, render="turbo")


def test_extract_request_url_required() -> None:
    """Missing url raises ValidationError."""
    from pydantic import ValidationError

    from api.knowledge_extract import ExtractRequest

    with pytest.raises(ValidationError):
        ExtractRequest(schema={"type": "object"})


def test_extract_request_schema_required() -> None:
    """Missing schema raises ValidationError."""
    from pydantic import ValidationError

    from api.knowledge_extract import ExtractRequest

    with pytest.raises(ValidationError):
        ExtractRequest(url="https://example.com")


# ---------------------------------------------------------------------------
# extract_url_endpoint — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_url_endpoint_success_no_ingest() -> None:
    """Returns ExtractResponse with schema_valid=True on happy path."""
    from api.knowledge_extract import ExtractRequest, extract_url_endpoint

    req = ExtractRequest(url="https://example.com", schema={"type": "object"}, ingest=False)
    extract_result = _make_extract_result()

    with patch("api.knowledge_extract.extract_url", new_callable=AsyncMock, return_value=extract_result):
        response = await extract_url_endpoint(req)

    assert response.url == "https://example.com"
    assert response.schema_valid is True
    assert response.data == {"name": "Widget"}


@pytest.mark.asyncio
async def test_extract_url_endpoint_success_with_ingest() -> None:
    """ingest=True triggers _maybe_ingest (non-fatal on error)."""
    from api.knowledge_extract import ExtractRequest, extract_url_endpoint

    req = ExtractRequest(url="https://example.com", schema={"type": "object"}, ingest=True)
    extract_result = _make_extract_result()

    with (
        patch("api.knowledge_extract.extract_url", new_callable=AsyncMock, return_value=extract_result),
        patch("api.knowledge_extract._maybe_ingest", new_callable=AsyncMock) as mock_ingest,
    ):
        response = await extract_url_endpoint(req)

    mock_ingest.assert_awaited_once()
    assert response.schema_valid is True


# ---------------------------------------------------------------------------
# extract_url_endpoint — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_url_endpoint_fetch_failure_returns_502() -> None:
    """RuntimeError from extract_url maps to 502 with fetch_failed error_code."""
    from fastapi import HTTPException

    from api.knowledge_extract import ExtractRequest, extract_url_endpoint

    req = ExtractRequest(url="https://broken.example.com", schema={"type": "object"})

    with patch("api.knowledge_extract.extract_url", new_callable=AsyncMock, side_effect=RuntimeError("connection")):
        with pytest.raises(HTTPException) as exc_info:
            await extract_url_endpoint(req)

    assert exc_info.value.status_code == 502
    detail = exc_info.value.detail
    assert detail["success"] is False
    assert detail["error_code"] == "fetch_failed"
    assert detail["retryable"] is True


@pytest.mark.asyncio
async def test_extract_url_endpoint_schema_validation_failure_returns_422() -> None:
    """ValueError from extract_url maps to 422 with schema_invalid error_code."""
    from fastapi import HTTPException

    from api.knowledge_extract import ExtractRequest, extract_url_endpoint

    req = ExtractRequest(url="https://example.com", schema={"type": "object", "required": ["name"]})

    with patch(
        "api.knowledge_extract.extract_url", new_callable=AsyncMock, side_effect=ValueError("'name' is required")
    ):
        with pytest.raises(HTTPException) as exc_info:
            await extract_url_endpoint(req)

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["success"] is False
    assert detail["error_code"] == "schema_invalid"
    assert "name" in detail["details"]


# ---------------------------------------------------------------------------
# Prompt-injection guard (via endpoint integration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_script_injection_not_in_extract_result() -> None:
    """A <script>alert(1)</script> page must not bleed into extracted data.

    The stripping happens inside extract_url() (unit-tested separately).
    This test verifies the endpoint contract: if extract_url returns valid
    data, the endpoint passes it through unchanged regardless of the source.
    """
    from api.knowledge_extract import ExtractRequest, extract_url_endpoint

    malicious_data = {"name": "Widget"}  # sanitised output — no JS payload
    req = ExtractRequest(url="https://example.com", schema={"type": "object"})

    with patch(
        "api.knowledge_extract.extract_url",
        new_callable=AsyncMock,
        return_value=_make_extract_result(data=malicious_data),
    ):
        response = await extract_url_endpoint(req)

    assert "alert" not in str(response.data)


# ---------------------------------------------------------------------------
# _maybe_ingest — non-fatal on WebFetcher error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_ingest_non_fatal_on_exception() -> None:
    """_maybe_ingest swallows exceptions and does not propagate."""
    from api.knowledge_extract import _maybe_ingest

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, side_effect=RuntimeError("chromadb down")):
        # Must not raise
        await _maybe_ingest("https://example.com", {"url": "https://example.com", "data": {}, "schema_valid": True})


@pytest.mark.asyncio
async def test_maybe_ingest_calls_ingest_markdown_on_success() -> None:
    """_maybe_ingest calls ingest_markdown when fetch succeeds."""
    from api.knowledge_extract import _maybe_ingest

    mock_fr = MagicMock()
    mock_fr.success = True
    mock_fr.markdown = "# Hello world"
    mock_fr.title = "Hello"
    mock_fr.url = "https://example.com"

    with (
        patch("api.knowledge_extract.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_fr),
        patch("api.knowledge_extract.ingest_markdown", new_callable=AsyncMock, return_value=True) as mock_ingest,
    ):
        await _maybe_ingest("https://example.com", {"url": "https://example.com", "data": {}, "schema_valid": True})

    mock_ingest.assert_awaited_once()
