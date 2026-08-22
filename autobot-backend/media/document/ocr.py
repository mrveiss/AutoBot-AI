# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rasterize-then-OCR fallback for PDFs with no text layer (#13896).

A scanned PDF parses cleanly and yields nothing. #13884 made that *detectable* —
``ExtractedDocument.has_usable_text_layer`` and ``empty_page_numbers`` say which
pages carry no text. This module makes it *recoverable*: render those pages to
images and read them with tesseract.

Deliberately separate from ``extraction.py``. The canonical extractor stays free
of heavyweight optional dependencies, and OCR is opt-in per call rather than a
silent cost on every document — a born-digital PDF must never rasterize anything.

Both dependencies degrade rather than raise. ``pytesseract`` reaches a system
binary that a host may not have installed (#13885 shipped the binding for exactly
that reason), and the rasterizer is a native wheel. When either is missing the
caller gets a result that says so, which is the same contract #13884 established:
report what was not done rather than return an empty success.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from autobot_shared.env_utils import blank_to_none
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# Rasterization resolution. 150 DPI is the usual cause of OCR failures that get
# blamed on the engine; 300 is the long-standing scanning baseline for text and
# is what tesseract's own documentation assumes.
DEFAULT_OCR_DPI = 300

# Above this, OCR is refused rather than attempted. Rasterizing and reading a
# page costs CPU-seconds, so an unbounded document can occupy a worker for
# minutes — a caller that wants more must say so explicitly.
DEFAULT_MAX_OCR_PAGES = 50

# Per-page OCR wall-clock ceiling, seconds. Tesseract on a dense A4 page at 300
# DPI runs in single-digit seconds; this leaves headroom while still bounding a
# pathological page. Override with AUTOBOT_DOCUMENT_OCR_PAGE_TIMEOUT.
DEFAULT_OCR_PAGE_TIMEOUT = 60
# The whole-document ceiling. The page timeout bounds one page; this bounds
# the run, so a document of many just-under-the-page-limit pages cannot hold a
# worker indefinitely (#13896 review).
DEFAULT_OCR_TIMEOUT = 300

# Whole-document extraction (parse + table analysis), seconds. Generous
# relative to a normal parse so only a pathological document trips it.
DEFAULT_EXTRACTION_TIMEOUT = 120

# Ceilings. The floor alone left every knob unbounded upward, so a sane-looking
# config change — not just hostile input — removed the protection it configures
# (#14751). DPI is the sharpest: `render(scale=dpi/72)` allocates a bitmap sized
# by the page's declared box times the scale, so cost grows QUADRATICALLY in it.
MAX_OCR_DPI = 600  # beyond this adds no legibility tesseract can use
MAX_OCR_PAGES_CEILING = 500  # the page ceiling is the bound on a 5000-page scan
MAX_OCR_TIMEOUT = 1800  # a single ingest may not hold a worker for half an hour
MAX_EXTRACTION_TIMEOUT = 900  # an executor slot is shared; it may not be held forever
# A page may take up to a third of the whole-document budget. A flat 300s would
# have silently clamped an operator who had deliberately raised this knob, even
# where the document ceiling could accommodate that page. Derived rather than
# written twice, so the two ceilings cannot drift apart.
MAX_OCR_PAGE_TIMEOUT = MAX_OCR_TIMEOUT // 3

# Per-page rasterization budget, in pixels. A PDF declaring an enormous MediaBox
# becomes a multi-gigabyte allocation at 300 DPI before any per-page timeout can
# help — `_ocr_one_page` catches MemoryError, but an OS-level OOM kill lands
# before Python raises. 40 MP is roughly A0 at 300 DPI.
MAX_OCR_PAGE_PIXELS = 40_000_000

# What an unmeasurable or malformed page renders at: the default DPI rather
# than whatever was configured, so a bad declaration cannot buy a bigger bitmap.
_SAFE_UNMEASURED_SCALE = DEFAULT_OCR_DPI / 72


