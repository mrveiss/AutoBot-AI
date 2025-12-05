# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Documents Management Module

Contains the DocumentsMixin class for document processing, ingestion,
and file operations.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
        doc_id: Optional[str] = None,
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
        from src.utils.knowledge_base_timeouts import kb_timeouts

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
            logger.error(f"Document addition failed: {e}")
            return {"status": "error", "message": str(e)}

    async def _add_document_internal(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Internal document addition implementation"""
        # This delegates to store_fact for simplicity
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
            output_path.mkdir(parents=True, exist_ok=True)

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
            logger.error(f"Export failed: {e}")
            return {"status": "error", "message": str(e)}

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
        Add a document from a file (supports TXT, MD, PDF, etc).

        Args:
            file_path: Path to the file
            category: Document category
            metadata: Additional metadata

        Returns:
            Dict with status
        """
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                return {"status": "error", "message": "File not found"}

            # Read file content
            content = await asyncio.to_thread(
                file_path_obj.read_text, encoding="utf-8"
            )

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
            logger.error(f"Failed to add document from file {file_path}: {e}")
            return {"status": "error", "message": str(e)}

    async def add_documents_from_directory(
        self, dir_path: str, category: str = "general", pattern: str = "*.txt"
    ) -> Dict[str, Any]:
        """
        Add all documents from a directory matching pattern.

        Args:
            dir_path: Directory path
            category: Category for documents
            pattern: File pattern (e.g., "*.txt", "*.md")

        Returns:
            Dict with status and counts
        """
        try:
            dir_path_obj = Path(dir_path)
            if not dir_path_obj.exists() or not dir_path_obj.is_dir():
                return {"status": "error", "message": "Directory not found"}

            # Find matching files
            files = list(dir_path_obj.glob(pattern))
            logger.info(f"Found {len(files)} files matching pattern '{pattern}'")

            # Process files in parallel with bounded concurrency
            semaphore = asyncio.Semaphore(10)  # Limit concurrent file operations

            async def process_file(file_path: Path) -> Dict[str, Any]:
                async with semaphore:
                    try:
                        return await self.add_document_from_file(
                            str(file_path), category=category
                        )
                    except Exception as e:
                        return {"status": "error", "message": str(e)}

            # Process all files in parallel
            results = await asyncio.gather(
                *[process_file(file_path) for file_path in files],
                return_exceptions=True
            )

            # Count results
            success_count = 0
            error_count = 0
            for result in results:
                if isinstance(result, Exception):
                    error_count += 1
                elif result.get("status") == "success":
                    success_count += 1
                else:
                    error_count += 1

            return {
                "status": "success",
                "total_files": len(files),
                "success_count": success_count,
                "error_count": error_count,
            }

        except Exception as e:
            logger.error(f"Failed to add documents from directory {dir_path}: {e}")
            return {"status": "error", "message": str(e)}

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
            logger.error(f"Failed to get librarian info: {e}")
            return {"status": "error", "message": str(e)}

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
