# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Document Analysis Skill (Issue #731, wired in #13897)

Analyze documents (PDF, DOCX, text) for content extraction and structure.

Every handler here used to return ``{"success": True, "status": "queued"}``
against no queue, no worker and no consumer. The skill is **registered and
reachable** — ``SkillRegistry.discover_builtin_skills()`` finds it by module
scan, so it is routable without any textual reference to grep for — which made
the fabricated success worse than dead code: a live surface reporting work it
never did (#13897).

Extraction now goes through the canonical document extractor
(``media/document/extraction.py``, #13893), so this skill inherits its text-layer
detection and page structure rather than reimplementing either.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import PROJECT_ALLOWED_ROOTS, validate_path
from skills.base_skill import BaseSkill, SkillConfigField, SkillManifest

logger = get_logger(__name__)

# Formats this skill can read, mirroring the canonical extractor's coverage.
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".csv"}


class DocumentAnalysisSkill(BaseSkill):
    """Analyze and extract information from documents."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        """Return document analysis manifest."""
        return SkillManifest(
            name="document-analysis",
            version="2.0.0",
            description="Analyze documents for content extraction and structure",
            author="mrveiss",
            category="analysis",
            dependencies=[],
            config={
                "ocr_enabled": SkillConfigField(
                    type="bool",
                    default=False,
                    description=(
                        "Attempt OCR on documents with no text layer. No OCR backend is "
                        "wired yet (#13896); while that is true, enabling this makes the "
                        "skill report that OCR is required and unavailable rather than "
                        "silently returning an empty extraction."
                    ),
                ),
                "max_pages": SkillConfigField(
                    type="int",
                    default=100,
                    description="Maximum pages to read from a paginated document",
                ),
                "output_format": SkillConfigField(
                    type="string",
                    default="markdown",
                    description="Output format for extracted content",
                    choices=["markdown", "plain", "json"],
                ),
            },
            tools=[
                "analyze_document",
                "extract_text",
                "summarize_document",
            ],
            triggers=["document_uploaded"],
            tags=["document", "pdf", "ocr", "extraction", "analysis"],
        )

    def get_trigger_actions(self) -> Dict[str, str]:
        """Bind the declared trigger to the action that handles it (#14406)."""
        return {"document_uploaded": "analyze_document"}

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute document analysis action."""
        handlers = {
            "analyze_document": self._analyze,
            "extract_text": self._extract_text,
            "summarize_document": self._summarize,
        }
        handler = handlers.get(action)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action}"}
        return await handler(params)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    async def _load(self, params: Dict[str, Any]) -> Tuple[Any, Dict[str, Any] | None]:
        """Read and extract a document, or return the failure to report.

        Returns ``(extracted, None)`` on success and ``(None, error_dict)``
        otherwise. Callers return the error verbatim — no handler may convert a
        failure here into a success.
        """
        from media.document.extraction import DocumentExtractionError, extract_document

        path, error = self._resolve_path(params.get("file_path"))
        if error:
            return None, error

        try:
            raw = await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            logger.warning("Cannot read document %s: %s", path.name, exc)
            return None, {"success": False, "error": f"Cannot read file: {exc}"}

        try:
            extracted = await asyncio.to_thread(extract_document, raw)
        except DocumentExtractionError as exc:
            logger.warning("Extraction failed for %s: %s", path.name, exc)
            return None, {"success": False, "error": str(exc)}

        unreadable = self._unreadable_error(extracted)
        return (None, unreadable) if unreadable else (extracted, None)

    def _resolve_path(self, raw_path: Any) -> Tuple[Path | None, Dict[str, Any] | None]:
        """Validate the requested path before any filesystem access."""
        if not raw_path or not isinstance(raw_path, str):
            return None, {"success": False, "error": "file_path is required"}

        # This skill reads whatever it is handed, so validation happens before
        # the open() rather than after — a rejected path must never have been
        # touched.
        #
        # autobot_shared's validator, not utils.path_validation: a skill may only
        # import autobot_shared (#7372 layer boundary), and this one is stronger
        # anyway. It canonicalizes and then confines the resolved path to the
        # allowed roots, rather than denylisting ".." in the raw string — #14050
        # records why a raw-string denylist is the wrong check.
        try:
            path = validate_path(raw_path, allowed_roots=PROJECT_ALLOWED_ROOTS)
        except ValueError as exc:
            logger.warning("Rejected document path: %s", exc)
            return None, {"success": False, "error": f"Invalid file_path: {exc}"}

        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            return None, {
                "success": False,
                "error": f"Unsupported format '{path.suffix}'. Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}",
            }
        return path, None

    def _unreadable_error(self, extracted: Any) -> Dict[str, Any] | None:
        """Report a document that parsed but yielded nothing usable (#13884)."""
        if extracted.has_usable_content:
            return None

        if self._config.get("ocr_enabled", False):
            reason = "The document has no text layer and OCR is not available yet (#13896)."
        else:
            reason = "The document has no extractable text. It is most likely scanned or image-only."

        return {
            "success": False,
            "error": reason,
            "page_count": extracted.page_count,
            "empty_pages": list(extracted.empty_page_numbers),
        }

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _analyze(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a document's structure and content."""
        extracted, error = await self._load(params)
        if error:
            return error

        return {
            "success": True,
            "file_path": params["file_path"],
            "format": extracted.format,
            "page_count": extracted.page_count,
            "char_count": extracted.char_count,
            "empty_pages": list(extracted.empty_page_numbers),
            "tables": [list(table) for table in extracted.tables],
            "document_info": dict(extracted.info),
        }

    async def _extract_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Extract text content from a document."""
        extracted, error = await self._load(params)
        if error:
            return error

        output_format = self._config.get("output_format", "markdown")
        pages = self._pages_within_limit(extracted)

        return {
            "success": True,
            "file_path": params["file_path"],
            "format": output_format,
            "pages_read": len(pages) if extracted.pages else None,
            "truncated": bool(extracted.pages) and len(pages) < len(extracted.pages),
            **self._render(extracted, pages, output_format),
        }

    def _pages_within_limit(self, extracted: Any) -> Tuple[Any, ...]:
        """Apply ``max_pages``, which previously changed nothing at all."""
        max_pages = self._config.get("max_pages", 100)
        if not extracted.pages or not isinstance(max_pages, int) or max_pages <= 0:
            return extracted.pages
        return extracted.pages[:max_pages]

    def _render(self, extracted: Any, pages: Tuple[Any, ...], output_format: str) -> Dict[str, Any]:
        """Render extracted content in the configured output format."""
        from media.document.extraction import render_pages, strip_page_markers

        if not pages:
            # Unpaginated formats carry their whole body in ``text``.
            body = extracted.text
            return {"content": body} if output_format != "json" else {"content": {"text": body, "pages": []}}

        if output_format == "json":
            return {"content": {"pages": [{"page": p.number, "text": p.text} for p in pages]}}
        if output_format == "plain":
            # Rendered then stripped, rather than joined directly, so the two
            # formats stay identical apart from the markers.
            return {"content": strip_page_markers(render_pages(pages))}
        return {"content": render_pages(pages)}

    async def _summarize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize document content.

        Extraction is real and so is the summary now (#14258): the text goes to
        SummarizationAgent, which builds the prompt and calls
        ``services.llm_service`` — the same backend skill_router already reaches.
        Going through the agent rather than the service directly keeps prompt
        construction (style, length) in one place instead of a second copy here.

        When the backend is unreachable this returns ``success: False`` with the
        extracted text, never a summary that is really just the document. The
        #13897 invariant holds: no handler reports success for work that did not
        happen.
        """
        extracted, error = await self._load(params)
        if error:
            return error

        max_length = params.get("max_length", "medium")
        summary, failure = await self._summarize_text(extracted.text, max_length, params.get("style", "concise"))
        if failure:
            return {
                "success": False,
                "error": failure,
                "file_path": params["file_path"],
                "max_length": max_length,
                "extracted_text": extracted.text,
                "char_count": extracted.char_count,
            }

        return {
            "success": True,
            "file_path": params["file_path"],
            "max_length": max_length,
            "summary": summary,
            "char_count": extracted.char_count,
        }

    async def _summarize_text(self, text: str, max_length: Any, style: str):
        """Return ``(summary, None)`` or ``(None, reason)``.

        The agent is imported at call time and guarded: a skill must not fail to
        load because an optional backend is absent, and the layer waiver below is
        narrower if it is not evaluated at module import.
        """
        try:
            # The published skill surface has no summarizer. skill_router.py
            # reaches services.llm_service the same way; SummarizationAgent sits
            # on top of that identical service, so this is one route to one
            # backend rather than a second path to the same thing (#14258).
            from agents.base_agent import AgentRequest  # nosemgrep: extension-no-core-internals
            from agents.summarization_agent import get_summarization_agent  # nosemgrep: extension-no-core-internals
        except ImportError as exc:
            logger.warning("Summarization backend unavailable: %s", exc)
            return None, f"Summarization backend is unavailable: {exc}"

        request = AgentRequest(
            request_id=f"document-analysis-{uuid.uuid4()}",
            agent_type="summarization",
            action="summarize",
            payload={"text": text, "max_length": max_length, "style": style},
        )

        try:
            result = await get_summarization_agent().handle_summarize(request)
        except Exception as exc:
            logger.warning("Summarization failed: %s", exc)
            return None, f"Summarization failed: {exc}"

        failure = self._agent_failure(result)
        if failure:
            return None, failure

        summary = self._summary_text(result)
        if not summary:
            # A backend that returned nothing is a failure, not an empty summary.
            return None, "The summarization backend returned no text"
        return summary, None

    @staticmethod
    def _agent_failure(result: Any) -> str:
        """Return why *result* is not a successful summary, or ``""`` if it is.

        ``BaseModalityAgent.process_query`` does not re-raise: on any error it
        returns ``{"status": "error", "response": QUERY_ERROR_MESSAGE, ...}``.
        For SummarizationAgent that message is the human-readable string
        "Error generating summary. Please try again." — a perfectly non-empty
        value under a key ``_summary_text`` happily accepts. Reading the text
        without first reading the status therefore reports ``success: True``
        with an error notice presented as the document's summary, which is the
        exact outcome the #13897 invariant exists to prevent.

        So the status is checked first, and an unrecognised shape is a failure
        rather than a fall-through: a result this function cannot classify is
        one it cannot vouch for.
        """
        if not isinstance(result, dict):
            return f"The summarization backend returned an unrecognised result type: {type(result).__name__}"

        status = result.get("status")
        if status is None:
            return "The summarization backend returned no status field"
        if status != "success":
            # `response_text` carries the underlying exception; `response` is
            # the user-facing notice. Prefer the specific one.
            detail = result.get("response_text") or result.get("response") or status
            return f"Summarization failed: {detail}"
        return ""

    @staticmethod
    def _summary_text(result: Any) -> str:
        """Pull the summary out of an agent result already known to be a success.

        Only reached after :meth:`_agent_failure` has cleared the status, so the
        key-priority walk below can no longer pick up an error notice.
        """
        if isinstance(result, dict):
            for key in ("summary", "response", "result", "text", "content"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""