def extraction_timeout() -> int:
    """Whole-document extraction ceiling, seconds (#14754).

    Offloading to a thread frees the event loop but does not bound the work:
    `asyncio.to_thread` uses the process-wide default executor, so an extraction
    that never finishes occupies one of a small number of shared slots forever —
    slots the OCR path's own deadline-bounded calls also draw from.

    Distinct from `ocr_timeout`, which bounds only the OCR recovery pass.
    """
    return _positive_int_setting(
        blank_to_none(config.misc.document_extraction_timeout),
        DEFAULT_EXTRACTION_TIMEOUT,
        "AUTOBOT_DOCUMENT_EXTRACTION_TIMEOUT",
        MAX_EXTRACTION_TIMEOUT,
    )


def ocr_dpi() -> int:
    """Resolve the rasterization DPI from config."""
    return _positive_int_setting(
        blank_to_none(config.misc.document_ocr_dpi),
        DEFAULT_OCR_DPI,
        "AUTOBOT_DOCUMENT_OCR_DPI",
        MAX_OCR_DPI,
    )


def ocr_page_timeout() -> int:
    """Resolve the per-page OCR wall-clock ceiling, in seconds.

    The page ceiling bounds how many pages are read; this bounds how long any
    one of them may take. Both are needed on an ingest path taking arbitrary
    uploads — a single page can be arbitrarily expensive regardless of count.
    """
    return _positive_int_setting(
        blank_to_none(config.misc.document_ocr_page_timeout),
        DEFAULT_OCR_PAGE_TIMEOUT,
        "AUTOBOT_DOCUMENT_OCR_PAGE_TIMEOUT",
        MAX_OCR_PAGE_TIMEOUT,
    )


def max_ocr_pages() -> int:
    """Resolve the per-document page ceiling for OCR."""
    return _positive_int_setting(
        blank_to_none(config.misc.document_max_ocr_pages),
        DEFAULT_MAX_OCR_PAGES,
        "AUTOBOT_DOCUMENT_MAX_OCR_PAGES",
        MAX_OCR_PAGES_CEILING,
    )


def ocr_timeout() -> int:
    """Resolve the whole-document OCR wall-clock ceiling, in seconds.

    `ocr_page_timeout` bounds a single page and the page ceiling bounds how
    many are read, but neither bounds the run: fifty pages each finishing just
    inside the page timeout is still fifty times that budget. This is the
    deadline the caller enforces around the whole attempt.
    """
    return _positive_int_setting(
        blank_to_none(config.misc.document_ocr_timeout),
        DEFAULT_OCR_TIMEOUT,
        "AUTOBOT_DOCUMENT_OCR_TIMEOUT",
        MAX_OCR_TIMEOUT,
    )


def ocr_enabled() -> bool:
    """Whether the OCR fallback may run at all.

    Defaults to on: it only ever touches pages that produced no text, so a
    born-digital document rasterizes nothing and pays nothing. Turning it off
    trades scanned documents for a hard CPU ceiling.
    """
    raw = blank_to_none(config.misc.document_ocr_enabled)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def tesseract_cmd() -> str:
    """The configured tesseract binary path, or "" when unset.

    Read from the environment because there is no SSOT field for it and
    `ssot_config` is already over its size ceiling; the substantive defect was
    never where it is read from but that setting it did nothing (#14751).
    """
    return os.environ.get("TESSERACT_CMD", "").strip()


def _apply_tesseract_cmd(pytesseract) -> None:
    """Point pytesseract at the configured binary.

    `ocr_environment_report` displayed TESSERACT_CMD without ever assigning it,
    so an operator could believe they had redirected OCR when they had not — a
    diagnostic reporting a setting it does not apply is worse than no field.
    """
    configured = tesseract_cmd()
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured


