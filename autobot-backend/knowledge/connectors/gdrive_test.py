# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for Google Drive Knowledge Connector (Issue #9003)
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.time_utils import now_utc
from knowledge.connectors.gdrive import GoogleDriveConnector
from knowledge.connectors.models import ConnectorConfig


@pytest.fixture
def mock_config():
    """Minimal ConnectorConfig for testing."""
    return ConnectorConfig(
        connector_id="test-gdrive-123",
        connector_type="gdrive",
        name="Test Google Drive",
        config={
            "token": "mock_access_token",
            "source_type": "mydrive",
            "sync_subfolders": True,
            "max_file_size_mb": 100,
        },
    )


@pytest.fixture
def connector(mock_config):
    """GoogleDriveConnector instance with mocked config."""
    return GoogleDriveConnector(mock_config)


class TestGoogleDriveConnector:
    """Test suite for GoogleDriveConnector."""

    def test_connector_registration(self):
        """Test that connector is registered in the registry."""
        from knowledge.connectors.registry import ConnectorRegistry

        assert "gdrive" in ConnectorRegistry._connectors
        assert ConnectorRegistry._connectors["gdrive"] == GoogleDriveConnector

    def test_connector_tier(self):
        """Test that connector has correct tier (OAuth2 required)."""
        assert GoogleDriveConnector.tier == 2

    def test_auth_schema(self):
        """Test that connector declares BearerAuth schema."""
        from autobot_shared.auth import BearerAuth

        assert GoogleDriveConnector.auth_schema() == BearerAuth

    def test_output_schema(self):
        """Test that connector declares output metadata schema."""
        schema = GoogleDriveConnector.output_schema()
        assert schema["type"] == "object"
        assert "file_id" in schema["required"]
        assert "file_name" in schema["required"]
        assert "file_extension" in schema["required"]
        assert "last_modified" in schema["required"]

    def test_max_concurrency_default(self, connector):
        """Test default max_concurrency is 4."""
        assert connector.max_concurrency == 4

    def test_max_concurrency_override(self, mock_config):
        """Test max_concurrency can be overridden in config."""
        mock_config.max_concurrency = 8
        connector = GoogleDriveConnector(mock_config)
        assert connector.max_concurrency == 8

    @pytest.mark.asyncio
    async def test_test_connection_success(self, connector):
        """Test successful connection test."""
        mock_response = {
            "status_code": 200,
            "body": {"user": {"displayName": "Test User"}},
        }

        with patch.object(connector, "_drive_request", return_value=mock_response):
            result = await connector.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, connector):
        """Test failed connection test."""
        mock_response = {
            "status_code": 401,
            "body": {"error": {"message": "Invalid credentials"}},
        }

        with patch.object(connector, "_drive_request", return_value=mock_response):
            result = await connector.test_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_discover_sources(self, connector):
        """Test source discovery."""
        mock_files = [
            {
                "id": "file1",
                "name": "document.gdoc",
                "mimeType": "application/vnd.google-apps.document",
                "size": "1024",
                "modifiedTime": "2026-06-04T10:00:00Z",
                "webViewLink": "https://docs.google.com/document/d/file1",
                "parents": ["root"],
                "driveId": "drive1",
            },
            {
                "id": "file2",
                "name": "spreadsheet.gsheet",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "size": "2048",
                "modifiedTime": "2026-06-04T11:00:00Z",
                "webViewLink": "https://docs.google.com/spreadsheets/d/file2",
                "parents": ["root"],
                "driveId": "drive1",
            },
        ]

        with patch.object(connector, "_list_all_files", return_value=mock_files):
            sources = await connector.discover_sources()
            assert len(sources) == 2
            assert sources[0].source_id == "gdrive:test-gdrive-123:file:file1"
            assert sources[0].name == "document.gdoc"
            assert sources[1].source_id == "gdrive:test-gdrive-123:file:file2"
            assert sources[1].name == "spreadsheet.gsheet"

    @pytest.mark.asyncio
    async def test_fetch_content_google_doc(self, connector):
        """Test fetching Google Doc content."""
        file_id = "doc123"
        source_id = f"gdrive:{connector.config.connector_id}:file:{file_id}"

        mock_metadata = {
            "status_code": 200,
            "body": {
                "id": file_id,
                "name": "Test Document.gdoc",
                "mimeType": "application/vnd.google-apps.document",
                "size": "0",
                "modifiedTime": "2026-06-04T10:00:00Z",
                "webViewLink": "https://docs.google.com/document/d/doc123",
                "parents": ["root"],
                "driveId": "drive1",
            },
        }

        mock_content = {
            "status_code": 200,
            "content": b"This is the content of the Google Doc.",
        }

        async def mock_request(method, url, **kwargs):
            if "/export" in url:
                return mock_content
            return mock_metadata

        with patch.object(connector, "_drive_request", side_effect=mock_request):
            with patch("knowledge.connectors.gdrive._store_ts", return_value=None):
                result = await connector.fetch_content(source_id)

                assert result is not None
                assert result.source_id == source_id
                assert "This is the content of the Google Doc" in result.content
                assert result.metadata["file_id"] == file_id
                assert result.metadata["file_name"] == "Test Document.gdoc"
                assert result.metadata["file_extension"] == ".gdoc"

    @pytest.mark.asyncio
    async def test_fetch_content_pdf(self, connector):
        """Test fetching PDF content."""
        file_id = "pdf123"
        source_id = f"gdrive:{connector.config.connector_id}:file:{file_id}"

        mock_metadata = {
            "status_code": 200,
            "body": {
                "id": file_id,
                "name": "Test Document.pdf",
                "mimeType": "application/pdf",
                "size": "10240",
                "modifiedTime": "2026-06-04T10:00:00Z",
                "webViewLink": "https://drive.google.com/file/d/pdf123",
                "parents": ["root"],
                "driveId": "drive1",
            },
        }

        # Mock PDF content (simplified - real PDF would be binary)
        mock_content = {
            "status_code": 200,
            "content": b"%PDF-1.4\n...minimal pdf content...",
        }

        async def mock_request(method, url, **kwargs):
            if "alt=media" in str(kwargs.get("params", {})):
                return mock_content
            return mock_metadata

        with patch.object(connector, "_drive_request", side_effect=mock_request):
            with patch("knowledge.connectors.gdrive._extract_text_from_pdf", return_value="Extracted PDF text"):
                with patch("knowledge.connectors.gdrive._store_ts", return_value=None):
                    result = await connector.fetch_content(source_id)

                    assert result is not None
                    assert result.source_id == source_id
                    assert "Extracted PDF text" in result.content
                    assert result.metadata["file_extension"] == ".pdf"

    @pytest.mark.asyncio
    async def test_detect_changes_initial_sync(self, connector):
        """Test change detection on initial sync (no timestamp)."""
        mock_files = [
            {
                "id": "file1",
                "name": "document.gdoc",
                "mimeType": "application/vnd.google-apps.document",
                "size": "1024",
                "modifiedTime": "2026-06-04T10:00:00Z",
                "webViewLink": "https://docs.google.com/document/d/file1",
                "parents": ["root"],
                "driveId": "drive1",
            },
        ]

        with patch.object(connector, "_list_all_files", return_value=mock_files):
            with patch("knowledge.connectors.gdrive._load_ts", return_value=None):
                changes = await connector.detect_changes(since=None)

                assert len(changes) == 1
                assert changes[0].source_id == "gdrive:test-gdrive-123:file:file1"
                assert changes[0].change_type == "added"

    @pytest.mark.asyncio
    async def test_detect_changes_modified_file(self, connector):
        """Test change detection for modified file."""
        mock_files = [
            {
                "id": "file1",
                "name": "document.gdoc",
                "mimeType": "application/vnd.google-apps.document",
                "size": "1024",
                "modifiedTime": "2026-06-04T12:00:00Z",  # Newer timestamp
                "webViewLink": "https://docs.google.com/document/d/file1",
                "parents": ["root"],
                "driveId": "drive1",
            },
        ]

        old_timestamp = "2026-06-04T10:00:00Z"  # Older timestamp

        with patch.object(connector, "_list_all_files", return_value=mock_files):
            with patch("knowledge.connectors.gdrive._load_ts", return_value=old_timestamp):
                changes = await connector.detect_changes(since=now_utc())

                assert len(changes) == 1
                assert changes[0].source_id == "gdrive:test-gdrive-123:file:file1"
                assert changes[0].change_type == "modified"

    def test_get_file_extension_gdoc(self):
        """Test file extension detection for Google Doc."""
        ext = GoogleDriveConnector._get_file_extension("My Document", "application/vnd.google-apps.document")
        assert ext == ".gdoc"

    def test_get_file_extension_gsheet(self):
        """Test file extension detection for Google Sheet."""
        ext = GoogleDriveConnector._get_file_extension("My Spreadsheet", "application/vnd.google-apps.spreadsheet")
        assert ext == ".gsheet"

    def test_get_file_extension_regular_file(self):
        """Test file extension detection for regular file."""
        ext = GoogleDriveConnector._get_file_extension("document.pdf", "application/pdf")
        assert ext == ".pdf"

    def test_get_content_type_gdoc(self):
        """Test content type mapping for Google Doc."""
        ctype = GoogleDriveConnector._get_content_type(".gdoc", "application/vnd.google-apps.document")
        assert ctype == "application/vnd.google-apps.document"

    def test_get_content_type_pdf(self):
        """Test content type mapping for PDF."""
        ctype = GoogleDriveConnector._get_content_type(".pdf", "application/pdf")
        assert ctype == "application/pdf"

    @pytest.mark.asyncio
    async def test_list_all_files_pagination(self, connector):
        """Test file listing with pagination."""
        # First page response
        page1_response = {
            "status_code": 200,
            "body": {
                "files": [
                    {
                        "id": "file1",
                        "name": "doc1.gdoc",
                        "mimeType": "application/vnd.google-apps.document",
                        "size": "1024",
                        "modifiedTime": "2026-06-04T10:00:00Z",
                        "webViewLink": "https://docs.google.com/document/d/file1",
                        "parents": ["root"],
                        "driveId": "drive1",
                    },
                ],
                "nextPageToken": "page2token",
            },
        }

        # Second page response
        page2_response = {
            "status_code": 200,
            "body": {
                "files": [
                    {
                        "id": "file2",
                        "name": "doc2.gdoc",
                        "mimeType": "application/vnd.google-apps.document",
                        "size": "2048",
                        "modifiedTime": "2026-06-04T11:00:00Z",
                        "webViewLink": "https://docs.google.com/document/d/file2",
                        "parents": ["root"],
                        "driveId": "drive1",
                    },
                ],
                # No nextPageToken - end of pagination
            },
        }

        call_count = 0

        async def mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page1_response
            return page2_response

        with patch.object(connector, "_drive_request", side_effect=mock_request):
            with patch.object(connector, "_list_subfolders", return_value=[]):
                files = await connector._list_all_files()

                assert len(files) == 2
                assert files[0]["id"] == "file1"
                assert files[1]["id"] == "file2"
                assert call_count == 2  # Two pages fetched
