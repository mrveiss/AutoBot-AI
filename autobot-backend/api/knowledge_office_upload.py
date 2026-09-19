# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Spreadsheet, presentation and OpenDocument uploads for the KB (#16775).

``DocumentParser`` has carried working parsers for these formats all along; the upload
form's allowlist simply never named them, so a user could not upload a file the backend
could already read. This is the routing that closes that gap -- no new extraction logic.

It deliberately does not extend the allowlist to the legacy binary formats: ``.doc`` and
``.ppt`` are OLE2 containers, and the parsers behind them (python-docx, python-pptx) read
only the OOXML ones. Advertising them would accept a valid file and then report it
corrupt, which is #16786, an owner decision of its own. ``.odg`` is left out too --
drawings carry almost no extractable text, and this endpoint stores flattened text only.

Format is resolved from content first (#16773), so a renamed upload reaches the parser
its bytes call for rather than the one its name claims.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException

from autobot_shared.logging_manager import get_logger
from media.document.zip_formats import verified_suffix

logger = get_logger(__name__)

#: Handled through DocumentParser. Every one is a ZIP container, so #16773's content
#: verification covers the whole set.
OFFICE_EXTENSIONS = {".xlsx", ".pptx", ".odt", ".ods", ".odp"}


def verified_upload_extension(filename: str, file_content: bytes) -> str:
    """The extension to dispatch on: what the bytes say, else what the name says (#16773).

    The allowlist upstream still rules on the *name* — this decides only which parser
    reads an already-accepted upload, so a mislabeled file is parsed correctly instead
    of being handed to the wrong parser.
    """
    named = os.path.splitext(filename.lower())[1]
    verified = verified_suffix(file_content)
    if verified and verified != named:
        logger.info("Upload %s: content is %s, name says %s — parsing as %s", filename, verified, named, verified)
        return verified
    return named


def extract_office_upload(filename: str, file_content: bytes, ext: str) -> str:
    """Text of an uploaded spreadsheet, presentation or OpenDocument file.

    ``DocumentParser`` reads from a path, so the bytes land in a temp file carrying the
    *verified* suffix. Runs blocking work on purpose: the caller
    (``api.knowledge._extract_file_content``) is already off the event loop in
    ``asyncio.to_thread``.

    Raises:
        HTTPException: 400 when no candidate parser could read the document, matching
            how the pdf and docx helpers next to the caller report a bad upload.
    """
    from utils.document_parser import parse_document_text

    with tempfile.NamedTemporaryFile(suffix=ext) as handle:
        handle.write(file_content)
        handle.flush()
        text, metadata = parse_document_text(Path(handle.name))

    if not metadata.get("extraction_success"):
        detail = metadata.get("extraction_error") or "no parser could read it"
        raise HTTPException(status_code=400, detail=f"Failed to parse {ext.lstrip('.')} file: {detail}")
    logger.info("Parsed %s upload %s as %s (%d chars)", ext, filename, metadata.get("format"), len(text))
    return text
