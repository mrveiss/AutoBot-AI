# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tell ZIP-based office and OpenDocument formats apart by content (#16773).

``detect_format`` verified pdf and docx by magic bytes; the other six office formats
were routed on their extension alone, by ``utils/document_parser.py``'s extension ->
parser dict and ``utils/document_extractors.py``'s suffix routing. All seven share the
same ``PK`` prefix, so the prefix cannot separate them -- what distinguishes them is
inside the archive. OOXML carries a part only its own type has (``word/document.xml``,
``xl/workbook.xml``, ``ppt/presentation.xml``); ODF stores an uncompressed ``mimetype``
member first, naming the type exactly.

This reads the central directory and at most one small member, so it does not read the
archive and adds no dependency: ``zipfile`` is stdlib, and ``detect_format`` already
unzips docx this way.

Research: ``docs/research/document-to-markdown-conversion-pipeline.md``, "What We Can
Adopt" #1.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

ZIP_MAGIC = b"PK"

#: OOXML: the part only that type carries.
OOXML_PARTS = {
    "word/document.xml": "docx",
    "xl/workbook.xml": "xlsx",
    "ppt/presentation.xml": "pptx",
}

#: ODF: the exact value of the archive's first member.
ODF_MIMETYPES = {
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "application/vnd.oasis.opendocument.graphics": "odg",
}

#: Where a verified format dispatches -- callers route on a suffix, not on the label.
SUFFIX_BY_FORMAT = {
    "docx": ".docx",
    "xlsx": ".xlsx",
    "pptx": ".pptx",
    "odt": ".odt",
    "ods": ".ods",
    "odp": ".odp",
    "odg": ".odg",
}

_ODF_MIMETYPE_MEMBER = "mimetype"
#: An ODF mimetype is a short ASCII string. Capping the read means a crafted archive
#: cannot hand us an arbitrarily large "mimetype" to hold in memory.
_MIMETYPE_MAX_BYTES = 128


def _odf_format(archive: zipfile.ZipFile, names: list[str]) -> str | None:
    """The ODF type named by the archive's first member, or None."""
    if not names or names[0] != _ODF_MIMETYPE_MEMBER:
        return None
    with archive.open(_ODF_MIMETYPE_MEMBER) as member:
        declared = member.read(_MIMETYPE_MAX_BYTES).decode("ascii", "ignore").strip()
    return ODF_MIMETYPES.get(declared)


def format_from_members(archive: zipfile.ZipFile) -> str | None:
    """The office/ODF format *archive* holds, or None for any other ZIP."""
    names = archive.namelist()
    odf = _odf_format(archive, names)
    if odf:
        return odf
    present = set(names)
    for part, fmt in OOXML_PARTS.items():
        if part in present:
            return fmt
    return None


def sniff_zip_format(source: bytes | bytearray | str | Path) -> str | None:
    """The verified format of *source*, or None when it is not an office/ODF container.

    None covers every "cannot tell" case alike -- not a ZIP, truncated, encrypted,
    unreadable, or a plain ZIP -- because the callers fall back to the extension they
    already trusted. Never raises: a sniff that fails must not fail an ingest.
    """
    try:
        if isinstance(source, (bytes, bytearray)):
            if bytes(source[:2]) != ZIP_MAGIC:
                return None
            with zipfile.ZipFile(io.BytesIO(bytes(source))) as archive:
                return format_from_members(archive)
        with zipfile.ZipFile(source) as archive:
            return format_from_members(archive)
    except (zipfile.BadZipFile, OSError, KeyError, ValueError, RuntimeError) as exc:
        logger.debug("ZIP format sniff failed (%s): %s", type(exc).__name__, exc)
        return None


def verified_suffix(source: bytes | bytearray | str | Path) -> str | None:
    """The suffix the verified format dispatches to, or None when unverified."""
    fmt = sniff_zip_format(source)
    return SUFFIX_BY_FORMAT.get(fmt) if fmt else None
