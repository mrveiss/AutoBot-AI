# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
POST /knowledge/extract — Schema-driven structured data extraction from a URL.

Issue #7405: Round 3 of the unified web-research epic (#7396).

Fetches a URL via :class:`web_fetch.WebFetcher`, strips script blocks as a
prompt-injection guard, calls the LLM gateway in structured-output mode, and
validates the response against the caller-supplied JSON Schema.

API contract::

    POST /knowledge/extract
    {
      "url":    "https://...",
      "schema": { /* JSON Schema draft 2020-12 */ },
      "render": "auto" | "fast" | "playwright",  # default: "auto"
      "ingest": true | false                       # default: false
    }

    200 OK::
    {
      "url": "https://...",
      "data": { /* extracted structured data */ },
      "schema_valid": true
    }

    422 (schema validation failure)::
    {
      "success": false,
      "error_code": "schema_invalid",
      "details": "..."
    }

    502 (fetch failure)::
    {
      "success": false,
      "error_code": "fetch_failed",
      "retryable": true
    }
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_knowledge_web import ExtractRequest, ExtractResponse
from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from web_fetch import FetchResult, RenderMode, WebFetcher
from web_fetch.extractors import extract_url
from web_fetch.ingest import ingest_markdown

logger = get_logger(__name__)

# #16375: mounted with no auth dependency. Owner decision: any signed-in user
# may extract — only the web-research settings mutations stay admin-only.
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/extract", response_model=ExtractResponse, summary="Extract structured data from a URL via LLM")
async def extract_url_endpoint(request: ExtractRequest) -> ExtractResponse:
    """Fetch *request.url* and extract structured data matching *request.json_schema*.

    The LLM gateway is called with ``structured_output=True`` so the model
    returns JSON.  The response is validated against the caller-supplied JSON
    Schema using ``jsonschema.Draft202012Validator``.

    When ``ingest=True``, the raw page markdown (not the extracted data) is
    indexed into ChromaDB — structured data is returned in the response only.
    """
    try:
        result = await extract_url(
            url=request.url,
            schema=request.json_schema,
            render=request.render,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error_code": "fetch_failed", "retryable": True, "details": str(exc)},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error_code": "schema_invalid", "details": str(exc)},
        )

    if request.ingest:
        await _maybe_ingest(request.url, result)

    return ExtractResponse(url=result["url"], data=result["data"], schema_valid=result["schema_valid"])


async def _maybe_ingest(url: str, result: Dict[str, Any]) -> None:
    """Optionally ingest the raw page markdown into ChromaDB (non-fatal on error)."""
    try:
        fetch_result: FetchResult = await WebFetcher.fetch(url, render=RenderMode.AUTO)
        if fetch_result.success and fetch_result.markdown:
            await ingest_markdown(fetch_result.url, fetch_result.markdown, fetch_result.title)
    except Exception as exc:
        logger.warning("extract ingest failed for %s: %s", url, exc)


def _create_extract_mcp_tool() -> Dict[str, Any]:
    """Return the MCP tool descriptor for the extract endpoint."""
    return {
        "name": "extract_structured_data",
        "description": (
            "Fetch a URL and extract structured data matching a JSON Schema via LLM. "
            "Strips script blocks before calling the LLM (prompt-injection guard). "
            "Returns validated JSON matching the supplied schema."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL to fetch"},
                "schema": {"type": "object", "description": "JSON Schema (draft 2020-12) for the output"},
                "render": {
                    "type": "string",
                    "enum": ["auto", "fast", "playwright"],
                    "default": "auto",
                    "description": "Render mode",
                },
                "ingest": {
                    "type": "boolean",
                    "default": False,
                    "description": "Index raw page markdown into ChromaDB",
                },
            },
            "required": ["url", "schema"],
        },
    }
