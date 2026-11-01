# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bounds that apply BEFORE an attached file is opened for text (#20195).

The text budget in ``attachment_context`` cuts what reaches the prompt, but extraction runs first, so a huge
file or a small archive that expands to gigabytes (an Office zip bomb) would already have cost the process its
memory and time. These checks run ahead of any reader and have no side effects:

* the file on disk is larger than ``limits.ATTACHMENT_MAX_FILE_BYTES``;
* a zip-based format (OOXML / OpenDocument) whose own member index sums to more than
  ``limits.ATTACHMENT_MAX_UNCOMPRESSED_BYTES``. ``zipfile`` stops reading a member at its declared size, so the
  index is the bound the extractors run under; a file that is not a readable archive is left to the extractor;
* a timeout (``limits.ATTACHMENT_EXTRACT_TIMEOUT_SECONDS``) around the reader, applied by the caller via
  ``within_extract_deadline``. The extraction thread cannot be killed; the turn simply stops waiting for it.

Only sizes, codes and ids are ever logged.
"""

from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path
from typing import Any, Awaitable

from autobot_shared.logging_manager import get_logger
from chat_workflow import limits

logger = get_logger(__name__)

#: Formats whose container is a zip archive (the rest are read as PDF, legacy binary or plain text).
ZIP_SUFFIXES = frozenset({".docx", ".docm", ".dotx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".odg"})


def _declared_uncompressed(path: Path) -> int | None:
    """Sum of the archive's declared member sizes, or None when *path* is not a readable zip."""
    try:
        with zipfile.ZipFile(path) as archive:
            return sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, OSError):
        return None


def refusal_code(path: Path, suffix: str) -> str | None:
    """The notice code for a file that must not be opened (``over_budget``), else None. Blocking: use a thread."""
    try:
        size = path.stat().st_size
    except OSError:
        return None  # a missing file is the reader's "unreadable", reported there
    if size > limits.ATTACHMENT_MAX_FILE_BYTES:
        logger.warning("Attachment refused before extraction: oversize (%d bytes)", size)
        return "over_budget"
    if suffix in ZIP_SUFFIXES:
        declared = _declared_uncompressed(path)
        if declared is not None and declared > limits.ATTACHMENT_MAX_UNCOMPRESSED_BYTES:
            logger.warning("Attachment refused before extraction: archive declares %d bytes", declared)
            return "over_budget"
    return None


async def within_extract_deadline(work: Awaitable[Any]) -> Any:
    """Await *work* for at most the configured extraction time; ``TimeoutError`` past it."""
    return await asyncio.wait_for(work, timeout=limits.ATTACHMENT_EXTRACT_TIMEOUT_SECONDS)
