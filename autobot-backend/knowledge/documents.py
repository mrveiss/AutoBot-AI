# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Documents Management Module

Contains the DocumentsMixin class for document processing, ingestion,
and file operations.
"""

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class DocumentsMixin:
    """
    Document management mixin for knowledge base.

    Provides document operations:
    - Add documents with chunking
    - Process files (PDF, TXT, MD)
    - Directory ingestion
    - Export all data
    - Librarian functionality

    Key Features:
    - Automatic chunking and vectorization
    - Multiple file format support
    - Category extraction
    """

    async def add_document(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        doc_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Add a document to the knowledge base with async processing.

        Args:
            content: Document content
            metadata: Document metadata
            doc_id: Optional document ID

        Returns:
            Result dictionary with status and details
        """
        from utils.knowledge_base_timeouts import kb_timeouts

        if not content.strip():
            return {"status": "error", "message": "Empty content provided"}

        try:
            # Use asyncio.wait_for for timeout protection
            return await asyncio.wait_for(
                self._add_document_internal(content, metadata, doc_id),
                timeout=kb_timeouts.document_add,
            )
        except asyncio.TimeoutError:
            logger.warning("Document addition timed out")
            return {"status": "timeout", "message": "Document addition timed out"}
        except Exception as e:
            logger.error("Document addition failed: %s", e)
            return {"status": "error", "message": "Document operation failed"}

    async def _add_document_internal(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        doc_id: str | None = None,
    ) -> Dict[str, Any]:
        """Internal document addition implementation.

        Issue #1252: Ensures provenance source_type defaults to 'manual_upload'
        for documents added via this path unless caller already specified it.
        """
        if metadata is None:
            metadata = {}
        metadata.setdefault("source_type", "manual_upload")
        metadata.setdefault("verification_status", "unverified")
        return await self.store_fact(content, metadata, doc_id)

    async def export_all_data(self, output_dir: str = "data/exports") -> Dict[str, Any]:
        """
        Export all knowledge base data to JSON files.

        Args:
            output_dir: Directory to save exports

        Returns:
            Dict with export status and file paths
        """
        try:
            output_path = Path(output_dir)
            # Issue #358 - avoid blocking
            await asyncio.to_thread(output_path.mkdir, parents=True, exist_ok=True)

            # Export facts
            facts = await self.get_all_facts()
            facts_file = output_path / "facts.json"
            await asyncio.to_thread(
                facts_file.write_text,
                json.dumps(facts, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            return {
                "status": "success",
                "facts_exported": len(facts),
                "facts_file": str(facts_file),
            }

        except Exception as e:
            logger.error("Export failed: %s", e)
            return {"status": "error", "message": "Document operation failed"}

    def extract_category_names(self, facts: List[Dict[str, Any]]) -> List[str]:
        """Extract unique category names from facts"""
        categories = set()
        for fact in facts:
            metadata = fact.get("metadata", {})
            if "category" in metadata:
                categories.add(metadata["category"])
        return sorted(list(categories))

    async def add_document_from_file(
        self, file_path: str, category: str = "general", metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Add a document from a file.

        #14333: this used to claim PDF support in its docstring and then call
        ``read_text(encoding="utf-8")``, which reads a PDF as UTF-8 — raising on
        the binary header or, worse, storing mojibake. Extraction now goes
        through DocumentExtractor, so the advertised formats are the handled
        ones: PDF, DOC/DOCX, plain text, and the spreadsheet / presentation /
        OpenDocument set it delegates to DocumentParser.

        Args:
            file_path: Path to the file
            category: Document category
            metadata: Additional metadata

        Returns:
            Dict with status
        """
        try:
            file_path_obj = Path(file_path)
            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(file_path_obj.exists):
                return {"status": "error", "message": "File not found"}

            content = await self._extract_file_text(file_path_obj)
            if content is None:
                return {"status": "error", "message": f"Unsupported file type: {file_path_obj.suffix}"}
            if not content.strip():
                # A file that parsed cleanly and yielded nothing is the scanned-PDF
                # shape (#13884); storing it would be a silently empty document.
                return {"status": "error", "message": "No extractable text content"}

            # Prepare metadata
            if metadata is None:
                metadata = {}
            metadata["category"] = category
            metadata["source_file"] = str(file_path)
            metadata["filename"] = file_path_obj.name

            # Store document
            result = await self.add_document(content, metadata)

            return result

        except Exception as e:
            logger.error("Failed to add document from file %s: %s", file_path, e)
            return {"status": "error", "message": "Document operation failed"}

    async def _discover_documents(self, dir_path: Path, pattern: str | None) -> List[Path]:
        """List the files in *dir_path* worth attempting.

        Without an explicit pattern this uses DocumentExtractor's own notion of
        what it supports, so discovery and extraction cannot disagree — a
        discovery pass that skips a handled format is a silently smaller ingest
        that reports success.
        """
        from utils.document_extractors import DocumentExtractor

        if pattern:
            return await asyncio.to_thread(lambda: list(dir_path.glob(pattern)))

        def _scan() -> List[Path]:
            return [
                path
                for path in sorted(dir_path.glob("*"))
                if path.is_file() and DocumentExtractor.is_supported_format(path)
            ]

        return await asyncio.to_thread(_scan)

    async def _extract_file_text(self, file_path: Path) -> str | None:
        """Extract text for any supported format, or None if unsupported.

        Single entry point on purpose — the batch path had its own
        ``read_text`` while five other extractors existed elsewhere (#13893).
        """
        from utils.document_extractors import DocumentExtractor

        if not DocumentExtractor.is_supported_format(file_path):
            return None
        try:
            return await DocumentExtractor.extract_from_file(file_path)
        except (ValueError, FileNotFoundError) as exc:
            logger.warning("Extraction failed for %s: %s", file_path.name, exc)
            return None

    async def _validate_directory(self, dir_path: str) -> Path | None:
        """Validate directory exists and is accessible (Issue #398: extracted)."""
        dir_path_obj = Path(dir_path)
        exists = await asyncio.to_thread(dir_path_obj.exists)
        is_dir = await asyncio.to_thread(dir_path_obj.is_dir) if exists else False
        return dir_path_obj if exists and is_dir else None

    async def _process_file_with_semaphore(
        self, semaphore: asyncio.Semaphore, file_path: Path, category: str
    ) -> Dict[str, Any]:
        """Process single file with semaphore-controlled concurrency (Issue #398: extracted)."""
        async with semaphore:
            try:
                return await self.add_document_from_file(str(file_path), category=category)
            except Exception:
                return {"status": "error", "message": "Document operation failed"}

    def _count_results(self, results: List[Any]) -> tuple:
        """Count success and error results (Issue #398: extracted)."""
        success_count = 0
        error_count = 0
        for result in results:
            if isinstance(result, Exception):
                error_count += 1
            elif result.get("status") == "success":
                success_count += 1
            else:
                error_count += 1
        return success_count, error_count

    async def add_documents_from_directory(
        self, dir_path: str, category: str = "general", pattern: str | None = None
    ) -> Dict[str, Any]:
        """Add documents from a directory (Issue #398: refactored).

        #14333: ``pattern`` defaulted to ``"*.txt"``, so a directory of PDFs
        ingested nothing and reported ``total_files: 0`` — a successful-looking
        no-op. With no pattern the discovery set is now every format
        DocumentExtractor can actually handle. An explicit pattern still wins,
        for callers that mean to narrow it.
        """
        try:
            dir_path_obj = await self._validate_directory(dir_path)
            if not dir_path_obj:
                return {"status": "error", "message": "Directory not found"}

            files = await self._discover_documents(dir_path_obj, pattern)
            logger.info("Found %d ingestible file(s) in %s", len(files), dir_path_obj.name)

            semaphore = asyncio.Semaphore(10)
            results = await asyncio.gather(
                *[self._process_file_with_semaphore(semaphore, f, category) for f in files], return_exceptions=True
            )

            success_count, error_count = self._count_results(results)
            return {
                "status": "success",
                "total_files": len(files),
                "success_count": success_count,
                "error_count": error_count,
            }

        except Exception as e:
            logger.error("Failed to add documents from directory %s: %s", dir_path, e)
            return {"status": "error", "message": "Document operation failed"}

    async def get_librarian(self) -> Dict[str, Any]:
        """
        Get librarian stats and information.

        Returns:
            Dict with librarian information
        """
        try:
            stats = await self.get_stats()
            return {
                "status": "online",
                "total_facts": stats.get("total_facts", 0),
                "total_documents": stats.get("total_documents", 0),
                "categories": stats.get("categories", []),
            }
        except Exception as e:
            logger.error("Failed to get librarian info: %s", e)
            return {"status": "error", "message": "Document operation failed"}

    # Method references needed from other mixins
    async def store_fact(self, content: str, metadata: Dict[str, Any], fact_id: str):
        """Store fact - implemented in facts mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def get_all_facts(self):
        """Get all facts - implemented in facts mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def get_stats(self):
        """Get stats - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")
