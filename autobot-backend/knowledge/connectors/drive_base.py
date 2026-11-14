# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared core of the file-drive connectors (Issue #18557, slice 3; parent #17312).

``gdrive.py`` and ``onedrive.py`` carried identical ``discover_sources``,
``auth_schema`` and ``max_concurrency``, near-identical ``output_schema`` and the
same common config parsing.  Change detection already lives in
``AbstractConnector._detect_changes_via_file_listing()`` (#12659); this class
adds the rest.  Provider hooks: ``drive_label`` (schema descriptions),
``_extra_output_properties`` (provider-only metadata fields),
``_default_extensions`` and ``_file_to_source_info`` / ``_list_all_files``.
``fetch_content`` stays per provider (only ~0.6 similar).
"""

from typing import Any, Dict, List

from autobot_shared.auth import BearerAuth
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import ConnectorConfig, SourceInfo

_DEFAULT_MAX_CONCURRENCY = 4
_DEFAULT_MAX_FILE_SIZE_MB = 100


class DriveConnector(AbstractConnector):
    """Bearer-token file-drive connector base (Google Drive, OneDrive)."""

    #: Provider name used in schema descriptions, e.g. ``"OneDrive"``.
    drive_label: str = ""
    #: Extensions indexed when the config does not set ``supported_extensions``.
    _default_extensions: List[str] = []
    #: Provider-only ``ContentResult.metadata`` schema properties (appended last).
    _extra_output_properties: Dict[str, Any] = {}

    @classmethod
    def auth_schema(cls) -> type:
        """Drive providers require a bearer token (OAuth2 access token)."""
        return BearerAuth

    @classmethod
    def output_schema(cls) -> Dict[str, Any]:
        """Return JSONSchema for ContentResult.metadata."""
        properties: Dict[str, Any] = {
            "file_id": {"type": "string", "description": "%s file ID" % cls.drive_label},
            "file_name": {"type": "string", "description": "File name with extension"},
            "file_extension": {"type": "string", "description": "File extension (e.g., .docx)"},
            "file_path": {"type": "string", "description": "Full path in drive"},
            "file_size": {"type": "integer", "description": "File size in bytes"},
            "last_modified": {"type": "string", "description": "ISO-8601 last modified datetime"},
            "web_url": {"type": "string", "description": "Web URL to view file"},
            "drive_id": {"type": "string", "description": "Drive ID"},
        }
        properties.update(cls._extra_output_properties)
        return {
            "type": "object",
            "required": ["file_id", "file_name", "file_extension", "last_modified"],
            "properties": properties,
        }

    @property
    def max_concurrency(self) -> int:
        """Max parallel file fetches. Default 4."""
        cfg_val = self.config.max_concurrency
        return cfg_val if cfg_val is not None else _DEFAULT_MAX_CONCURRENCY

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._token: str = cfg.get("token", "")
        self._drive_id = cfg.get("drive_id")
        self._sync_subfolders: bool = cfg.get("sync_subfolders", True)
        self._max_file_size: int = cfg.get("max_file_size_mb", _DEFAULT_MAX_FILE_SIZE_MB) * 1024 * 1024
        self._supported_extensions: List[str] = cfg.get("supported_extensions", self._default_extensions)

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every supported file in the configured drive/folder."""
        files = await self._list_all_files()
        sources: List[SourceInfo] = []
        for file_item in files:
            source_info = self._file_to_source_info(file_item)
            if source_info:
                sources.append(source_info)
        return sources