def _positive_int_setting(raw: str | None, default: int, env_name: str, maximum: int | None = None) -> int:
    """Parse a positive-int knob, falling back loudly rather than silently.

    *maximum* is clamped to rather than rejected: an operator who asked for more
    than the ceiling wants as much as they can have, and refusing to the default
    would quietly give them *less* than they asked for (#14751).
    """
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; falling back to %d", env_name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%d must be positive; falling back to %d", env_name, value, default)
        return default
    if maximum is not None and value > maximum:
        logger.warning("%s=%d exceeds the %d ceiling; clamping", env_name, value, maximum)
        return maximum
    return value


@dataclass(frozen=True)
class OcrResult:
    """Outcome of an OCR attempt over a set of pages.

    ``attempted`` is the field that keeps this honest: an empty ``pages`` means
    "OCR ran and found nothing" only when ``attempted`` is true. Otherwise it
    means the attempt never happened, and ``reason`` says why (#13895 made the
    same distinction for tables).
    """

    attempted: bool
    pages: Dict[int, str] = field(default_factory=dict)
    reason: str = ""
    skipped_pages: Tuple[int, ...] = ()

    @property
    def recovered_any(self) -> bool:
        """Whether any page yielded non-whitespace text."""
        return any(text.strip() for text in self.pages.values())


class OcrUnavailableError(RuntimeError):
    """Raised only by :func:`require_ocr`; the normal path degrades instead."""


def ocr_availability() -> Tuple[bool, str]:
    """Report whether OCR can run here, and what is missing if not.

    Checked in dependency order so the message names the first real blocker
    rather than the last one tried. The tesseract *binary* is probed separately
    from its binding: #13885 shipped hosts where the system packages were present
    and the Python binding was not, and the reverse is equally possible.
    """
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract is not installed"

    _apply_tesseract_cmd(pytesseract)

    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False, "pypdfium2 is not installed, so PDF pages cannot be rasterized"

    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:
        return False, f"the tesseract binary is not usable: {exc}"

    return True, ""


def require_ocr() -> None:
    """Raise if OCR cannot run. For callers that want a hard failure."""
    available, reason = ocr_availability()
    if not available:
        raise OcrUnavailableError(reason)


def ocr_pdf_pages(raw: bytes, page_numbers: Sequence[int]) -> OcrResult:
    """OCR the given 1-indexed pages of a PDF.

    Only the requested pages are rendered. The caller decides which ones need it
    — normally ``extracted.empty_page_numbers`` — so a mixed document pays for
    its scanned appendix and not for its born-digital body.
    """
    wanted = sorted({int(n) for n in page_numbers})
    if not wanted:
        return OcrResult(attempted=False, reason="no pages requested")

    if not ocr_enabled():
        return OcrResult(attempted=False, reason="OCR is disabled by configuration", skipped_pages=tuple(wanted))

    available, reason = ocr_availability()
    if not available:
        logger.info("OCR unavailable, skipping %d page(s): %s", len(wanted), reason)
        return OcrResult(attempted=False, reason=reason, skipped_pages=tuple(wanted))

    ceiling = max_ocr_pages()
    skipped = tuple(wanted[ceiling:])
    if skipped:
        logger.warning(
            "OCR page ceiling %d reached; %d page(s) left unread. "
            "Raise AUTOBOT_DOCUMENT_MAX_OCR_PAGES to change this.",
            ceiling,
            len(skipped),
        )

    return _run_ocr(raw, wanted[:ceiling], skipped)


def _run_ocr(raw: bytes, wanted: List[int], skipped: Tuple[int, ...]) -> OcrResult:
    """Render and read the pages, translating any failure into a reported reason."""
    import pypdfium2
    import pytesseract

    _apply_tesseract_cmd(pytesseract)

    dpi = ocr_dpi()
    recovered: Dict[int, str] = {}

    try:
        document = pypdfium2.PdfDocument(raw)
        try:
            page_count = len(document)
            for number in wanted:
                if not 1 <= number <= page_count:
                    logger.warning("Requested OCR for page %d outside a %d-page document", number, page_count)
                    continue
                recovered[number] = _ocr_one_page(document, number, dpi, pytesseract)
        finally:
            document.close()
    except Exception as exc:
        logger.warning("OCR failed while rasterizing: %s", exc)
        return OcrResult(attempted=False, reason=f"rasterization failed: {exc}", skipped_pages=tuple(wanted) + skipped)

    return OcrResult(attempted=True, pages=recovered, skipped_pages=skipped)


