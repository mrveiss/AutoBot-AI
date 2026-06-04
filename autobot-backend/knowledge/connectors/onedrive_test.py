# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Tests for OneDrive/SharePoint Knowledge Connector (Issue #9004)
"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.onedrive import OneDriveConnector


@pytest.fixture
def onedrive_config():
    """Sample OneDrive connector config."""
    return ConnectorConfig(
        connector_id="test-onedrive-1",
        connector_type="onedrive",
        name="Test OneDrive",
        config={
            "token": "test_access_token_12345",
            "source_type": "onedrive",
            "folder_path": "/",
            "sync_subfolders": True,
            "max_file_size_mb": 100,
            "supported_extensions": [".docx", ".pdf", ".md"],
        },
        enabled=True,
        verification_mode="collaborative",
    )


@pytest.fixture
def sharepoint_config():
    """Sample SharePoint connector config."""
    return ConnectorConfig(
        connector_id="test-sharepoint-1",
        connector_type="onedrive",
        name="Test SharePoint",
        config={
            "token": "test_access_token_67890",
            "source_type": "sharepoint",
            "site_id": "test-site-id-123",
            "drive_id": "test-drive-id-456",
            "folder_path": "/",
            "sync_subfolders": True,
        },
        enabled=True,
        verification_mode="collaborative",
    )


class TestOneDriveConnector:
    """Tests for OneDriveConnector."""

    def test_init_onedrive(self, onedrive_config):
        """Test OneDrive connector initialization."""
        connector = OneDriveConnector(onedrive_config)
        assert connector.connector_type == "onedrive"
        assert connector.tier == 2
        assert connector._source_type == "onedrive"
        assert connector._token == "test_access_token_12345"
        assert connector._folder_path == "/"
        assert connector._sync_subfolders is True
        assert connector.max_concurrency == 4

    def test_init_sharepoint(self, sharepoint_config):
        """Test SharePoint connector initialization."""
        connector = OneDriveConnector(sharepoint_config)
        assert connector._source_type == "sharepoint"
        assert connector._site_id == "test-site-id-123"
        assert connector._drive_id == "test-drive-id-456"

    def test_auth_schema(self):
        """Test auth schema declaration."""
        from autobot_shared.auth import BearerAuth

        assert OneDriveConnector.auth_schema() == BearerAuth

    def test_output_schema(self):
        """Test output schema structure."""
        schema = OneDriveConnector.output_schema()
        assert schema["type"] == "object"
        assert "file_id" in schema["required"]
        assert "file_name" in schema["required"]
        assert "file_extension" in schema["required"]
        assert "last_modified" in schema["required"]
        assert "properties" in schema

    @pytest.mark.asyncio
    async def test_get_drive_url_onedrive_default(self, onedrive_config):
        """Test drive URL generation for default OneDrive."""
        connector = OneDriveConnector(onedrive_config)
        url = await connector._get_drive_url()
        assert url == "https://graph.microsoft.com/v1.0/me/drive"

    @pytest.mark.asyncio
    async def test_get_drive_url_onedrive_specific(self, onedrive_config):
        """Test drive URL generation for specific OneDrive drive."""
        onedrive_config.config["drive_id"] = "test-drive-123"
        connector = OneDriveConnector(onedrive_config)
        url = await connector._get_drive_url()
        assert url == "https://graph.microsoft.com/v1.0/drives/test-drive-123"

    @pytest.mark.asyncio
    async def test_get_drive_url_sharepoint(self, sharepoint_config):
        """Test drive URL generation for SharePoint."""
        connector = OneDriveConnector(sharepoint_config)
        url = await connector._get_drive_url()
        assert url == "https://graph.microsoft.com/v1.0/sites/test-site-id-123/drives/test-drive-id-456"

    @pytest.mark.asyncio
    async def test_get_drive_url_sharepoint_no_site_id(self, onedrive_config):
        """Test drive URL generation fails without site_id for SharePoint."""
        onedrive_config.config["source_type"] = "sharepoint"
        connector = OneDriveConnector(onedrive_config)
        with pytest.raises(ValueError, match="site_id required"):
            await connector._get_drive_url()

    def test_get_file_extension(self):
        """Test file extension extraction."""
        assert OneDriveConnector._get_file_extension("document.docx") == ".docx"
        assert OneDriveConnector._get_file_extension("report.pdf") == ".pdf"
        assert OneDriveConnector._get_file_extension("readme.md") == ".md"
        assert OneDriveConnector._get_file_extension("no_extension") == ""
        assert OneDriveConnector._get_file_extension("multiple.dots.txt") == ".txt"

    @pytest.mark.asyncio
    async def test_test_connection_success(self, onedrive_config):
        """Test successful connection test."""
        connector = OneDriveConnector(onedrive_config)

        with patch.object(connector, "_graph_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "status_code": 200,
                "body": {"id": "test-drive-id", "name": "OneDrive"},
            }

            result = await connector.test_connection()
            assert result is True
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, onedrive_config):
        """Test failed connection test."""
        connector = OneDriveConnector(onedrive_config)

        with patch.object(connector, "_graph_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "status_code": 401,
                "body": {"error": {"message": "Unauthorized"}},
            }

            result = await connector.test_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_file_to_source_info(self, onedrive_config):
        """Test conversion of Graph API file item to SourceInfo."""
        connector = OneDriveConnector(onedrive_config)

        file_item = {
            "id": "file-123",
            "name": "document.docx",
            "size": 12345,
            "lastModifiedDateTime": "2026-06-04T08:00:00Z",
            "webUrl": "https://onedrive.live.com/file-123",
        }

        source_info = connector._file_to_source_info(file_item)

        assert source_info is not None
        assert source_info.source_id == "onedrive:test-onedrive-1:file:file-123"
        assert source_info.name == "document.docx"
        assert "document.docx" in source_info.description
        assert source_info.metadata["file_id"] == "file-123"
        assert source_info.metadata["file_extension"] == ".docx"

    @pytest.mark.asyncio
    async def test_file_to_source_info_unsupported_extension(self, onedrive_config):
        """Test that unsupported file extensions return None."""
        connector = OneDriveConnector(onedrive_config)

        file_item = {
            "id": "file-456",
            "name": "video.mp4",  # Not in supported_extensions
            "size": 50000000,
            "lastModifiedDateTime": "2026-06-04T08:00:00Z",
        }

        source_info = connector._file_to_source_info(file_item)
        assert source_info is None

    @pytest.mark.asyncio
    async def test_classify_change_initial_sync(self, onedrive_config):
        """Test change classification when since is None (initial sync)."""
        connector = OneDriveConnector(onedrive_config)

        source_id = "onedrive:test-onedrive-1:file:file-123"
        last_modified = "2026-06-04T08:00:00Z"

        change = await connector._classify_change(source_id, last_modified, since=None)

        assert change is not None
        assert change.source_id == source_id
        assert change.change_type == "added"
        assert change.details["last_modified"] == last_modified

    @pytest.mark.asyncio
    async def test_max_concurrency_default(self, onedrive_config):
        """Test default max_concurrency is 4."""
        connector = OneDriveConnector(onedrive_config)
        assert connector.max_concurrency == 4

    @pytest.mark.asyncio
    async def test_max_concurrency_override(self, onedrive_config):
        """Test max_concurrency can be overridden in config."""
        onedrive_config.max_concurrency = 8
        connector = OneDriveConnector(onedrive_config)
        assert connector.max_concurrency == 8
