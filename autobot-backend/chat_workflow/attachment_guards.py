# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bounds that apply BEFORE an attached file is opened for text (#20195).

The text budget in ``attachment_context`` cuts what reaches the prompt, but extraction runs first, so a huge
file or a small archive that expands to gigabytes (an Office zip bomb) would already have cost the process its
memory and time. These checks run ahead of any reader and have no side effects:

* the file on disk is larger than ``limits.ATTACHMENT_MAX_FILE_BYTES``;
* any file that IS a zip archive, judged by its content (``zipfile.is_zipfile``), never by its name: the parser
  picks the format from content too, so a bomb named ``x.pdf``, ``.doc`` or ``.ppt`` is extracted as an Office
  archive and must be bounded as one. Its own member index must sum to at most
  ``limits.ATTACHMENT_MAX_UNCOMPRESSED_BYTES``. ``zipfile`` stops reading a member at its declared size, so the
  index is the bound the extractors run under; a file that is not a readable archive is left to the extractor;
* a timeout (``limits.ATTACHMENT_EXTRACT_TIMEOUT_SECONDS``) around the reader, applied by the caller via
  ``within_extract_deadline``. The extraction thread cannot be killed; the turn simply stops waiting for it, and
  its slot in the bounded pool (``attachment_extract``) stays taken until it really ends.

Not bounded here: the decompressed size of a PDF. pypdf caps each stream (~75 MB) but not their sum, and the
table and OCR readers have no cap; the file-size cap, the deadline and the pool bound are what limit a PDF.

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


def _declared_uncompressed(path: Path) -> int | None:
    """Sum of the archive's declared member sizes, or None when *path*'s CONTENT is not a readable zip."""
    try:
        if not zipfile.is_zipfile(path):
            return None
        with zipfile.ZipFile(path) as archive:
            return sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, OSError):
        return None


def refusal_code(path: Path) -> str | None:
    """The notice code for a file that must not be opened (``over_budget``), else None. Blocking: use a thread."""
    try:
        size = path.stat().st_size
    except OSError:
        return None  # a missing file is the reader's "unreadable", reported there
    if size > limits.ATTACHMENT_MAX_FILE_BYTES:
        logger.warning("Attachment refused before extraction: oversize (%d bytes)", size)
        return "over_budget"
    declared = _declared_uncompressed(path)  # by content: the name says nothing about what the parser will open
    if declared is not None and declared > limits.ATTACHMENT_MAX_UNCOMPRESSED_BYTES:
        logger.warning("Attachment refused before extraction: archive declares %d bytes", declared)
        return "over_budget"
    return None


async def within_extract_deadline(work: Awaitable[Any]) -> Any:
    """Await *work* for at most the configured extraction time; ``TimeoutError`` past it."""
    return await asyncio.wait_for(work, timeout=limits.ATTACHMENT_EXTRACT_TIMEOUT_SECONDS)
