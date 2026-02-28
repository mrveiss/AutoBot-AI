# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
File Server Connector

Issue #1254: Ingests content from a mounted directory (NFS, SMB, local).
Supports plain-text formats: .txt, .md, .json, .csv, .py, .html.
PDF and DOCX are logged as warnings and skipped (future extension point).
"""

import asyncio
import fnmatch
import hashlib
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = logging.getLogger(__name__)

# File extensions this connector can read as plain text
_SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".rst",
    ".xml",
}

# Extensions we recognise but skip with an explicit warning
_SKIP_EXTENSIONS = {".pdf", ".docx", ".doc", ".xls", ".xlsx", ".pptx"}


@ConnectorRegistry.register("file_server")
class FileServerConnector(AbstractConnector):
    """Connector for local or network-mounted file directories.

    Config keys (all under ``config.config``):
        base_path (str): Absolute path to the root directory.
        include_patterns (list[str]): Glob patterns to include.
            Defaults to all supported text files.
        exclude_patterns (list[str]): Glob patterns to exclude.
            Defaults to ["**/node_modules/**", "**/.git/**"].
        max_file_size_mb (int): Skip files larger than this. Default 10.
    """

    connector_type = "file_server"

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._base_path = Path(cfg.get("base_path", ""))
        self._include_patterns: List[str] = cfg.get(
            "include_patterns",
            ["**/*.txt", "**/*.md", "**/*.json", "**/*.csv", "**/*.py", "**/*.html"],
        )
        self._exclude_patterns: List[str] = cfg.get(
            "exclude_patterns",
            ["**/node_modules/**", "**/.git/**", "**/__pycache__/**"],
        )
        self._max_size_bytes: int = int(cfg.get("max_file_size_mb", 10)) * 1024 * 1024

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Return True if base_path exists and is readable."""
        try:
            exists = await asyncio.to_thread(self._base_path.exists)
            if not exists:
                self.logger.warning("base_path does not exist: %s", self._base_path)
                return False
            is_dir = await asyncio.to_thread(self._base_path.is_dir)
            if not is_dir:
                self.logger.warning("base_path is not a directory: %s", self._base_path)
                return False
            # Quick readable check
            await asyncio.to_thread(list, self._base_path.iterdir())
            return True
        except PermissionError as exc:
            self.logger.error(
                "Permission denied on base_path %s: %s", self._base_path, exc
            )
            return False
        except Exception as exc:
            self.logger.error("test_connection failed: %s", exc)
            return False

    async def discover_sources(self) -> List[SourceInfo]:
        """Scan base_path recursively and return a SourceInfo per matching file."""
        return await asyncio.to_thread(self._scan_files_sync)

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Read and return file content for *source_id* (which is the file path)."""
        return await asyncio.to_thread(self._read_file_sync, source_id)

    async def detect_changes(
        self, since: Optional[datetime] = None
    ) -> List[ChangeInfo]:
        """Compare current file mtimes against *since* and report changes."""
        sources = await self.discover_sources()
        changes: List[ChangeInfo] = []

        for src in sources:
            if since is None or src.last_modified > since:
                change_type = "modified" if since is not None else "added"
                changes.append(
                    ChangeInfo(
                        source_id=src.source_id,
                        change_type=change_type,
                        timestamp=src.last_modified,
                        details={"path": src.path, "size_bytes": src.size_bytes},
                    )
                )

        self.logger.info(
            "detect_changes: %d changes found (since=%s)",
            len(changes),
            since,
        )
        return changes

    # ------------------------------------------------------------------
    # Internal sync helpers
    # ------------------------------------------------------------------

    def _matches_include(self, rel_path: str) -> bool:
        """Return True if rel_path matches any include pattern."""
        if not self._include_patterns:
            return True
        return any(fnmatch.fnmatch(rel_path, pat) for pat in self._include_patterns)

    def _matches_exclude(self, rel_path: str) -> bool:
        """Return True if rel_path matches any exclude pattern."""
        return any(fnmatch.fnmatch(rel_path, pat) for pat in self._exclude_patterns)

    def _build_source_id(self, file_path: Path) -> str:
        """Derive a stable source_id from the absolute file path."""
        return hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:32]

    def _scan_files_sync(self) -> List[SourceInfo]:
        """Blocking directory walk — run via asyncio.to_thread (Issue #1254)."""
        sources: List[SourceInfo] = []

        if not self._base_path.exists() or not self._base_path.is_dir():
            logger.warning("base_path not available: %s", self._base_path)
            return sources

        for file_path in self._base_path.rglob("*"):
            if not file_path.is_file():
                continue

            rel = str(file_path.relative_to(self._base_path))

            if self._matches_exclude(rel):
                continue
            if not self._matches_include(rel):
                continue

            ext = file_path.suffix.lower()
            if ext in _SKIP_EXTENSIONS:
                logger.debug("Skipping unsupported format: %s", file_path)
                continue

            try:
                stat = file_path.stat()
            except OSError as exc:
                logger.warning("Cannot stat %s: %s", file_path, exc)
                continue

            if stat.st_size > self._max_size_bytes:
                logger.debug(
                    "Skipping oversized file (%d bytes > %d): %s",
                    stat.st_size,
                    self._max_size_bytes,
                    file_path,
                )
                continue

            content_type = mimetypes.guess_type(str(file_path))[0] or "text/plain"
            source_id = self._build_source_id(file_path)
            last_modified = datetime.utcfromtimestamp(stat.st_mtime)

            sources.append(
                SourceInfo(
                    source_id=source_id,
                    name=file_path.name,
                    path=str(file_path),
                    content_type=content_type,
                    size_bytes=stat.st_size,
                    last_modified=last_modified,
                    metadata={"relative_path": rel, "extension": ext},
                )
            )

        logger.debug("Scanned %d sources from %s", len(sources), self._base_path)
        return sources

    def _read_file_sync(self, source_id: str) -> Optional[ContentResult]:
        """Blocking file read — run via asyncio.to_thread (Issue #1254)."""
        # source_id is a hash; we must scan to find the matching path
        sources = self._scan_files_sync()
        target = next((s for s in sources if s.source_id == source_id), None)
        if target is None:
            logger.warning("source_id not found in scan: %s", source_id)
            return None

        file_path = Path(target.path)
        ext = file_path.suffix.lower()

        if ext not in _SUPPORTED_EXTENSIONS:
            logger.warning("Unsupported extension '%s' for %s", ext, file_path)
            return None

        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.error("Failed to read %s: %s", file_path, exc)
            return None

        chunks = _chunk_text(text)

        return ContentResult(
            source_id=source_id,
            content=text,
            content_type=target.content_type,
            metadata={
                "path": target.path,
                "name": target.name,
                "relative_path": target.metadata.get("relative_path", ""),
                "extension": ext,
                "connector_id": self.config.connector_id,
            },
            chunks=chunks,
        )


def _chunk_text(text: str, max_chars: int = 2000) -> List[str]:
    """Split text into paragraph-based chunks of at most *max_chars* chars.

    Falls back to fixed-size splitting when paragraphs are very long.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        # If a single paragraph exceeds max_chars, split by fixed size
        if len(para) > max_chars:
            for i in range(0, len(para), max_chars):
                chunks.append(para[i : i + max_chars])
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks
