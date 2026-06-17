# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Nextcloud Documents Knowledge Connector (Issue #9005 / MVA-2039)

Indexes documents from self-hosted Nextcloud instances into the AutoBot
knowledge base via WebDAV protocol.

Config keys:
    nextcloud_url (str): Base URL of the Nextcloud instance (e.g., "https://cloud.example.com").
                         Required.
    username (str): Nextcloud username for WebDAV authentication. Required.
    password (str): Nextcloud app password or account password. Required.
    folders (list[str]): List of folder paths to sync (e.g., ["/Documents", "/Notes"]).
                         Empty list = sync all accessible files. Default [].
    file_extensions (list[str]): File extensions to index (without dots).
                                  Default ["pdf", "docx", "odt", "md", "txt"].
    max_file_size_mb (int): Skip files larger than this size in MB. Default 50.
    per_page (int): Number of items per WebDAV request. Default 100.
    max_concurrency (int): Parallel source fetches. Default 4.

Nextcloud WebDAV endpoint: {nextcloud_url}/remote.php/dav/files/{username}/
"""

from datetime import datetime
from typing import List, Optional
from urllib.parse import quote, urljoin, urlparse

import aiohttp
import defusedxml.ElementTree as ET

from autobot_shared.auth import BasicAuth
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from knowledge.connectors.base import AbstractConnector, RetryableError
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

# WebDAV namespaces
NS_DAV = "{DAV:}"
NS_OC = "{http://owncloud.org/ns}"
NS_NC = "{http://nextcloud.org/ns}"

# Default supported file extensions
DEFAULT_FILE_EXTENSIONS = ["pdf", "docx", "odt", "md", "txt"]

# Redis key prefix for storing last-modified timestamps
_REDIS_TS_PREFIX = "connector:nextcloud:ts:"
_REDIS_TS_TTL = 86400 * 30  # 30 days


def _is_supported_file(path: str, extensions: List[str]) -> bool:
    """Check if file extension is in the supported list."""
    if not path:
        return False
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ext in extensions


async def _load_ts(connector_id: str, source_id: str) -> Optional[str]:
    """Load last-modified timestamp from Redis for incremental sync."""
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
    """Store last-modified timestamp to Redis for incremental sync."""
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(database="knowledge")
        key = f"{_REDIS_TS_PREFIX}{connector_id}:{source_id}"
        result = redis.set(key, ts, ex=_REDIS_TS_TTL)
        if hasattr(result, "__await__"):
            await result
    except Exception as exc:
        logger.warning("Redis store_ts failed for %s: %s", source_id, exc)


@ConnectorRegistry.register("nextcloud")
class NextcloudConnector(AbstractConnector):
    """Knowledge connector for Nextcloud instances via WebDAV.

    Indexes documents from specified folders (or all accessible files) into
    the AutoBot knowledge base. Each file becomes one KB fact keyed by
    ``nextcloud:{connector_id}:file:{url_encoded_path}``.

    Supports incremental sync via WebDAV ``getlastmodified`` property comparison
    cached in Redis.
    """

    connector_type = "nextcloud"
    tier = 2  # Requires credentials (app password)
    max_concurrency = 4

    @classmethod
    def auth_schema(cls) -> type:
        return BasicAuth

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._base_url: str = cfg.get("nextcloud_url", "").rstrip("/")
        self._username: str = cfg.get("username", "")
        self._password: str = cfg.get("password", "")
        self._folders: List[str] = cfg.get("folders", [])
        self._file_extensions: List[str] = [
            ext.lower().lstrip(".") for ext in cfg.get("file_extensions", DEFAULT_FILE_EXTENSIONS)
        ]
        self._max_file_size_mb: int = int(cfg.get("max_file_size_mb", 50))
        self._max_file_size_bytes = self._max_file_size_mb * 1024 * 1024
        self._per_page: int = int(cfg.get("per_page", 100))

        if not self._base_url:
            raise ValueError("nextcloud_url is required")
        if not self._username:
            raise ValueError("username is required")
        if not self._password:
            raise ValueError("password is required")

        # Construct WebDAV endpoint: {base_url}/remote.php/dav/files/{username}/
        self._webdav_base = urljoin(self._base_url, f"/remote.php/dav/files/{quote(self._username)}/")

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Test WebDAV connection with OPTIONS request."""
        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(self._username, self._password)
                timeout = aiohttp.ClientTimeout(total=30.0)
                async with session.options(self._webdav_base, auth=auth, timeout=timeout) as resp:
                    if resp.status in (200, 204):
                        self.logger.info("Nextcloud connection test successful: %s", self._webdav_base)
                        return True
                    self.logger.warning("Nextcloud test_connection failed: HTTP %d", resp.status)
                    return False
        except Exception as exc:
            self.logger.error("Nextcloud test_connection error: %s", exc)
            return False

    async def discover_sources(self) -> List[SourceInfo]:
        """Discover all supported files in configured folders via WebDAV PROPFIND."""
        sources: List[SourceInfo] = []

        if self._folders:
            # Sync specific folders
            for folder in self._folders:
                sources.extend(await self._discover_folder(folder))
        else:
            # Sync all accessible files from root
            sources.extend(await self._discover_folder("/"))

        self.logger.info("Discovered %d sources from Nextcloud %s", len(sources), self._base_url)
        return sources

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Fetch file content via WebDAV GET."""
        # source_id format: nextcloud:{connector_id}:file:{url_encoded_path}
        parts = source_id.split(":", 3)
        if len(parts) < 4 or parts[2] != "file":
            self.logger.error("Malformed source_id: %s", source_id)
            return None

        encoded_path = parts[3]
        file_url = urljoin(self._webdav_base, encoded_path)

        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(self._username, self._password)
                timeout = aiohttp.ClientTimeout(total=300.0)
                async with session.get(file_url, auth=auth, timeout=timeout) as resp:
                    if resp.status == 200:
                        content_bytes = await resp.read()
                        content_type = resp.headers.get("Content-Type", "application/octet-stream")

                        # Decode text content
                        try:
                            content = content_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            # For binary files (PDF, DOCX), return as base64 or skip
                            self.logger.warning("Binary content for %s - may need extraction", source_id)
                            content = content_bytes.decode("utf-8", errors="replace")

                        await _store_ts(
                            self.config.connector_id,
                            source_id,
                            resp.headers.get("Last-Modified", ""),
                        )

                        return ContentResult(
                            source_id=source_id,
                            content=content,
                            content_type=content_type,
                            metadata={"url": file_url},
                        )
                    elif resp.status == 404:
                        self.logger.warning("File not found: %s", file_url)
                        return None
                    else:
                        raise RetryableError(f"WebDAV GET failed: HTTP {resp.status}", resp.status)
        except aiohttp.ClientError as exc:
            self.logger.error("WebDAV GET error for %s: %s", source_id, exc)
            raise RetryableError(str(exc))

    async def detect_changes(self, since: Optional[datetime] = None) -> List[ChangeInfo]:
        """Detect changed files by comparing last-modified timestamps."""
        changes: List[ChangeInfo] = []

        # Re-discover all sources and compare timestamps
        sources = await self.discover_sources()
        for src in sources:
            stored_ts = await _load_ts(self.config.connector_id, src.source_id)
            current_ts = src.last_modified.isoformat()

            if not stored_ts:
                # New file
                changes.append(
                    ChangeInfo(
                        source_id=src.source_id,
                        change_type="added",
                        timestamp=src.last_modified,
                        details={"path": src.path},
                    )
                )
            elif stored_ts != current_ts:
                # Modified file
                changes.append(
                    ChangeInfo(
                        source_id=src.source_id,
                        change_type="modified",
                        timestamp=src.last_modified,
                        details={"path": src.path},
                    )
                )

        self.logger.info("Detected %d changes in Nextcloud", len(changes))
        return changes

    # ------------------------------------------------------------------
    # WebDAV helpers
    # ------------------------------------------------------------------

    async def _discover_folder(self, folder_path: str) -> List[SourceInfo]:
        """Discover files in a specific folder via WebDAV PROPFIND."""
        folder_path = folder_path.strip().lstrip("/")
        folder_url = urljoin(self._webdav_base, quote(folder_path))

        # WebDAV PROPFIND request body
        propfind_body = """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">
  <d:prop>
    <d:getlastmodified/>
    <d:getcontentlength/>
    <d:getcontenttype/>
    <d:resourcetype/>
    <d:displayname/>
  </d:prop>
