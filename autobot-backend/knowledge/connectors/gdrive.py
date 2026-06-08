# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Google Drive Knowledge Connector (Issue #9003)

Indexes documents from Google Drive personal and shared drives into the
AutoBot knowledge base via Google Drive API v3.

Supported file types:
- Google Docs (.gdoc) - exported as plain text
- Google Sheets (.gsheet) - exported as CSV then text
- PDF documents (.pdf) - text extraction
- Word documents (.docx) - full text extraction
- Markdown files (.md) - raw content

Config keys (under ``ConnectorConfig.config``):
    token (str): Google Drive API OAuth2 access token. Required.
    source_type (str): "mydrive" or "shared". Default "mydrive".
    drive_id (str): Specific shared drive ID. Required when source_type is "shared".
    folder_id (str): Specific folder ID to sync. Default None (root).
    sync_subfolders (bool): Recursively sync subfolders. Default True.
    max_file_size_mb (int): Skip files larger than this. Default 100MB.
    supported_extensions (list[str]): File extensions to index.
                                      Default [".gdoc", ".gsheet", ".pdf", ".docx", ".md"].
"""

import hashlib
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from autobot_shared.auth import BearerAuth
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
_REDIS_TS_PREFIX = "connector:gdrive:ts:"
_REDIS_TS_TTL = 86400 * 30  # 30 days

# Default supported extensions (Google native + common formats)
_DEFAULT_EXTENSIONS = [".gdoc", ".gsheet", ".pdf", ".docx", ".md", ".txt"]

# Max file size in bytes (default 100MB)
_DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024

# Google Drive native MIME types
_GDOC_MIME = "application/vnd.google-apps.document"
_GSHEET_MIME = "application/vnd.google-apps.spreadsheet"


def _content_hash(text: str) -> str:
    """Generate SHA-256 hash of content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_text_from_docx(content_bytes: bytes) -> str:
    """Extract text from Word .docx file."""
    try:
        from docx import Document

        doc = Document(io.BytesIO(content_bytes))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as exc:
        logger.warning("Failed to extract text from DOCX: %s", exc)
        return ""


def _extract_text_from_pdf(content_bytes: bytes) -> str:
    """Extract text from PDF file."""
    try:
        from PyPDF2 import PdfReader

        pdf = PdfReader(io.BytesIO(content_bytes))
        pages_text = []
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text.strip():
                pages_text.append(f"## Page {page_num}\n{text}")
        return "\n\n".join(pages_text)
    except Exception as exc:
        logger.warning("Failed to extract text from PDF: %s", exc)
        return ""


async def _load_ts(connector_id: str, source_id: str) -> Optional[str]:
    """Load last-modified timestamp for a source from Redis."""
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(database="knowledge")
        key = f"{_REDIS_TS_PREFIX}{connector_id}:{source_id}"
        value = redis.get(key)
        if hasattr(value, "__await__"):
            value = await value
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value
    except Exception as exc:
        logger.warning("Redis load_ts failed for %s: %s", source_id, exc)
        return None


async def _store_ts(connector_id: str, source_id: str, ts: str) -> None:
    """Store last-modified timestamp for a source in Redis."""
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(database="knowledge")
        key = f"{_REDIS_TS_PREFIX}{connector_id}:{source_id}"
        result = redis.set(key, ts, ex=_REDIS_TS_TTL)
        if hasattr(result, "__await__"):
            await result
    except Exception as exc:
        logger.warning("Redis store_ts failed for %s: %s", source_id, exc)


