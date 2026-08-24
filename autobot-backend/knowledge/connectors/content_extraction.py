# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared content-extraction helpers for knowledge connectors.

Pure, provider-agnostic utilities that were byte-identical across the Google
Drive and OneDrive connectors (and, for ``content_hash``, several others).
Extracted here so every connector imports a single implementation (#9794
duplication sweep) instead of carrying its own copy.
"""

import hashlib

from autobot_shared.logging_manager import get_logger
from media.document.extraction import DocumentExtractionError, extract_docx, extract_pdf

logger = get_logger(__name__)


def content_hash(text: str) -> str:
    """Generate SHA-256 hash of content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_text_from_docx(content_bytes: bytes) -> str:
    """Extract text from Word .docx file.

    Connectors ingest in bulk, so a single unreadable file must not abort a sync:
    failures degrade to an empty string, as they always have here.
    """
    try:
        return extract_docx(content_bytes).text
    except DocumentExtractionError as exc:
        logger.warning("Failed to extract text from DOCX: %s", exc)
        return ""


def extract_text_from_pdf(content_bytes: bytes) -> str:
    """Extract text from PDF file.

    Previously ran ``PyPDF2``, which is unmaintained, while the repo pins
    ``pypdf`` as a security update — so Drive/OneDrive ingestion used the library
    the rest of the codebase had deliberately moved off (#13893). Now shares the
    canonical extractor, which emits the same ``## Page N`` markers this
    connector already used.
    """
    try:
        return extract_pdf(content_bytes).text
    except DocumentExtractionError as exc:
        logger.warning("Failed to extract text from PDF: %s", exc)
        return ""
