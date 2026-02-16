# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Codebase Indexing Service

This service provides comprehensive codebase indexing capabilities for the AutoBot Knowledge Manager.
It scans the entire AutoBot project, processes different file types, creates intelligent chunks,
and stores them in the knowledge base with proper metadata and categorization.

Features:
- Multi-file type support (Python, Vue, Markdown, Config, etc.)
- Intelligent code-aware chunking
- Automatic categorization and metadata enrichment
- Progress tracking and batch processing
- Integration with existing knowledge base infrastructure
- Configurable scanning and filtering
"""

import asyncio
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from backend.constants.path_constants import PATH
from backend.constants.threshold_constants import TimingConstants
from knowledge_base_factory import get_knowledge_base

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for file type and metadata filtering (Issue #326)
JAVASCRIPT_LANGUAGE_TYPES = {"javascript", "typescript"}
EXCLUDED_CHUNK_METADATA_KEYS = {"content"}

# Issue #380: Module-level tuple for code definition prefixes
_CODE_DEF_PREFIXES = ("def ", "class ", "async def ")

# Issue #380: Pre-compiled regex patterns for Vue and code chunking
_VUE_TEMPLATE_RE = re.compile(r"<template[^>]*>(.*?)</template>", re.DOTALL)
_VUE_SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.DOTALL)
_VUE_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL)
_JS_FUNCTION_RE = re.compile(r"^\s*(function|const|let|var|export|async)")
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)")


@dataclass
class IndexingProgress:
    """Track indexing progress and statistics"""

    total_files: int = 0
    processed_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    total_chunks: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    current_file: str = ""
    current_category: str = ""
    errors: List[str] = None

    def __post_init__(self):
        """Initialize errors list if not provided."""
        if self.errors is None:
            self.errors = []

    @property
    def progress_percentage(self) -> float:
        """Calculate progress as percentage of files processed."""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100

    @property
    def is_complete(self) -> bool:
        """Check if indexing has completed all files."""
        return self.processed_files >= self.total_files and self.total_files > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert progress to dictionary with computed properties."""
        return {
            **asdict(self),
            "progress_percentage": self.progress_percentage,
            "is_complete": self.is_complete,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


@dataclass
class FileInfo:
    """Information about a file to be indexed"""

    path: Path
    relative_path: str
    file_type: str
    category: str
    language: str
    size: int
    modified_time: datetime


class CodeChunker:
    """Intelligent code-aware chunking for different file types"""

    def __init__(self, max_chunk_size: int = 2000, overlap_size: int = 200):
        """Initialize code chunker with configurable size limits and overlap."""
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size

    def _create_chunk_dict(
        self,
        lines: List[str],
        chunk_type: str,
        start_line: int,
        end_line: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a chunk dictionary from lines if content is not empty.

        Issue #281: Extracted from chunk_python_file to reduce repetition.

        Args:
            lines: List of code lines to join as content
            chunk_type: Type of chunk (general, function, class)
            start_line: Starting line number (1-based)
            end_line: Ending line number (1-based)

        Returns:
            Chunk dictionary or None if content is empty
        """
        chunk_content = "\n".join(lines)
        if not chunk_content.strip():
            return None

        return {
            "content": chunk_content,
            "type": chunk_type,
            "start_line": start_line,
            "end_line": end_line,
        }

    def _append_chunk_if_valid(
        self,
        chunks: List[Dict[str, Any]],
        lines_list: List[str],
        chunk_type: str,
        start_line: int,
        end_line: int,
    ) -> None:
        """
        Create and append chunk to list if valid.

        Issue #665: Extracted from chunk_python_file to reduce function length.

        Args:
            chunks: List to append chunk to
            lines_list: Lines to create chunk from
            chunk_type: Type of chunk
            start_line: Starting line number
            end_line: Ending line number
        """
        chunk = self._create_chunk_dict(lines_list, chunk_type, start_line, end_line)
        if chunk:
            chunks.append(chunk)

    def _collect_definition_block(
        self, lines: List[str], start_idx: int, base_indent: int
    ) -> tuple[List[str], int]:
        """
        Collect all lines belonging to a function/class definition.

        Issue #665: Extracted from chunk_python_file to reduce function length.

        Args:
            lines: All file lines
            start_idx: Index after the definition line
            base_indent: Indentation level of the definition

        Returns:
            Tuple of (collected lines, next index to process)
        """
        collected = []
        i = start_idx
        while i < len(lines):
            next_line = lines[i]
            next_indent = (
                len(next_line) - len(next_line.lstrip())
                if next_line.strip()
                else base_indent + 1
            )
            # Continue if still inside the block or blank line
            if not next_line.strip() or next_indent > base_indent:
                collected.append(next_line)
                i += 1
            else:
                break
        return collected, i

    def _process_definition_line(
        self,
        lines: List[str],
        line: str,
        stripped_line: str,
        i: int,
        chunks: List[Dict[str, Any]],
        current_chunk: List[str],
        current_chunk_type: str,
    ) -> tuple[int, List[str], str]:
        """
        Process a function/class definition line and collect its block.

        Issue #620.
        """
        # Save previous chunk if it exists
        if current_chunk:
            self._append_chunk_if_valid(
                chunks, current_chunk, current_chunk_type, i - len(current_chunk) + 1, i
            )

        # Determine chunk type and collect definition block
        chunk_type = "function" if "def " in stripped_line else "class"
        current_indent = len(line) - len(line.lstrip())
        block_lines, new_i = self._collect_definition_block(
            lines, i + 1, current_indent
        )
        full_block = [line] + block_lines

        # Save the function/class chunk
        self._append_chunk_if_valid(
            chunks, full_block, chunk_type, new_i - len(full_block), new_i - 1
        )
        return new_i, [], "general"

    def chunk_python_file(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Chunk Python files by functions, classes, and logical blocks.

        Issue #620: Refactored to use _process_definition_line helper.
        """
        chunks = []
        lines = content.split("\n")
        current_chunk = []
        current_chunk_type = "general"
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped_line = line.strip()

            if stripped_line.startswith(_CODE_DEF_PREFIXES):
                i, current_chunk, current_chunk_type = self._process_definition_line(
                    lines,
                    line,
                    stripped_line,
                    i,
                    chunks,
                    current_chunk,
                    current_chunk_type,
                )
                continue

            current_chunk.append(line)
            i += 1

            if len("\n".join(current_chunk)) > self.max_chunk_size:
                self._append_chunk_if_valid(
                    chunks,
                    current_chunk,
                    current_chunk_type,
                    i - len(current_chunk) + 1,
                    i,
                )
                current_chunk = []

        if current_chunk:
            self._append_chunk_if_valid(
                chunks,
                current_chunk,
                current_chunk_type,
                len(lines) - len(current_chunk) + 1,
                len(lines),
            )

        return chunks

    def _add_vue_script_chunks(
        self, chunks: List[Dict[str, Any]], script_content: str
    ) -> None:
        """
        Add script section chunks to the Vue file chunks list.

        Issue #620.
        """
        if len(script_content) > self.max_chunk_size:
            script_chunks = self.chunk_javascript_content(script_content)
            for i, chunk in enumerate(script_chunks):
                chunks.append(
                    {
                        "content": f"<script>\n{chunk['content']}\n</script>",
                        "type": "script",
                        "section": f"script_part_{i+1}",
                        "script_type": chunk.get("type", "general"),
                    }
                )
        else:
            chunks.append(
                {
                    "content": f"<script>\n{script_content}\n</script>",
                    "type": "script",
                    "section": "script",
                }
            )

    def chunk_vue_file(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Chunk Vue files by template, script, and style sections."""
        chunks = []
        template_match = _VUE_TEMPLATE_RE.search(content)
        script_match = _VUE_SCRIPT_RE.search(content)
        style_match = _VUE_STYLE_RE.search(content)

        if template_match:
            template_content = template_match.group(1).strip()
            if template_content:
                chunks.append(
                    {
                        "content": f"<template>\n{template_content}\n</template>",
                        "type": "template",
                        "section": "template",
                    }
                )

        if script_match:
            script_content = script_match.group(1).strip()
            if script_content:
                self._add_vue_script_chunks(chunks, script_content)

        if style_match:
            style_content = style_match.group(1).strip()
            if style_content:
                chunks.append(
                    {
                        "content": f"<style>\n{style_content}\n</style>",
                        "type": "style",
                        "section": "style",
                    }
                )

        return (
            chunks
            if chunks
            else [{"content": content, "type": "vue_file", "section": "complete"}]
        )

    def chunk_javascript_content(self, content: str) -> List[Dict[str, Any]]:
        """Chunk JavaScript content by functions and logical blocks"""
        chunks = []
        lines = content.split("\n")
        current_chunk = []

        i = 0
        while i < len(lines):
            line = lines[i]
            current_chunk.append(line)

            # Check for function definitions using pre-compiled pattern (Issue #380)
            if _JS_FUNCTION_RE.match(line):
                # Look for the complete function
                brace_count = line.count("{") - line.count("}")
                i += 1

                while i < len(lines) and brace_count > 0:
                    next_line = lines[i]
                    current_chunk.append(next_line)
                    brace_count += next_line.count("{") - next_line.count("}")
                    i += 1

                # Save the function chunk
                chunk_content = "\n".join(current_chunk)
                if chunk_content.strip():
                    chunks.append({"content": chunk_content, "type": "function"})
                current_chunk = []
                continue

            # Check if chunk is getting too large
            if len("\n".join(current_chunk)) > self.max_chunk_size:
                chunk_content = "\n".join(current_chunk)
                if chunk_content.strip():
                    chunks.append({"content": chunk_content, "type": "general"})
                current_chunk = []

            i += 1

        # Save final chunk
        if current_chunk:
            chunk_content = "\n".join(current_chunk)
            if chunk_content.strip():
                chunks.append({"content": chunk_content, "type": "general"})

        return chunks if chunks else [{"content": content, "type": "general"}]

    def _append_md_section_chunk(
        self, chunks: List[Dict[str, Any]], lines: List[str], heading: str, level: int
    ) -> None:
        """
        Append a markdown section chunk if content is non-empty.

        Issue #620.
        """
        chunk_content = "\n".join(lines)
        if chunk_content.strip():
            chunks.append(
                {
                    "content": chunk_content,
                    "type": "section",
                    "heading": heading,
                    "level": level,
                }
            )

    def chunk_markdown_file(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Chunk Markdown files by headings and sections."""
        chunks = []
        lines = content.split("\n")
        current_chunk = []
        current_heading = ""
        current_level = 0

        for line in lines:
            heading_match = _MD_HEADING_RE.match(line)

            if heading_match:
                if current_chunk:
                    self._append_md_section_chunk(
                        chunks, current_chunk, current_heading, current_level
                    )
                current_level = len(heading_match.group(1))
                current_heading = heading_match.group(2)
                current_chunk = [line]
            else:
                current_chunk.append(line)
                if len("\n".join(current_chunk)) > self.max_chunk_size:
                    self._append_md_section_chunk(
                        chunks, current_chunk, current_heading, current_level
                    )
                    current_chunk = []

        if current_chunk:
            self._append_md_section_chunk(
                chunks, current_chunk, current_heading, current_level
            )

        return chunks if chunks else [{"content": content, "type": "document"}]

    def chunk_generic_file(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Generic chunking for other file types"""
        if len(content) <= self.max_chunk_size:
            return [{"content": content, "type": "complete_file"}]

        chunks = []
        lines = content.split("\n")
        current_chunk = []

        for line in lines:
            current_chunk.append(line)

            if len("\n".join(current_chunk)) > self.max_chunk_size:
                # Try to find a good break point
                chunk_content = "\n".join(current_chunk[:-1])  # Exclude the last line
                if chunk_content.strip():
                    chunks.append({"content": chunk_content, "type": "text_chunk"})
                current_chunk = [line]  # Start new chunk with the current line

        # Save final chunk
        if current_chunk:
            chunk_content = "\n".join(current_chunk)
            if chunk_content.strip():
                chunks.append({"content": chunk_content, "type": "text_chunk"})

        return chunks if chunks else [{"content": content, "type": "text_chunk"}]


class CodebaseIndexingService:
    """Main service for comprehensive codebase indexing"""

    def _get_include_patterns(self) -> set:
        """
        Return file patterns to include in indexing.

        Issue #620.
        """
        return {
            "*.py",
            "*.vue",
            "*.js",
            "*.ts",
            "*.md",
            "*.yaml",
            "*.yml",
            "*.json",
            "*.txt",
            "*.rst",
            "*.css",
            "*.scss",
            "*.html",
            "*.sh",
            "*.bash",
            "*.dockerfile",
            "Dockerfile*",
            "*.env*",
        }

    def _get_exclude_patterns(self) -> set:
        """
        Return file patterns to exclude from indexing.

        Issue #620.
        """
        return {
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".git",
            ".gitignore",
            "node_modules",
            ".npm",
            ".vscode",
            ".idea",
            "*.log",
            "dist",
            "build",
            ".next",
            ".nuxt",
            "coverage",
            "*.min.js",
            "*.min.css",
            "*.map",
        }

    def _get_exclude_dirs(self) -> set:
        """
        Return directory names to exclude from indexing.

        Issue #620.
        """
        return {
            ".git",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            "venv",
            ".venv",
            "env",
            ".env",
            "dist",
            "build",
            ".next",
            ".nuxt",
            "coverage",
            "logs",
            ".logs",
        }

    def _get_category_mapping(self) -> Dict[str, List[str]]:
        """
        Return mapping of categories to path patterns.

        Issue #620.
        """
        return {
            "backend": ["backend/", "src/", "api/", "services/", "models/", "utils/"],
            "frontend": ["autobot-vue/", "frontend/", "static/", "public/"],
            "docs": ["docs/", "documentation/", "README", "CHANGELOG", ".md"],
            "config": ["config/", "settings/", ".env", ".yaml", ".yml", ".json"],
            "scripts": ["scripts/", "bin/", ".sh", ".bash"],
            "tests": ["tests/", "test_", "_test.py", "spec/", "__tests__/"],
            "docker": ["docker/", "Dockerfile", "docker-compose", ".dockerfile"],
            "infrastructure": ["ansible/", "terraform/", "k8s/", "kubernetes/"],
        }

    def __init__(self, root_path: str = str(PATH.PROJECT_ROOT)):
        """Initialize codebase indexing service with root path and file patterns."""
        self.root_path = Path(root_path)
        self.chunker = CodeChunker()
        self.progress = IndexingProgress()
        self.include_patterns = self._get_include_patterns()
        self.exclude_patterns = self._get_exclude_patterns()
        self.exclude_dirs = self._get_exclude_dirs()
        self.category_mapping = self._get_category_mapping()

    def _should_include_file(self, file_path: Path) -> bool:
        """Check if a file should be included in indexing"""
        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if file_path.match(pattern):
                return False

        # Check if in excluded directory
        for part in file_path.parts:
            if part in self.exclude_dirs:
                return False

        # Check include patterns
        for pattern in self.include_patterns:
            if file_path.match(pattern):
                return True

        return False

    def _get_file_category(self, relative_path: str) -> str:
        """Determine the category of a file based on its path"""
        path_lower = relative_path.lower()

        for category, patterns in self.category_mapping.items():
            for pattern in patterns:
                if pattern in path_lower:
                    return category

        return "general"

    def _get_file_language(self, file_path: Path) -> str:
        """Determine the programming language of a file"""
        extension = file_path.suffix.lower()

        language_map = {
            ".py": "python",
            ".vue": "vue",
            ".js": "javascript",
            ".ts": "typescript",
            ".md": "markdown",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".css": "css",
            ".scss": "scss",
            ".html": "html",
            ".sh": "bash",
            ".bash": "bash",
            ".dockerfile": "dockerfile",
            ".txt": "text",
            ".rst": "restructuredtext",
        }

        return language_map.get(extension, "text")

    def _scan_files(self) -> List[FileInfo]:
        """Scan the codebase and collect file information"""
        files = []

        for file_path in self.root_path.rglob("*"):
            if file_path.is_file() and self._should_include_file(file_path):
                try:
                    relative_path = str(file_path.relative_to(self.root_path))
                    file_info = FileInfo(
                        path=file_path,
                        relative_path=relative_path,
                        file_type=file_path.suffix.lower() or "unknown",
                        category=self._get_file_category(relative_path),
                        language=self._get_file_language(file_path),
                        size=file_path.stat().st_size,
                        modified_time=datetime.fromtimestamp(file_path.stat().st_mtime),
                    )
                    files.append(file_info)
                except (OSError, ValueError) as e:
                    logger.warning("Could not process file %s: %s", file_path, e)
                    continue

        return files

    async def _read_file_content(self, file_path: Path) -> Optional[str]:
        """Read file content with error handling"""
        try:
            # Try UTF-8 first
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                return await f.read()
        except UnicodeDecodeError:
            try:
                # Try with latin-1 as fallback
                async with aiofiles.open(file_path, "r", encoding="latin-1") as f:
                    return await f.read()
            except OSError as e:
                logger.warning("Failed to read file %s: %s", file_path, e)
                return None
            except Exception as e:
                logger.warning("Could not decode file %s: %s", file_path, e)
                return None
        except OSError as e:
            logger.warning("Failed to read file %s: %s", file_path, e)
            return None
        except Exception as e:
            logger.warning("Error reading file %s: %s", file_path, e)
            return None

    def _chunk_file_content(
        self, content: str, file_info: FileInfo
    ) -> List[Dict[str, Any]]:
        """Chunk file content based on file type"""
        if file_info.language == "python":
            return self.chunker.chunk_python_file(content, str(file_info.path))
        elif file_info.language == "vue":
            return self.chunker.chunk_vue_file(content, str(file_info.path))
        elif file_info.language == "markdown":
            return self.chunker.chunk_markdown_file(content, str(file_info.path))
        elif file_info.language in JAVASCRIPT_LANGUAGE_TYPES:
            return self.chunker.chunk_javascript_content(content)
        else:
            return self.chunker.chunk_generic_file(content, str(file_info.path))

    def _build_chunk_metadata(
        self, file_info: FileInfo, chunk: Dict[str, Any], index: int, total: int
    ) -> Dict[str, Any]:
        """
        Build metadata dictionary for a chunk.

        Issue #620.
        """
        metadata = {
            "source": file_info.relative_path,
            "file_path": str(file_info.path),
            "file_type": file_info.file_type,
            "category": file_info.category,
            "language": file_info.language,
            "file_size": file_info.size,
            "modified_time": file_info.modified_time.isoformat(),
            "chunk_index": index,
            "total_chunks": total,
            "chunk_type": chunk.get("type", "general"),
            "indexed_at": datetime.now().isoformat(),
            "indexer_version": "1.0.0",
        }
        for key, value in chunk.items():
            if key not in EXCLUDED_CHUNK_METADATA_KEYS:
                metadata[f"chunk_{key}"] = value
        return metadata

    async def _store_single_chunk(
        self,
        chunk: Dict[str, Any],
        metadata: Dict[str, Any],
        knowledge_base,
        index: int,
        total: int,
        relative_path: str,
    ) -> bool:
        """
        Store a single chunk in the knowledge base.

        Issue #620.
        """
        if not hasattr(knowledge_base, "store_fact"):
            logger.warning("Knowledge base does not support store_fact method")
            return False

        result = await knowledge_base.store_fact(chunk["content"], metadata)
        if result and result.get("status") == "success":
            logger.debug("Stored chunk %s/%s for %s", index + 1, total, relative_path)
            return True
        logger.warning(
            "Failed to store chunk %s for %s: %s", index + 1, relative_path, result
        )
        return False

    async def _store_chunks(
        self, chunks: List[Dict[str, Any]], file_info: FileInfo, knowledge_base
    ) -> int:
        """Store file chunks in the knowledge base."""
        stored_count = 0
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            try:
                metadata = self._build_chunk_metadata(file_info, chunk, i, total)
                if await self._store_single_chunk(
                    chunk, metadata, knowledge_base, i, total, file_info.relative_path
                ):
                    stored_count += 1
            except Exception as e:
                logger.error(
                    "Error storing chunk %s for %s: %s",
                    i + 1,
                    file_info.relative_path,
                    e,
                )
                self.progress.errors.append(
                    f"Chunk storage error in {file_info.relative_path}[{i+1}]: {str(e)}"
                )

        return stored_count

    def _record_indexing_result(self, file_info: FileInfo, stored_count: int) -> bool:
        """
        Record the result of indexing a file.

        Issue #620.
        """
        self.progress.total_chunks += stored_count
        if stored_count > 0:
            self.progress.successful_files += 1
            logger.info("Indexed %s: %s chunks", file_info.relative_path, stored_count)
        else:
            self.progress.failed_files += 1
            self.progress.errors.append(
                f"No chunks stored for: {file_info.relative_path}"
            )
        self.progress.processed_files += 1
        return stored_count > 0

    async def index_single_file(self, file_info: FileInfo, knowledge_base) -> bool:
        """Index a single file."""
        try:
            self.progress.current_file = file_info.relative_path
            self.progress.current_category = file_info.category

            content = await self._read_file_content(file_info.path)
            if content is None:
                self.progress.failed_files += 1
                self.progress.errors.append(
                    f"Could not read file: {file_info.relative_path}"
                )
                return False

            if not content.strip():
                logger.debug("Skipping empty file: %s", file_info.relative_path)
                self.progress.processed_files += 1
                return True

            chunks = self._chunk_file_content(content, file_info)
            if not chunks:
                logger.warning("No chunks generated for: %s", file_info.relative_path)
                self.progress.processed_files += 1
                return True

            stored_count = await self._store_chunks(chunks, file_info, knowledge_base)
            return self._record_indexing_result(file_info, stored_count)

        except Exception as e:
            logger.error("Error indexing file %s: %s", file_info.relative_path, e)
            self.progress.failed_files += 1
            self.progress.processed_files += 1
            self.progress.errors.append(
                f"Indexing error in {file_info.relative_path}: {str(e)}"
            )
            return False

    def _group_files_by_category(self, files: List) -> Dict[str, List]:
        """Group files by their category (Issue #665: extracted helper)."""
        files_by_category = {}
        for file_info in files:
            category = file_info.category
            if category not in files_by_category:
                files_by_category[category] = []
            files_by_category[category].append(file_info)
        return files_by_category

    async def _process_category_batches(
        self, category_files: List, batch_size: int, knowledge_base
    ) -> None:
        """Process a category's files in batches (Issue #665: extracted helper)."""
        for i in range(0, len(category_files), batch_size):
            batch = category_files[i : i + batch_size]

            tasks = [
                self.index_single_file(file_info, knowledge_base) for file_info in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successful_in_batch = sum(1 for r in results if r is True)
            logger.info(
                "Batch %s: %s/%s files indexed successfully",
                i // batch_size + 1,
                successful_in_batch,
                len(batch),
            )

            await asyncio.sleep(TimingConstants.MICRO_DELAY)

    def _log_indexing_completion(self) -> None:
        """Log indexing completion summary (Issue #665: extracted helper)."""
        logger.info("Codebase indexing completed!")
        logger.info(
            "Results: %s successful, %s failed",
            self.progress.successful_files,
            self.progress.failed_files,
        )
        logger.info("Total chunks created: %s", self.progress.total_chunks)

        if self.progress.errors:
            logger.warning("Errors encountered: %s", len(self.progress.errors))
            for error in self.progress.errors[:10]:
                logger.warning("  - %s", error)

    async def index_codebase(
        self, batch_size: int = 10, max_files: Optional[int] = None
    ) -> IndexingProgress:
        """Index the entire codebase with progress tracking"""
        logger.info("Starting codebase indexing for: %s", self.root_path)

        self.progress = IndexingProgress()
        self.progress.start_time = datetime.now()

        try:
            knowledge_base = await get_knowledge_base()
            if knowledge_base is None:
                raise RuntimeError("Could not initialize knowledge base")

            logger.info("Scanning codebase for files...")
            files = self._scan_files()

            if max_files:
                files = files[:max_files]

            self.progress.total_files = len(files)
            logger.info("Found %s files to index", len(files))

            files_by_category = self._group_files_by_category(files)

            for category, category_files in files_by_category.items():
                logger.info(
                    "Processing %s files in category: %s", len(category_files), category
                )
                await self._process_category_batches(
                    category_files, batch_size, knowledge_base
                )

            self.progress.end_time = datetime.now()
            self._log_indexing_completion()

            return self.progress

        except Exception as e:
            logger.error("Codebase indexing failed: %s", e)
            self.progress.end_time = datetime.now()
            self.progress.errors.append(f"Indexing failed: {str(e)}")
            return self.progress

    def get_indexing_stats(self) -> Dict[str, Any]:
        """Get current indexing statistics"""
        return self.progress.to_dict()

    async def _process_category_reindex_batches(
        self, category: str, category_files: List, batch_size: int, knowledge_base
    ) -> None:
        """
        Process category files in batches during reindexing.

        Issue #620.
        """
        for i in range(0, len(category_files), batch_size):
            batch = category_files[i : i + batch_size]
            tasks = [
                self.index_single_file(file_info, knowledge_base) for file_info in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful_in_batch = sum(1 for r in results if r is True)
            logger.info(
                "Category %s batch %s: %s/%s files indexed",
                category,
                i // batch_size + 1,
                successful_in_batch,
                len(batch),
            )
            await asyncio.sleep(TimingConstants.MICRO_DELAY)

    def _handle_reindex_error(
        self, category: str, error: Exception
    ) -> IndexingProgress:
        """
        Handle error during category reindexing.

        Issue #620.
        """
        logger.error("Category reindexing failed for %s: %s", category, error)
        self.progress.end_time = datetime.now()
        self.progress.errors.append(f"Category reindexing failed: {str(error)}")
        return self.progress

    async def reindex_category(
        self, category: str, batch_size: int = 10
    ) -> IndexingProgress:
        """Reindex files in a specific category."""
        logger.info("Starting category reindexing for: %s", category)
        self.progress = IndexingProgress()
        self.progress.start_time = datetime.now()

        try:
            knowledge_base = await get_knowledge_base()
            if knowledge_base is None:
                raise RuntimeError("Could not initialize knowledge base")

            files = self._scan_files()
            category_files = [f for f in files if f.category == category]
            self.progress.total_files = len(category_files)
            logger.info("Found %s files in category: %s", len(category_files), category)

            if not category_files:
                logger.warning("No files found for category: %s", category)
                return self.progress

            await self._process_category_reindex_batches(
                category, category_files, batch_size, knowledge_base
            )

            self.progress.end_time = datetime.now()
            logger.info(
                "Category %s reindexing completed: %s successful",
                category,
                self.progress.successful_files,
            )
            return self.progress

        except Exception as e:
            return self._handle_reindex_error(category, e)


# Global service instance (thread-safe)
import threading

_indexing_service: Optional[CodebaseIndexingService] = None
_indexing_service_lock = threading.Lock()


def get_indexing_service() -> CodebaseIndexingService:
    """Get the global indexing service instance (thread-safe)."""
    global _indexing_service
    if _indexing_service is None:
        with _indexing_service_lock:
            # Double-check after acquiring lock
            if _indexing_service is None:
                _indexing_service = CodebaseIndexingService()
    return _indexing_service


# Convenience functions
async def index_autobot_codebase(
    max_files: Optional[int] = None, batch_size: int = 10
) -> IndexingProgress:
    """Index the AutoBot codebase"""
    service = get_indexing_service()
    return await service.index_codebase(batch_size=batch_size, max_files=max_files)


async def reindex_category(category: str, batch_size: int = 10) -> IndexingProgress:
    """Reindex a specific category"""
    service = get_indexing_service()
    return await service.reindex_category(category, batch_size=batch_size)


def get_indexing_progress() -> Dict[str, Any]:
    """Get current indexing progress"""
    service = get_indexing_service()
    return service.get_indexing_stats()