@ConnectorRegistry.register("gdrive")
class GoogleDriveConnector(AbstractConnector):
    """Knowledge connector for Google Drive personal and shared drives.

    Indexes documents from Google Drive into the AutoBot knowledge base.
    Supports incremental sync via last-modified timestamp comparison.

    Each file becomes one KB fact keyed by ``gdrive:{connector_id}:file:{file_id}``.
    """

    connector_type = "gdrive"
    # Issue #4421: needs OAuth2 access token (tier 2 = credentials/OAuth)
    tier = 2

    @classmethod
    def auth_schema(cls) -> type:
        """Google Drive requires a bearer token (OAuth2 access token)."""
        return BearerAuth

    @classmethod
    def output_schema(cls) -> Dict[str, Any]:
        """Return JSONSchema for ContentResult.metadata."""
        return {
            "type": "object",
            "required": ["file_id", "file_name", "file_extension", "last_modified"],
            "properties": {
                "file_id": {"type": "string", "description": "Google Drive file ID"},
                "file_name": {"type": "string", "description": "File name with extension"},
                "file_extension": {"type": "string", "description": "File extension (e.g., .docx)"},
                "file_path": {"type": "string", "description": "Full path in drive"},
                "file_size": {"type": "integer", "description": "File size in bytes"},
                "last_modified": {"type": "string", "description": "ISO-8601 last modified datetime"},
                "web_url": {"type": "string", "description": "Web URL to view file"},
                "drive_id": {"type": "string", "description": "Drive ID"},
                "mime_type": {"type": "string", "description": "MIME type"},
            },
        }

    @property
    def max_concurrency(self) -> int:
        """Max parallel file fetches. Default 4 for Google Drive."""
        cfg_val = self.config.max_concurrency
        return cfg_val if cfg_val is not None else 4

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._token: str = cfg.get("token", "")
        self._source_type: str = cfg.get("source_type", "mydrive")  # "mydrive" or "shared"
        self._drive_id: Optional[str] = cfg.get("drive_id")
        self._folder_id: Optional[str] = cfg.get("folder_id")
        self._sync_subfolders: bool = cfg.get("sync_subfolders", True)
        self._max_file_size: int = cfg.get("max_file_size_mb", 100) * 1024 * 1024
        self._supported_extensions: List[str] = cfg.get("supported_extensions", _DEFAULT_EXTENSIONS)
        self._api_base: str = cfg.get("api_base", _DRIVE_API_BASE).rstrip("/")

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Verify Google Drive credentials by fetching about info."""
        try:
            url = f"{self._api_base}/about"
            params = {"fields": "user"}
            result = await self._drive_request("GET", url, params=params)
            healthy = result.get("status_code") == 200
            if not healthy:
                self.logger.warning(
                    "Google Drive test_connection failed: HTTP %s",
                    result.get("status_code"),
                )
            return healthy
        except Exception as exc:
            self.logger.error("Google Drive test_connection raised: %s", exc)
            return False

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every supported file in the configured drive/folder."""
        files = await self._list_all_files()
        sources: List[SourceInfo] = []
        for file_item in files:
            source_info = self._file_to_source_info(file_item)
            if source_info:
                sources.append(source_info)
        return sources

    async def fetch_content(self, source_id: str) -> ContentResult | None:
        """Fetch and extract text content for a Google Drive file by ID."""
        # source_id format: "gdrive:{connector_id}:file:{file_id}"
        parts = source_id.split(":")
        if len(parts) != 4 or parts[0] != "gdrive" or parts[2] != "file":
            self.logger.error("Invalid source_id format: %s", source_id)
            return None

        file_id = parts[3]

        # Get file metadata first
        metadata_url = f"{self._api_base}/files/{file_id}"
        params = {
            "fields": "id,name,mimeType,size,modifiedTime,webViewLink,parents,driveId",
            "supportsAllDrives": "true",
        }
        metadata_result = await self._drive_request("GET", metadata_url, params=params)

        if metadata_result.get("status_code") != 200:
            self.logger.error(
                "Failed to fetch Google Drive file metadata %s: HTTP %s",
                file_id,
                metadata_result.get("status_code"),
            )
            return None

        file_meta = metadata_result.get("body", {})
        file_name = file_meta.get("name", "")
        mime_type = file_meta.get("mimeType", "")
        file_ext = self._get_file_extension(file_name, mime_type).lower()

        # Download or export file content
        text = ""
        if mime_type == _GDOC_MIME:
            # Export Google Doc as plain text
            export_url = f"{self._api_base}/files/{file_id}/export"
            export_params = {"mimeType": "text/plain"}
            download_result = await self._drive_request("GET", export_url, params=export_params, raw_content=True)
            if download_result.get("status_code") == 200:
                content_bytes = download_result.get("content", b"")
                try:
                    text = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    self.logger.warning("Failed to decode Google Doc %s as UTF-8", file_id)
                    text = content_bytes.decode("utf-8", errors="replace")
        elif mime_type == _GSHEET_MIME:
            # Export Google Sheet as CSV
            export_url = f"{self._api_base}/files/{file_id}/export"
            export_params = {"mimeType": "text/csv"}
            download_result = await self._drive_request("GET", export_url, params=export_params, raw_content=True)
            if download_result.get("status_code") == 200:
                content_bytes = download_result.get("content", b"")
                try:
                    text = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    self.logger.warning("Failed to decode Google Sheet %s as UTF-8", file_id)
                    text = content_bytes.decode("utf-8", errors="replace")
        else:
            # Download regular file
            download_url = f"{self._api_base}/files/{file_id}"
            download_params = {"alt": "media", "supportsAllDrives": "true"}
            download_result = await self._drive_request("GET", download_url, params=download_params, raw_content=True)

            if download_result.get("status_code") != 200:
                self.logger.error(
                    "Failed to download Google Drive file %s: HTTP %s",
                    file_id,
                    download_result.get("status_code"),
                )
                return None

            content_bytes = download_result.get("content", b"")

            # Extract text based on file type
            if file_ext == ".docx":
                text = _extract_text_from_docx(content_bytes)
            elif file_ext == ".pdf":
                text = _extract_text_from_pdf(content_bytes)
            elif file_ext in [".md", ".txt"]:
                try:
                    text = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    self.logger.warning("Failed to decode text file %s as UTF-8", file_id)
                    text = content_bytes.decode("utf-8", errors="replace")
            else:
                self.logger.warning("Unsupported file type for %s: %s", file_id, file_ext)
                return None

        if not text.strip():
            self.logger.debug("Extracted empty text from file %s", file_id)
            return None

        # Add file header
        header = f"# {file_name}\n\nFile: {file_meta.get('webViewLink', '')}\n\n"
        text = header + text

        # Update stored timestamp
        last_modified = file_meta.get("modifiedTime", "")
        if last_modified:
            await _store_ts(self.config.connector_id, source_id, last_modified)

        # Build file path from parents
        file_path = await self._build_file_path(file_meta.get("parents", []), file_name)

        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "file_id": file_id,
                "file_name": file_name,
                "file_extension": file_ext,
                "file_path": file_path,
                "file_size": file_meta.get("size", 0),
                "last_modified": last_modified,
                "web_url": file_meta.get("webViewLink", ""),
                "drive_id": file_meta.get("driveId", ""),
                "mime_type": mime_type,
                "connector_id": self.config.connector_id,
            },
        )

    async def detect_changes(self, since: datetime | None = None) -> List[ChangeInfo]:
        """Return ChangeInfo for files added or modified since *since*.

        When *since* is None all files are reported as 'added'. Otherwise
        compares modifiedTime against stored Redis timestamp.
        """
        files = await self._list_all_files()
        changes: List[ChangeInfo] = []

        for file_item in files:
            file_id = file_item.get("id", "")
            source_id = f"gdrive:{self.config.connector_id}:file:{file_id}"
            last_modified = file_item.get("modifiedTime", "")

            change = await self._classify_change(source_id, last_modified, since)
            if change:
                changes.append(change)

        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _list_all_files(self) -> List[Dict[str, Any]]:
        """List all files in the configured drive/folder (with pagination)."""
        files: List[Dict[str, Any]] = []

        # Build query
        query_parts = []

        # Folder constraint
        if self._folder_id:
            query_parts.append(f"'{self._folder_id}' in parents")
        elif self._source_type == "shared" and self._drive_id:
            # Root of shared drive
            pass  # Will use driveId parameter
        else:
            # My Drive root
            query_parts.append("'root' in parents")

        # Only files (not folders for now, we'll handle subfolders separately)
        query_parts.append("mimeType != 'application/vnd.google-apps.folder'")

        # Not trashed
        query_parts.append("trashed = false")

        query = " and ".join(query_parts)

        # API parameters
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink,parents,driveId)",
            "pageSize": "100",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        if self._source_type == "shared" and self._drive_id:
            params["driveId"] = self._drive_id
            params["corpora"] = "drive"

        # Fetch all pages
        page_token = None
        while True:
            if page_token:
                params["pageToken"] = page_token

            url = f"{self._api_base}/files"
            result = await self._drive_request("GET", url, params=params)

            if result.get("status_code") != 200:
                self.logger.error(
                    "Failed to list Google Drive files: HTTP %s",
                    result.get("status_code"),
                )
                break

            body = result.get("body", {})
            items = body.get("files", [])

            for item in items:
                # Check file size
                size = int(item.get("size", 0))
                if size > self._max_file_size:
                    self.logger.debug(
                        "Skipping file %s (size %d exceeds max %d)",
                        item.get("name"),
                        size,
                        self._max_file_size,
                    )
                    continue

                # Check file extension
                file_name = item.get("name", "")
                mime_type = item.get("mimeType", "")
                file_ext = self._get_file_extension(file_name, mime_type).lower()
                if file_ext in self._supported_extensions:
                    files.append(item)
                else:
                    self.logger.debug(
                        "Skipping file %s (extension %s not supported)",
                        file_name,
                        file_ext,
                    )

            page_token = body.get("nextPageToken")
            if not page_token:
                break

        # Recursively list subfolders if enabled
        if self._sync_subfolders:
            subfolder_files = await self._list_subfolders()
            files.extend(subfolder_files)

        return files

    async def _list_subfolders(self) -> List[Dict[str, Any]]:
        """Recursively list all files in subfolders."""
        files: List[Dict[str, Any]] = []

        # Build query for folders
        query_parts = []

        # Folder constraint
        if self._folder_id:
            query_parts.append(f"'{self._folder_id}' in parents")
        elif self._source_type == "shared" and self._drive_id:
            pass  # Will use driveId parameter
        else:
            query_parts.append("'root' in parents")

        # Only folders
        query_parts.append("mimeType = 'application/vnd.google-apps.folder'")
        query_parts.append("trashed = false")

        query = " and ".join(query_parts)

        params = {
            "q": query,
            "fields": "nextPageToken,files(id)",
            "pageSize": "100",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        if self._source_type == "shared" and self._drive_id:
            params["driveId"] = self._drive_id
            params["corpora"] = "drive"

        # Fetch all folder pages
        page_token = None
        while True:
            if page_token:
                params["pageToken"] = page_token

            url = f"{self._api_base}/files"
            result = await self._drive_request("GET", url, params=params)

            if result.get("status_code") != 200:
                self.logger.warning(
                    "Failed to list subfolders: HTTP %s",
                    result.get("status_code"),
                )
                break

            body = result.get("body", {})
            folders = body.get("files", [])

            # Recursively list each folder
            for folder in folders:
                folder_id = folder.get("id", "")
                if folder_id:
                    folder_files = await self._list_folder_files(folder_id)
                    files.extend(folder_files)

            page_token = body.get("nextPageToken")
            if not page_token:
                break

        return files

    async def _list_folder_files(self, folder_id: str) -> List[Dict[str, Any]]:
        """List all files in a specific folder (recursively)."""
        files: List[Dict[str, Any]] = []

        # Build query for files in this folder
        query = f"'{folder_id}' in parents and trashed = false"

        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink,parents,driveId)",
            "pageSize": "100",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        if self._source_type == "shared" and self._drive_id:
            params["driveId"] = self._drive_id
            params["corpora"] = "drive"

        # Fetch all pages
        page_token = None
        while True:
            if page_token:
                params["pageToken"] = page_token

            url = f"{self._api_base}/files"
            result = await self._drive_request("GET", url, params=params)

            if result.get("status_code") != 200:
                self.logger.warning(
                    "Failed to list folder %s: HTTP %s",
                    folder_id,
                    result.get("status_code"),
                )
                break

            body = result.get("body", {})
            items = body.get("files", [])

            for item in items:
                mime_type = item.get("mimeType", "")

                # Skip folders (we'll handle them separately)
                if mime_type == "application/vnd.google-apps.folder":
                    # Recursively list subfolder
                    subfolder_id = item.get("id", "")
                    if subfolder_id:
                        subfolder_files = await self._list_folder_files(subfolder_id)
                        files.extend(subfolder_files)
                    continue

                # Check file size
                size = int(item.get("size", 0))
                if size > self._max_file_size:
                    continue

                # Check file extension
                file_name = item.get("name", "")
                file_ext = self._get_file_extension(file_name, mime_type).lower()
                if file_ext in self._supported_extensions:
                    files.append(item)

            page_token = body.get("nextPageToken")
            if not page_token:
                break

        return files

    async def _classify_change(
        self,
        source_id: str,
        last_modified: str,
        since: datetime | None,
    ) -> ChangeInfo | None:
        """Return ChangeInfo when the file is new or was modified after *since*."""
        if since is None:
            return ChangeInfo(
                source_id=source_id,
                change_type="added",
                timestamp=now_utc(),
                details={"last_modified": last_modified},
            )

        stored_ts = await _load_ts(self.config.connector_id, source_id)
        if stored_ts is None or last_modified > stored_ts:
            change_type = "added" if stored_ts is None else "modified"
            return ChangeInfo(
                source_id=source_id,
                change_type=change_type,
                timestamp=parse_utc_iso(last_modified) if last_modified else now_utc(),
                details={"last_modified": last_modified},
            )

        return None

    def _file_to_source_info(self, file_item: Dict[str, Any]) -> SourceInfo | None:
        """Convert a Drive API file item to SourceInfo."""
        file_id = file_item.get("id", "")
        if not file_id:
            return None

        file_name = file_item.get("name", "")
        mime_type = file_item.get("mimeType", "")
        file_ext = self._get_file_extension(file_name, mime_type).lower()

        if file_ext not in self._supported_extensions:
            return None

        source_id = f"gdrive:{self.config.connector_id}:file:{file_id}"
        last_modified_str = file_item.get("modifiedTime", "")
        last_modified = parse_utc_iso(last_modified_str) if last_modified_str else now_utc()

        # File path will be built asynchronously when needed
        # For now just use the file name
        file_path = f"/{file_name}"

        return SourceInfo(
            source_id=source_id,
            name=file_name,
            path=file_path,
            content_type=self._get_content_type(file_ext, mime_type),
            size_bytes=int(file_item.get("size", 0)),
            last_modified=last_modified,
            metadata={
                "file_id": file_id,
                "file_name": file_name,
                "file_extension": file_ext,
                "web_url": file_item.get("webViewLink", ""),
                "drive_id": file_item.get("driveId", ""),
                "mime_type": mime_type,
            },
        )

    async def _build_file_path(self, parent_ids: List[str], file_name: str) -> str:
        """Build full file path from parent folder IDs."""
        if not parent_ids:
            return f"/{file_name}"

        # For now, just use the file name
        # TODO: Implement full path resolution by fetching parent folder names
        return f"/{file_name}"

    @staticmethod
    def _get_file_extension(file_name: str, mime_type: str) -> str:
        """Extract file extension from file name or MIME type."""
        # Handle Google native types
        if mime_type == _GDOC_MIME:
            return ".gdoc"
        elif mime_type == _GSHEET_MIME:
            return ".gsheet"

        # Regular files - extract from name
        if "." in file_name:
            return "." + file_name.rsplit(".", 1)[-1]
        return ""

    @staticmethod
    def _get_content_type(file_ext: str, mime_type: str) -> str:
        """Map file extension to MIME type."""
        # Google native types
        if mime_type == _GDOC_MIME:
            return "application/vnd.google-apps.document"
        elif mime_type == _GSHEET_MIME:
            return "application/vnd.google-apps.spreadsheet"

        # Standard types
        content_type_map = {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pdf": "application/pdf",
            ".md": "text/markdown",
            ".txt": "text/plain",
        }
        return content_type_map.get(file_ext.lower(), mime_type or "application/octet-stream")

    async def _drive_request(
        self,
        method: str,
        url: str,
        json_data: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
        raw_content: bool = False,
    ) -> Dict[str, Any]:
        """Make an HTTP request to Google Drive API with auth and error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            json_data: JSON body for POST/PATCH requests
            params: Query parameters
            raw_content: If True, return raw bytes in "content" key instead of parsing JSON

        Returns:
            Dict with keys: status_code, body (or content if raw_content=True), error
        """
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=60.0)  # Longer timeout for file downloads
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    params=params,
                ) as resp:
                    status_code = resp.status

                    # Handle no-content responses
                    if status_code == 204:
                        return {"status_code": 204, "body": {}}

                    if raw_content:
                        content = await resp.read()
                        return {
                            "status_code": status_code,
                            "content": content,
                        }

                    try:
                        body = await resp.json()
                    except aiohttp.ContentTypeError:
                        body = {}

                    # Log errors
                    if status_code >= 400:
                        error_msg = body.get("error", {}).get("message", "Unknown error")
                        self.logger.warning(
                            "Drive API request to %s failed: HTTP %d - %s",
                            url,
                            status_code,
                            error_msg,
                        )

                    return {
                        "status_code": status_code,
                        "body": body,
                        "error": body.get("error", {}).get("message") if status_code >= 400 else None,
                    }

        except aiohttp.ClientError as exc:
            self.logger.error("Drive API request to %s failed: %s", url, exc)
            return {
                "status_code": 0,
                "body": {},
                "error": str(exc),
            }
        except Exception as exc:
            self.logger.error("Unexpected error in Drive API request to %s: %s", url, exc)
            return {
                "status_code": 0,
                "body": {},
                "error": str(exc),
            }
