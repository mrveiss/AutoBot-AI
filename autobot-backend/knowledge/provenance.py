# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/knowledge/provenance.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where a stored fact came from, whichever intake leg wrote it (#17527).

Five legs write provenance and no two write it the same way. Measured on
`origin/main`:

===============  ===================================================  ==================
leg              keys                                                 what ``source`` is
===============  ===================================================  ==================
file upload      ``source``, ``type="file"``, ``filename``            the filename
transcriber      ``source_type="transcript"``, ``source``, ``recording_id``  a ``recording:<id>`` URN
watch folder     ``source="watch_folder"``, ``folder_id``, ``file_path``     a literal category
connector        ``source_type="connector"``, ``connector_type``, ``source_id``  absent
manual entry     ``source``, ``title``                                whatever the caller passed
===============  ===================================================  ==================

So ``metadata["source"]`` alone answers a different question per leg, and for a
connector-ingested fact it answers nothing. Every consumer that wants an origin
would otherwise have to know all five dialects; this module knows them once.

**It returns None rather than a guess.** The defect this exists to fix is a
provenance-shaped field holding a plausible value from a different question —
`llc/kb/context_builder.py`'s ``sources`` answering with a tenancy id, the graph
loader's ``source`` holding the constant ``"ecl_pipeline"``. A caller receiving
``None`` knows it does not know; a caller receiving a fabricated string does not.

This is the read path in #17527's migration: canonical keys are the eventual fix,
and until every leg writes them, one accessor that speaks every dialect is what
lets retrieval surface an origin at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

#: The leg names this module recognises. A metadata dict matching none of them
#: yields ``leg=None``, which is a different answer from "no provenance".
TRANSCRIPT = "transcript"
CONNECTOR = "connector"
WATCH_FOLDER = "watch_folder"
UPLOAD = "upload"
MANUAL = "manual"


@dataclass(frozen=True)
class DocumentOrigin:
    """Where one fact came from.

    ``leg`` is None when no dialect matched, which says *this module did not
    recognise the shape* — not *the fact has no source*. ``reference`` is None
    when nothing identifying was stored. The two are separate so a caller can
    tell an unrecognised writer from an unattributed fact.
    """

    leg: str | None
    reference: str | None

    @property
    def known(self) -> bool:
        return self.reference is not None


_UNKNOWN = DocumentOrigin(leg=None, reference=None)


def _text(metadata: Mapping[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _connector_origin(metadata: Mapping[str, Any]) -> DocumentOrigin:
    """The only leg that writes no `source`: connector plus the id it gave the item."""
    connector = _text(metadata, "connector_type") or _text(metadata, "source_connector_id")
    item = _text(metadata, "source_id")
    parts = [p for p in (connector, item) if p]
    return DocumentOrigin(leg=CONNECTOR, reference=f"connector:{':'.join(parts)}" if parts else None)


def _watch_folder_origin(metadata: Mapping[str, Any]) -> DocumentOrigin:
    """`source` is the category here, so the identity is the file it watched."""
    path = _text(metadata, "file_path") or _text(metadata, "filename")
    return DocumentOrigin(leg=WATCH_FOLDER, reference=f"file:{path}" if path else None)


def _upload_origin(metadata: Mapping[str, Any]) -> DocumentOrigin:
    name = _text(metadata, "filename") or _text(metadata, "source")
    return DocumentOrigin(leg=UPLOAD, reference=f"file:{name}" if name else None)


def document_origin(metadata: Mapping[str, Any] | None) -> DocumentOrigin:
    """The origin of the fact described by *metadata*.

    Checked most-specific first: ``source_type`` is decisive where a leg sets it,
    and the legs that do not set it are distinguished by the keys they do write.
    """
    if not metadata:
        return _UNKNOWN
    source_type = _text(metadata, "source_type")
    if source_type == "connector":
        return _connector_origin(metadata)
    if source_type == "transcript":
        # Already a URN: `recording:<id>`.
        return DocumentOrigin(leg=TRANSCRIPT, reference=_text(metadata, "source"))
    if _text(metadata, "source") == "watch_folder":
        return _watch_folder_origin(metadata)
    if _text(metadata, "type") == "file":
        return _upload_origin(metadata)
    source = _text(metadata, "source")
    if source:
        # Manual entry, and anything else that set only `source`. Passed through
        # rather than prefixed: inventing a scheme would claim to know its meaning.
        return DocumentOrigin(leg=MANUAL, reference=source)
    return _UNKNOWN


def document_origins(chunks: list[Mapping[str, Any]]) -> list[str]:
    """Distinct known origins across *chunks*, in first-seen order.

    Chunks whose origin is unknown are omitted rather than represented by a
    placeholder: a list of origins that contains an invented entry is the defect
    this module exists to remove.
    """
    seen: list[str] = []
    for chunk in chunks:
        origin = document_origin(chunk.get("metadata") if isinstance(chunk, Mapping) else None)
        if origin.reference and origin.reference not in seen:
            seen.append(origin.reference)
    return seen
