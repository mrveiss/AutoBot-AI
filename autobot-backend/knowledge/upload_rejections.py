# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stable, machine-readable rejection codes for ``POST /knowledge_base/upload`` (#17577).

The endpoint used to compose English prose only, so a client could show it
untranslated or not at all. Every rejection now carries a ``detail_code`` from
:class:`UploadRejectionCode` plus ``detail_params`` (limits, names, counts); the
English ``detail`` stays for logs, non-browser callers and as the fallback for a
code a client does not know. Codes are identifiers -- never reword or reuse one.
"""

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from media.document.extraction import ExtractedDocument

logger = get_logger(__name__)


class UploadRejectionCode(str, Enum):
    """Every reason an upload can be rejected. Params noted per code."""

    FILE_REQUIRED = "upload.file_required"  # {}
    INVALID_FILENAME = "upload.invalid_filename"  # {}
    TOO_LARGE = "upload.too_large"  # {max_mb: int}
    UNSUPPORTED_TYPE = "upload.unsupported_type"  # {allowed: list[str]}
    EXTRACTION_TIMEOUT = "upload.extraction_timeout"  # {filename: str, timeout_s: number}
    NO_TEXT_LAYER = "upload.no_text_layer"  # {page_count: int}  (scanned PDF, needs OCR)
    NO_TEXT_CONTENT = "upload.no_text_content"  # {}
    PARSE_FAILED = "upload.parse_failed"  # {format: str}
    PARSER_UNAVAILABLE = "upload.parser_unavailable"  # {library: str}
    INGEST_FAILED = "upload.ingest_failed"  # {}  (nothing was stored)
    INGEST_TIMEOUT = "upload.ingest_timeout"  # {}  (the ingest budget ran out before any chunk was stored)


class UploadRejection(HTTPException):
    """HTTPException that also carries a stable ``detail_code`` and ``detail_params``."""

    def __init__(self, code: UploadRejectionCode, detail: str, status_code: int = 400, **params: Any) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.detail_code = code.value
        self.detail_params: Dict[str, Any] = params


async def upload_rejection_handler(_request, exc: UploadRejection) -> JSONResponse:
    """Render ``{detail, detail_code, detail_params}`` -- ``detail`` keeps the legacy shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "detail_code": exc.detail_code, "detail_params": exc.detail_params},
        headers=getattr(exc, "headers", None),
    )


def no_text_rejection(extracted: "ExtractedDocument | None") -> UploadRejection:
    """Explain *why* no text was extracted, not merely that none was (#13884).

    Consumes the extraction ``_extract_file_content`` already performed
    instead of re-parsing the file: a second ``extract_pdf`` call doubled
    parse cost on a user-triggerable path and used a different dispatch route
    (magic-byte sniffing) than the extension-based one above it, which could
    disagree with it.

    A paginated document that parsed cleanly but carries no text layer is a
    scan; telling the user that is the difference between "try OCR" and "try
    another file". A DOCX or a non-document format gets the generic message —
    OCR is not the fix for an empty markdown file.
    """
    if extracted is None or extracted.format != "pdf":
        return UploadRejection(UploadRejectionCode.NO_TEXT_CONTENT, "No text content could be extracted from file")

    if extracted.page_count:
        return UploadRejection(
            UploadRejectionCode.NO_TEXT_LAYER,
            f"No text layer found in any of the {extracted.page_count} page(s). "
            "The document appears to be scanned or image-only and needs OCR.",
            page_count=extracted.page_count,
        )
    return UploadRejection(UploadRejectionCode.NO_TEXT_CONTENT, "No text content could be extracted from file")


def no_text_detail(extracted: "ExtractedDocument | None") -> str:
    """English sentence of :func:`no_text_rejection` (#13884)."""
    return no_text_rejection(extracted).detail


async def extract_within_deadline(extract: Callable[[str, bytes], Any], filename: str, file_content: bytes) -> Any:
    """Run the blocking *extract* off the event loop, rejecting the upload if it outlives the deadline.

    #14754: extraction is CPU-bound (PDF parsing, layout analysis) and the handler is async, so running
    it inline stalled every coroutine on the worker. The deadline is what makes the offload safe:
    to_thread frees the loop, but the default executor's slots are process-wide and shared with the OCR
    path, so an extraction that never returns would hold one indefinitely.
    """
    from media.document.ocr import extraction_timeout

    deadline = extraction_timeout()
    try:
        return await asyncio.wait_for(asyncio.to_thread(extract, filename, file_content), timeout=deadline)
    except asyncio.TimeoutError:
        logger.warning("Extraction of %s exceeded %ss", filename, deadline)
        raise UploadRejection(
            UploadRejectionCode.EXTRACTION_TIMEOUT,
            f"Could not read {filename!r} within {deadline}s. The document may be "
            "unusually large or complex; try splitting it.",
            status_code=422,
            filename=filename,
            timeout_s=deadline,
        )