def _bounded_scale(page, dpi: int, number: int) -> float:
    """Scale for *page* at *dpi*, reduced so the bitmap fits the pixel budget.

    The page ceiling bounds how many pages are rasterized and the page timeout
    bounds how long one may take, but neither bounds how LARGE one is: a PDF
    declaring an enormous MediaBox allocates a multi-gigabyte bitmap at the
    default DPI before any timeout can intervene, and an OS-level OOM kill
    lands before Python raises MemoryError for the caller to catch (#14751).

    Downscaled rather than refused — OCR at a lower effective DPI still reads a
    page, whereas skipping it returns nothing for a page that was merely large.
    A page whose size cannot be measured — or which declares a degenerate one —
    renders at the DEFAULT DPI rather than whatever was configured, so a bad
    declaration cannot buy a larger bitmap than a good one.
    """
    scale = dpi / 72
    try:
        width, height = page.get_size()
    except Exception:  # a page that will not report its size is not measurable
        logger.warning("page %d would not report its size; keeping the default scale", number)
        return _SAFE_UNMEASURED_SCALE
    projected = (width * scale) * (height * scale)
    if projected <= 0:
        # A zero or inverted MediaBox is malformed, not small. Treating it as
        # "within budget" handed back the full scale for exactly the hostile
        # input this bound exists to catch, since a renderer taking abs() of a
        # negative dimension would then allocate unclamped.
        logger.warning("page %d declares a degenerate size; keeping the default scale", number)
        return _SAFE_UNMEASURED_SCALE
    if projected <= MAX_OCR_PAGE_PIXELS:
        return scale
    reduced = scale * (MAX_OCR_PAGE_PIXELS / projected) ** 0.5
    logger.warning(
        "page %d would rasterize to %.0f MP at %d DPI; reducing to %.0f DPI to stay " "within the %.0f MP budget",
        number,
        projected / 1_000_000,
        dpi,
        reduced * 72,
        MAX_OCR_PAGE_PIXELS / 1_000_000,
    )
    return reduced


def _ocr_one_page(document, number: int, dpi: int, pytesseract) -> str:
    """Read one page, degrading to empty text rather than failing the document.

    `render(scale=...)` takes a multiple of 72 DPI, pdfium's unit, and returns a
    PIL image directly — so the explicit `frombytes` round-trip the PyMuPDF
    version needed is gone rather than reimplemented.

    The `timeout` is not optional decoration. This runs on an ingest path that
    accepts arbitrary uploads, and `image_to_string` is otherwise unbounded: a
    page whose MediaBox is pathological still renders a very large bitmap
    however few pages were requested, so the page ceiling caps count and this
    caps cost.
    """
    try:
        page = document[number - 1]
        image = page.render(scale=_bounded_scale(page, dpi, number)).to_pil()
        try:
            return pytesseract.image_to_string(image, timeout=ocr_page_timeout()) or ""
        finally:
            image.close()
    except Exception as exc:
        logger.warning("OCR failed on page %d: %s", number, exc)
        return ""


def ocr_environment_report() -> Dict[str, object]:
    """Diagnostic snapshot for a health endpoint or a support bundle.

    #13885 was invisible for months because nothing ever asked whether the OCR
    stack was reachable. This makes that question answerable without running a
    document through the pipeline.
    """
    available, reason = ocr_availability()
    return {
        "available": available,
        "reason": reason,
        "dpi": ocr_dpi(),
        "max_pages": max_ocr_pages(),
        "tesseract_cmd": tesseract_cmd(),
    }