</d:propfind>"""

        sources: List[SourceInfo] = []

        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(self._username, self._password)
                timeout = aiohttp.ClientTimeout(total=60.0)
                headers = {
                    "Content-Type": "application/xml",
                    "Depth": "infinity",  # Recursive listing
                }

                async with session.request(
                    "PROPFIND",
                    folder_url,
                    auth=auth,
                    headers=headers,
                    data=propfind_body,
                    timeout=timeout,
                ) as resp:
                    if resp.status != 207:  # Multi-Status
                        self.logger.warning(
                            "WebDAV PROPFIND failed for %s: HTTP %d",
                            folder_path,
                            resp.status,
                        )
                        return sources

                    xml_data = await resp.text()
                    sources = self._parse_propfind_response(xml_data)

        except Exception as exc:
            self.logger.error("WebDAV PROPFIND error for %s: %s", folder_path, exc)

        return sources

    def _parse_propfind_response(self, xml_data: str) -> List[SourceInfo]:
        """Parse WebDAV PROPFIND XML response into SourceInfo objects."""
        sources: List[SourceInfo] = []

        try:
            root = ET.fromstring(xml_data)
            ns = {"d": "DAV:"}

            for response in root.findall(".//d:response", ns):
                href_elem = response.find("d:href", ns)
                if href_elem is None or not href_elem.text:
                    continue

                href = href_elem.text.strip()
                # Extract path from href (remove WebDAV base)
                parsed_href = urlparse(href)
                path = parsed_href.path

                # Skip if it's a collection (directory)
                resourcetype = response.find(".//d:resourcetype/d:collection", ns)
                if resourcetype is not None:
                    continue

                # Check file extension
                if not _is_supported_file(path, self._file_extensions):
                    continue

                # Get properties
                propstat = response.find("d:propstat", ns)
                if propstat is None:
                    continue

                prop = propstat.find("d:prop", ns)
                if prop is None:
                    continue

                # Extract file metadata
                size_elem = prop.find("d:getcontentlength", ns)
                size_bytes = int(size_elem.text) if size_elem is not None and size_elem.text else 0

                # Skip large files
                if size_bytes > self._max_file_size_bytes:
                    self.logger.debug("Skipping large file %s (%d MB)", path, size_bytes / 1024 / 1024)
                    continue

                modified_elem = prop.find("d:getlastmodified", ns)
                last_modified_str = modified_elem.text if modified_elem is not None and modified_elem.text else ""
                last_modified = self._parse_http_date(last_modified_str) if last_modified_str else now_utc()

                content_type_elem = prop.find("d:getcontenttype", ns)
                content_type = (
                    content_type_elem.text
                    if content_type_elem is not None and content_type_elem.text
                    else "application/octet-stream"
                )

                displayname_elem = prop.find("d:displayname", ns)
                display_name = (
                    displayname_elem.text
                    if displayname_elem is not None and displayname_elem.text
                    else path.rsplit("/", 1)[-1]
                )

                # Create source_id
                source_id = f"nextcloud:{self.config.connector_id}:file:{quote(path, safe='')}"

                sources.append(
                    SourceInfo(
                        source_id=source_id,
                        name=display_name,
                        path=path,
                        content_type=content_type,
                        size_bytes=size_bytes,
                        last_modified=last_modified,
                        metadata={"href": href},
                    )
                )

        except ET.ParseError as exc:
            self.logger.error("Failed to parse WebDAV PROPFIND response: %s", exc)

        return sources

    @staticmethod
    def _parse_http_date(date_str: str) -> datetime:
        """Parse HTTP date format (RFC 2822) to datetime."""
        from email.utils import parsedate_to_datetime

        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            return now_utc()
