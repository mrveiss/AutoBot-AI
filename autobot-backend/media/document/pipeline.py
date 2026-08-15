# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Document Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual document processing

"""Document processing pipeline for text documents, PDFs, DOCX, etc."""

import base64
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from media.core.pipeline import BasePipeline
from media.core.types import MediaInput, MediaType, ProcessingResult
from media.document.extraction import (
    DocumentDependencyError,
    DocumentExtractionError,
    ExtractedDocument,
    detect_format,
    extract_document,
)

logger = get_logger(__name__)


class DocumentPipeline(BasePipeline):
    """Pipeline for processing document content (PDF, DOCX, TXT, etc.)."""

    PIPELINE_NAME = "document"
    SUPPORTED_TYPES = [MediaType.DOCUMENT, MediaType.TEXT]

    async def _process_impl(self, media_input: MediaInput) -> ProcessingResult:
        """Process document content."""
        result_data = await self._process_document(media_input)
        confidence = self._calculate_confidence(result_data)

        return ProcessingResult(
            result_id=f"document_{media_input.media_id}",
            media_id=media_input.media_id,
            media_type=media_input.media_type,
            intent=media_input.intent,
            success=True,
            confidence=confidence,
            result_data=result_data,
            processing_time=0.0,  # Set by BasePipeline
        )

    async def _process_document(self, media_input: MediaInput) -> Dict[str, Any]:
        """Extract via the canonical core and adapt the result to this pipeline's shape."""
        raw_bytes = self._decode_input(media_input.data)
        mime_type = (media_input.mime_type or "").lower()

        try:
            extracted = extract_document(raw_bytes, mime_type)
        except DocumentDependencyError as exc:
            # A missing library is a deployment gap, not a bad upload — keep the
            # two distinguishable so one is never diagnosed as the other.
            return self._unavailable_result(detect_format(raw_bytes, mime_type), str(exc), media_input.metadata)
        except DocumentExtractionError as exc:
            logger.warning("Document extraction failed: %s", exc)
            return self._error_result(detect_format(raw_bytes, mime_type), str(exc), media_input.metadata)

        return self._to_result(extracted, media_input.metadata)

    # ------------------------------------------------------------------
    # Decoding helpers
    # ------------------------------------------------------------------

    def _decode_input(self, data: Any) -> bytes:
        """Normalize input to bytes (base64 string, bytes, or file path)."""
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            # Try base64 first, then treat as file path
            try:
                return base64.b64decode(data)
            except Exception:
                with open(data, "rb") as fh:
                    return fh.read()
        raise ValueError(f"Unsupported document data type: {type(data)}")

    # ------------------------------------------------------------------
    # Result adaptation
    # ------------------------------------------------------------------

    def _to_result(self, extracted: ExtractedDocument, metadata: Dict) -> Dict[str, Any]:
        """Adapt a canonical ExtractedDocument to this pipeline's result dict."""
        # Resolved once and threaded through, rather than each helper reading
        # ``has_usable_text_layer`` (and re-resolving the config knobs behind
        # it) independently — that used to emit a misconfigured-value warning
        # twice per document (#13884 review).
        usable_content = extracted.has_usable_content
        result: Dict[str, Any] = {
            "type": "document_analysis",
            "format": extracted.format,
            "extracted_text": extracted.text,
            "page_count": extracted.page_count,
            "confidence": self._confidence_for(extracted, usable_content),
            "metadata": metadata,
        }
        result.update(self._format_fields(extracted))
        result.update(self._text_layer_fields(extracted, usable_content))
        return result

    def _text_layer_fields(self, extracted: ExtractedDocument, usable_content: bool) -> Dict[str, Any]:
        """Report what was actually readable, so empty is never mistaken for blank.

        Two distinct failure shapes get two distinct statuses (#13884):
        ``no_text_layer`` for a paginated document (a PDF) with nothing
        usable — a scan, where OCR is the fix — and ``empty_document`` for an
        unpaginated one (a blank ``.txt``/``.md``, or a DOCX with neither text
        nor tables), where OCR does not apply at all. A DOCX whose content is
        entirely a table is neither: its data lives in ``tables``, and
        ``usable_content`` reflects that.
        """
        fields: Dict[str, Any] = {}

        # Report unreadable pages even when the document as a whole is usable: a
        # 40-page contract with one scanned addendum still has a hole in it, and
        # the caller can only OCR what it knows is missing.
        if extracted.pages and extracted.empty_page_numbers:
            fields["empty_pages"] = list(extracted.empty_page_numbers)
            fields["text_page_ratio"] = round(extracted.text_page_ratio, 4)
            fields["chars_per_page"] = round(extracted.avg_chars_per_page, 1)

        if usable_content:
            return fields

        if extracted.pages:
            fields["processing_status"] = "no_text_layer"
            fields["text_layer_reason"] = (
                "No recoverable text layer — the document is most likely scanned or image-only and needs OCR."
            )
            fields.setdefault("text_page_ratio", round(extracted.text_page_ratio, 4))
            fields.setdefault("chars_per_page", round(extracted.avg_chars_per_page, 1))
            logger.info(
                "Document has no usable text layer (format=%s, pages=%s, text_page_ratio=%.2f, chars_per_page=%.1f)",
                extracted.format,
                extracted.page_count,
                extracted.text_page_ratio,
                extracted.avg_chars_per_page,
            )
        else:
            fields["processing_status"] = "empty_document"
            fields["text_layer_reason"] = "The document contains no extractable text or table content."
            logger.info("Document has no extractable content (format=%s)", extracted.format)
        return fields

    def _format_fields(self, extracted: ExtractedDocument) -> Dict[str, Any]:
        """Per-format fields that are not part of the canonical result."""
        if extracted.format == "text":
            return {
                "line_count": len(extracted.text.splitlines()),
                "char_count": extracted.char_count,
            }

        fields: Dict[str, Any] = {
            "tables": [list(table) for table in extracted.tables],
            # #13895: an empty `tables` used to mean both "this document has no
            # tables" and "we never looked". PDF returned [] unconditionally
            # while DOCX did real work, from an identical-looking result — so a
            # consumer could not tell a genuine negative from a missing feature.
            "tables_attempted": extracted.tables_attempted,
            "document_info": dict(extracted.info),
        }
        if extracted.format == "docx":
            fields["paragraph_count"] = len([line for line in extracted.text.split("\n") if line.strip()])
        return fields

    def _confidence_for(self, extracted: ExtractedDocument, usable_content: bool) -> float:
        """Score what was recovered, not merely that parsing did not raise.

        A document with no usable text layer *and* no tables scores 0.0:
        previously an image-only PDF returned 0.95 with an empty
        ``extracted_text``, which asserted the document was blank rather than
        unread (#13884). A DOCX whose content is entirely a table still scores
        like a success — its data is real, it just lives in ``tables`` rather
        than ``extracted_text``.
        """
        if not usable_content:
            return 0.0
        return 1.0 if extracted.format == "text" else 0.95

    # ------------------------------------------------------------------
    # Error/fallback helpers
    # ------------------------------------------------------------------

    def _unavailable_result(self, fmt: str, reason: str, metadata: Dict) -> Dict[str, Any]:
        """Return structured result when a required library is unavailable."""
        logger.warning("Document pipeline (%s): %s", fmt, reason)
        return {
            "type": "document_analysis",
            "format": fmt,
            "extracted_text": "",
            "page_count": 0,
            "tables": [],
            "tables_attempted": False,
            "processing_status": "unavailable",
            "unavailability_reason": reason,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _error_result(self, fmt: str, error: str, metadata: Dict) -> Dict[str, Any]:
        """Return structured result on processing error."""
        return {
            "type": "document_analysis",
            "format": fmt,
            "extracted_text": "",
            "page_count": 0,
            "tables": [],
            "tables_attempted": False,
            "processing_status": "error",
            "error": error,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _calculate_confidence(self, result_data: Dict[str, Any]) -> float:
        """Calculate confidence score from result data."""
        return result_data.get("confidence", 0.5)
