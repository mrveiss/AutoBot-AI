# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Reusable Document Text Extraction Utilities

Provides async text extraction from various document formats:
- PDF files (pypdf)
- DOCX files (python-docx)
- Plain text files (TXT, MD, RST)
- Batch directory processing
- NumPy data type JSON encoding

This module is designed to be reusable by ANY component in the codebase,
not locked to the knowledge base.

Usage:
    from utils.document_extractors import DocumentExtractor

    # Extract from single file
    text = await DocumentExtractor.extract_from_pdf(Path("document.pdf"))

    # Extract from directory
    results = await DocumentExtractor.extract_from_directory(
        Path("docs/"),
        file_types=['.pdf', '.docx', '.md']
    )
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

import aiofiles
import numpy as np
from docx import Document as DocxDocument
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Module-level constants for O(1) lookups (Issue #326)
DOCX_EXTENSIONS = {".docx", ".doc"}

# Issue #380: Module-level tuple for numpy numeric type checks
_NUMPY_NUMERIC_TYPES = (np.integer, np.floating)


class NumpyJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles NumPy data types

    Converts NumPy types to native Python types for JSON serialization:
    - np.integer → int
    - np.floating → float
    - np.ndarray → list
    - Objects with __float__ → float
    - Objects with __int__ → int

    Usage:
        data = {"array": np.array([1, 2, 3]), "value": np.float64(3.14)}
        json.dumps(data, cls=NumpyJSONEncoder)
    """

    def default(self, obj):
        """Convert NumPy types to JSON-serializable Python types."""
        if isinstance(obj, _NUMPY_NUMERIC_TYPES):  # Issue #380
            return obj.item()
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif hasattr(obj, "__float__"):
            return float(obj)
        elif hasattr(obj, "__int__"):
            return int(obj)
        return super().default(obj)


class DocumentExtractor:
    """
    Reusable document text extraction utility

    Provides static async methods for extracting text from various document formats.
    All methods are async to avoid blocking the event loop during I/O operations.
    """

    # Supported file types by category
    SUPPORTED_FORMATS = {
        "pdf": [".pdf"],
        "docx": [".docx", ".doc"],
        "text": [".txt", ".md", ".rst", ".markdown", ".text"],
    }

    @staticmethod
    async def extract_from_pdf(file_path: Union[str, Path]) -> str:
        """
        Extract text from PDF file using pypdf

        Args:
            file_path: Path to PDF file

        Returns:
            Extracted text with pages separated by double newlines

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a valid PDF

        Example:
            text = await DocumentExtractor.extract_from_pdf("report.pdf")
        """
        file_path = Path(file_path)

        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(file_path.exists):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        if file_path.suffix.lower() != ".pdf":
            raise ValueError(f"File is not a PDF: {file_path}")

        def extract_sync():
            """Synchronous PDF extraction wrapped for async execution"""
            try:
                reader = PdfReader(file_path)
                pages = []

                for page_num, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            pages.append(text)
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract page {page_num} from {file_path.name}: {e}"
                        )
                        continue

                return "\n\n".join(pages)
            except Exception as e:
                logger.error("Failed to read PDF %s: %s", file_path, e)
                raise ValueError(f"Invalid or corrupted PDF file: {file_path}") from e

        # Run sync operation in thread pool to avoid blocking
        return await asyncio.to_thread(extract_sync)

    @staticmethod
    async def extract_from_docx(file_path: Union[str, Path]) -> str:
        """
        Extract text from DOCX file using python-docx

        Args:
            file_path: Path to DOCX file

        Returns:
            Extracted text with paragraphs separated by double newlines

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a valid DOCX

        Example:
            text = await DocumentExtractor.extract_from_docx("document.docx")
        """
        file_path = Path(file_path)

        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(file_path.exists):
            raise FileNotFoundError(f"DOCX file not found: {file_path}")

        if file_path.suffix.lower() not in DOCX_EXTENSIONS:  # O(1) lookup (Issue #326)
            raise ValueError(f"File is not a DOCX: {file_path}")

        def extract_sync():
            """Synchronous DOCX extraction wrapped for async execution"""
            try:
                doc = DocxDocument(file_path)
                paragraphs = []

                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text:
                        paragraphs.append(text)

                return "\n\n".join(paragraphs)
            except Exception as e:
                logger.error("Failed to read DOCX %s: %s", file_path, e)
                raise ValueError(f"Invalid or corrupted DOCX file: {file_path}") from e

        # Run sync operation in thread pool to avoid blocking
        return await asyncio.to_thread(extract_sync)

    @staticmethod
    async def extract_from_text(
        file_path: Union[str, Path], encoding: str = "utf-8"
    ) -> str:
        """
        Extract text from plain text file with proper UTF-8 encoding

        Args:
            file_path: Path to text file
            encoding: Text encoding (default: utf-8)

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If encoding doesn't match file

        Example:
            text = await DocumentExtractor.extract_from_text("readme.md")
        """
        file_path = Path(file_path)

        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(file_path.exists):
            raise FileNotFoundError(f"Text file not found: {file_path}")

        try:
            async with aiofiles.open(file_path, "r", encoding=encoding) as f:
                return await f.read()
        except UnicodeDecodeError as e:
            logger.error("Encoding error reading %s with %s: %s", file_path, encoding, e)
            raise
        except OSError as e:
            logger.error("Failed to read text file %s: %s", file_path, e)
            raise
        except Exception as e:
            logger.error("Unexpected error reading text file %s: %s", file_path, e)
            raise

    @staticmethod
    async def extract_from_file(file_path: Union[str, Path]) -> str:
        """
        Route to appropriate extraction method based on file extension

        Automatically detects file type and uses the correct extraction method.

        Supported formats:
        - .pdf: PDF documents
        - .docx, .doc: Microsoft Word documents
        - .txt, .md, .rst, .markdown, .text: Plain text/Markdown/reStructuredText

        Args:
            file_path: Path to file

        Returns:
            Extracted text

        Raises:
            ValueError: If file type is not supported
            FileNotFoundError: If file doesn't exist

        Example:
            # Automatically detects file type
            text = await DocumentExtractor.extract_from_file("document.pdf")
            text = await DocumentExtractor.extract_from_file("notes.md")
        """
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        # Route based on file extension
        if suffix in DocumentExtractor.SUPPORTED_FORMATS["pdf"]:
            return await DocumentExtractor.extract_from_pdf(file_path)
        elif suffix in DocumentExtractor.SUPPORTED_FORMATS["docx"]:
            return await DocumentExtractor.extract_from_docx(file_path)
        elif suffix in DocumentExtractor.SUPPORTED_FORMATS["text"]:
            return await DocumentExtractor.extract_from_text(file_path)
        else:
            raise ValueError(
                f"Unsupported file type: {suffix}. "
                f"Supported formats: {DocumentExtractor.get_supported_extensions()}"
            )

    @staticmethod
    async def _validate_directory(directory_path: Path) -> None:
        """Validate directory exists and is a directory (Issue #281 - extracted helper)."""
        if not await asyncio.to_thread(directory_path.exists):
            raise FileNotFoundError(f"Directory not found: {directory_path}")
        if not await asyncio.to_thread(directory_path.is_dir):
            raise NotADirectoryError(f"Path is not a directory: {directory_path}")

    @staticmethod
    def _collect_files_sync(
        directory_path: Path,
        file_types: List[str],
        glob_pattern: str,
        max_files: Optional[int],
    ) -> List[Path]:
        """Sync helper for collecting files (Issue #281 - extracted helper)."""
        result_files = []
        for ft in file_types:
            if not ft.startswith("."):
                ft = f".{ft}"

            for fp in directory_path.glob(f"{glob_pattern}{ft}"):
                if fp.is_file():
                    result_files.append(fp)
                    if max_files and len(result_files) >= max_files:
                        break

            if max_files and len(result_files) >= max_files:
                break
        return result_files

    @staticmethod
    async def _extract_single_file(file_path: Path) -> tuple:
        """Extract text from single file with error handling (Issue #281 - extracted helper)."""
        try:
            text = await DocumentExtractor.extract_from_file(file_path)
            logger.info("✅ Extracted %s chars from %s", len(text), file_path.name)
            return (file_path, text)
        except Exception as e:
            logger.error("❌ Failed to extract from %s: %s", file_path, e)
            return (file_path, None)

    @staticmethod
    async def extract_from_directory(
        directory_path: Union[str, Path],
        file_types: Optional[List[str]] = None,
        recursive: bool = True,
        max_files: Optional[int] = None,
    ) -> Dict[Path, str]:
        """
        Extract text from all supported documents in a directory.

        Issue #281: Refactored from 110 lines to use extracted helper methods.

        Args:
            directory_path: Path to directory to process
            file_types: List of file extensions to process (default: all supported)
            recursive: Process subdirectories recursively (default: True)
            max_files: Maximum number of files to process (default: unlimited)

        Returns:
            Dict mapping file paths to extracted text

        Raises:
            FileNotFoundError: If directory doesn't exist
            NotADirectoryError: If path is not a directory
        """
        directory_path = Path(directory_path)
        await DocumentExtractor._validate_directory(directory_path)

        if file_types is None:
            file_types = DocumentExtractor.get_supported_extensions()

        glob_pattern = "**/*" if recursive else "*"
        all_files = await asyncio.to_thread(
            DocumentExtractor._collect_files_sync,
            directory_path, file_types, glob_pattern, max_files
        )

        logger.info("Found %s files to process in %s", len(all_files), directory_path)

        # Process all files concurrently
        tasks = [DocumentExtractor._extract_single_file(fp) for fp in all_files]
        results = await asyncio.gather(*tasks)

        # Build result dict (exclude failures)
        extracted_texts = {fp: text for fp, text in results if text is not None}

        logger.info(
            f"Successfully extracted {len(extracted_texts)}/{len(all_files)} files "
            f"from {directory_path}"
        )

        return extracted_texts

    @staticmethod
    def get_supported_extensions() -> List[str]:
        """
        Get list of all supported file extensions

        Returns:
            List of file extensions (e.g., ['.pdf', '.docx', '.txt'])

        Example:
            extensions = DocumentExtractor.get_supported_extensions()
            # ['.pdf', '.docx', '.doc', '.txt', '.md', '.rst', '.markdown', '.text']
        """
        all_extensions = []
        for extensions in DocumentExtractor.SUPPORTED_FORMATS.values():
            all_extensions.extend(extensions)
        return all_extensions

    @staticmethod
    def is_supported_format(file_path: Union[str, Path]) -> bool:
        """
        Check if file format is supported

        Args:
            file_path: Path to file

        Returns:
            True if file format is supported, False otherwise

        Example:
            if DocumentExtractor.is_supported_format("report.pdf"):
                text = await DocumentExtractor.extract_from_file("report.pdf")
        """
        suffix = Path(file_path).suffix.lower()
        return suffix in DocumentExtractor.get_supported_extensions()


# Convenience functions for backward compatibility
async def extract_pdf_text(file_path: Union[str, Path]) -> str:
    """Convenience function for PDF extraction"""
    return await DocumentExtractor.extract_from_pdf(file_path)


async def extract_docx_text(file_path: Union[str, Path]) -> str:
    """Convenience function for DOCX extraction"""
    return await DocumentExtractor.extract_from_docx(file_path)


async def extract_text_file(file_path: Union[str, Path]) -> str:
    """Convenience function for text file extraction"""
    return await DocumentExtractor.extract_from_text(file_path)
