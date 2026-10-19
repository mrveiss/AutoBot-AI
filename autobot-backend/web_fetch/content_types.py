# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Content-Type dispatch for fetched bodies: only HTML reaches the HTML extractor (#18826).

``WebFetcher`` ran every non-jina body through the HTML extractor whatever the server
said it was, so a plain-text file was HTML-parsed and a PDF or image was decoded as
UTF-8 noise and stored as page text. Before #7401 the dispatch lived in
``SystemIntegration._process_web_content``; #7401 moved fetching into ``WebFetcher``
and left that dispatch behind with no caller. This is its home now.

=====================================  =====================================================
Content-Type                           Result
=====================================  =====================================================
``text/html``, ``application/xhtml+xml``  the one HTML extractor (:func:`extract_page`)
``text/plain``, ``text/markdown``      the text, whitespace normalised
``application/json``, ``*/*+json``     the JSON pretty-printed (passed through as text when
                                       it does not parse), as ``_process_web_content`` did
missing                                sniffed: HTML only when the body looks like HTML,
                                       ``unsupported`` when it looks binary, else text
anything else (binary, image, PDF)     :class:`UnsupportedContentType`, never extracted
=====================================  =====================================================

Every text this returns is sanitized exactly once: HTML inside :func:`extract_page`, text
and JSON here, both through :func:`knowledge.query_sanitizer.sanitize_document`.

:func:`decode_body` turns the fetched bytes into that body for every fetcher: the
byte-order mark, then the Content-Type ``charset=``, then (HTML or undeclared bodies
only) a ``<meta charset>`` in the first 2 KB, then UTF-8 with replacement characters.
"""

from __future__ import annotations

import codecs
import json
import re
from enum import Enum
from typing import Optional, Tuple, Union

from autobot_shared.logging_manager import get_logger
from knowledge.query_sanitizer import sanitize_document
from web_fetch.profile import IngestProfile, extract_page

logger = get_logger(__name__)

#: How much of a body without a Content-Type is inspected to sniff its kind.
_SNIFF_CHARS = 2048
#: Share of U+FFFD replacement characters above which an undeclared body is binary.
_BINARY_REPLACEMENT_RATIO = 0.05
_HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_TEXT_MEDIA_TYPES = frozenset({"text/plain", "text/markdown", "text/x-markdown"})
_CHARSET_PARAM = re.compile(r"""charset\s*=\s*["']?([^\s"';,]+)""", re.IGNORECASE)
_META_CHARSET = re.compile(rb"""<meta[^>]*?charset\s*=\s*["']?([A-Za-z0-9._:-]+)""", re.IGNORECASE)
#: Byte-order marks, longest first: a BOM outranks any declared charset (WHATWG encoding sniffing).
#: Longest marks first: the UTF-32 LE BOM (FF FE 00 00) starts with the UTF-16 LE BOM (FF FE).
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
#: Codecs a page may not select: UTF-7 can spell markup out of plain ASCII (WHATWG refuses it).
_REFUSED_CODECS = frozenset({"utf-7"})
#: Labels browsers read as windows-1252 (WHATWG): a page saying latin-1 means cp1252's smart quotes.
_AS_CP1252 = frozenset({"iso8859-1", "ascii"})
#: Opening tags that mark an undeclared body as HTML. Matched by a linear scan (``_looks_like_html``):
#: a ``(<!--.*?-->\s*)*`` regex backtracks catastrophically on repeated or unclosed comments.
_HTML_OPENERS = ("<!doctype html", "<html", "<head", "<body")


class BodyKind(str, Enum):
    """What a fetched body is, for extraction purposes."""

    HTML = "html"
    TEXT = "text"
    JSON = "json"
    UNSUPPORTED = "unsupported"


class UnsupportedContentType(ValueError):
    """A fetched body that is not HTML, text or JSON; it is never extracted as a page."""

    def __init__(self, content_type: Optional[str]) -> None:
        self.content_type = content_type or ""
        super().__init__(f"unsupported content type {self.content_type or '(undeclared, binary)'!r}")


def media_type(content_type: Optional[str]) -> str:
    """Return the lowercased media type of a Content-Type header, parameters dropped."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def _codec(label: Optional[str], origin: str) -> Optional[str]:
    """The Python codec for a charset *label*, or ``None`` (logged) when it is unknown or refused."""
    if not label:
        return None
    try:
        name = codecs.lookup(label.strip().lower()).name
    except LookupError:
        name = ""
    if not name or name in _REFUSED_CODECS:
        logger.warning("Ignoring unknown or refused charset %r from %s; decoding falls back (#18826)", label, origin)
        return None
    return "cp1252" if name in _AS_CP1252 else name


def _declared_charset(raw: bytes, content_type: Optional[str]) -> Optional[str]:
    """The header charset, else -- for an HTML or undeclared body -- a ``<meta>`` charset in the first 2 KB."""
    match = _CHARSET_PARAM.search(content_type or "")
    codec = _codec(match.group(1), "the Content-Type header") if match else None
    if codec or media_type(content_type) not in _HTML_MEDIA_TYPES | {""}:
        return codec
    meta = _META_CHARSET.search(raw[:_SNIFF_CHARS])
    return _codec(meta.group(1).decode("ascii"), "a <meta> tag") if meta else None


def decode_body(raw: bytes, content_type: Optional[str]) -> str:
    """Decode a fetched body: BOM, then declared charset, then UTF-8; undecodable bytes become U+FFFD."""
    for bom, codec in _BOMS:
        if raw.startswith(bom):
            return raw.decode(codec, errors="replace")
    codec = _declared_charset(raw, content_type) or "utf-8"
    try:
        return raw.decode(codec, errors="replace")
    except LookupError:
        # A codec that looks up but is not a text encoding (``base64``, ``rot13``, ...).
        logger.warning("Charset %r is not a text encoding; decoding as UTF-8 (#18826)", codec)
        return raw.decode("utf-8", errors="replace")


def _sniff(body: str) -> BodyKind:
    """Classify a body that came without a Content-Type, conservatively."""
    head = body[:_SNIFF_CHARS]
    if "\x00" in head or (head and head.count("�") / len(head) > _BINARY_REPLACEMENT_RATIO):
        return BodyKind.UNSUPPORTED
    return BodyKind.HTML if _looks_like_html(head) else BodyKind.TEXT


def _looks_like_html(head: str) -> bool:
    """Skip leading whitespace and complete ``<!-- -->`` comments, then test for an HTML opening tag."""
    i = 0
    while True:
        while i < len(head) and head[i].isspace():
            i += 1
        if not head.startswith("<!--", i):
            break
        end = head.find("-->", i + 4)
        if end < 0:
            return False  # an unclosed leading comment is not evidence of HTML
        i = end + 3
    rest = head[i : i + 16].lower()
    return any(rest.startswith(o) and (len(rest) == len(o) or rest[len(o)] in " \t\r\n>") for o in _HTML_OPENERS)


def classify_body(content_type: Optional[str], body: str) -> BodyKind:
    """Return the :class:`BodyKind` of *body* as declared by *content_type*."""
    declared = media_type(content_type)
    if not declared:
        return _sniff(body)
    if declared in _HTML_MEDIA_TYPES:
        return BodyKind.HTML
    if declared in _TEXT_MEDIA_TYPES:
        return BodyKind.TEXT
    if declared == "application/json" or declared.endswith("+json"):
        return BodyKind.JSON
    return BodyKind.UNSUPPORTED


def normalise_text(text: str) -> str:
    """Normalise line endings and whitespace while keeping paragraph breaks."""
    lines = (line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _json_text(body: str) -> str:
    """Pretty-print a JSON body; one that does not parse passes through as text."""
    try:
        return json.dumps(json.loads(body), indent=2, ensure_ascii=False)
    except ValueError:
        return normalise_text(body)


def page_from_body(
    body: str, content_type: Optional[str], profile: Union[IngestProfile, str], url: str
) -> Tuple[BodyKind, str, str]:
    """Return ``(kind, title, text)`` for a fetched body; raise :class:`UnsupportedContentType` otherwise."""
    kind = classify_body(content_type, body)
    if kind is BodyKind.HTML:
        document = extract_page(body, profile, base_url=url)
        return kind, document.info.get("title", ""), document.text
    if kind is BodyKind.TEXT:
        return kind, "", sanitize_document(normalise_text(body), source="web_text").sanitized_text
    if kind is BodyKind.JSON:
        return kind, "", sanitize_document(_json_text(body), source="web_text").sanitized_text
    raise UnsupportedContentType(content_type)
