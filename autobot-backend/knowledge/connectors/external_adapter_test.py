# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for ExternalConnectorAdapter (Issue #8150).

All subprocess calls are mocked -- no real connector packages are required.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.connectors.external_adapter import ExternalConnectorAdapter
from knowledge.connectors.models import ConnectorConfig, SyncResult


def _adapter_config(extra_config: dict | None = None) -> ConnectorConfig:
    base = {
        "entrypoint": "/opt/connectors/github/main.py",
        "source_config": {"token": "ghp_test"},
        "selected_streams": ["issues"],
        "field_map": {
            "issues": {
                "title": "title",
                "body": "body",
                "metadata": ["url", "created_at"],
            }
        },
    }
    if extra_config:
        base.update(extra_config)
    return ConnectorConfig(
        connector_id="ext-test-001",
        connector_type="external_adapter",
        name="Test External Adapter",
        config=base,
    )


def _make_process_mock(stdout_lines: list[str], stderr_lines: list[str] | None = None):
    """Build an AsyncMock that looks like asyncio.Process with streaming stdout."""
    proc = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.kill = MagicMock()

    async def _async_iter_stdout():
        for line in stdout_lines:
            yield (line + "\n").encode("utf-8")

    async def _async_iter_stderr():
        for line in stderr_lines or []:
            yield (line + "\n").encode("utf-8")

    stdout_mock = MagicMock()
    stdout_mock.__aiter__ = lambda self: _async_iter_stdout()
    stderr_mock = MagicMock()
    stderr_mock.__aiter__ = lambda self: _async_iter_stderr()

    proc.stdout = stdout_mock
    proc.stderr = stderr_mock
    return proc


@pytest.fixture
def adapter():
    return ExternalConnectorAdapter(_adapter_config())


# ------------------------------------------------------------------
# test_connection
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_returns_true_on_succeeded(adapter):
    check_msg = json.dumps(
        {
            "type": "CONNECTION_STATUS",
            "connectionStatus": {"status": "SUCCEEDED"},
        }
    )
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(
            (check_msg + "\n").encode("utf-8"),
            b"",
        )
    )
    proc.kill = MagicMock()
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await adapter.test_connection()
    assert result is True


@pytest.mark.asyncio
async def test_connection_returns_false_on_failed(adapter):
    check_msg = json.dumps(
        {
            "type": "CONNECTION_STATUS",
            "connectionStatus": {"status": "FAILED", "message": "Invalid token"},
        }
    )
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(
            (check_msg + "\n").encode("utf-8"),
            b"",
        )
    )
    proc.kill = MagicMock()
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await adapter.test_connection()
    assert result is False


@pytest.mark.asyncio
async def test_connection_returns_false_on_exception(adapter):
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("not found")):
        result = await adapter.test_connection()
    assert result is False


@pytest.mark.asyncio
async def test_connection_logs_stderr_as_warning(adapter):
    check_msg = json.dumps(
        {
            "type": "CONNECTION_STATUS",
            "connectionStatus": {"status": "SUCCEEDED"},
        }
    )
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(
            (check_msg + "\n").encode("utf-8"),
            b"warning: something\n",
        )
    )
    proc.kill = MagicMock()
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch.object(adapter.logger, "warning") as mock_warn:
            await adapter.test_connection()
    mock_warn.assert_called()


# ------------------------------------------------------------------
# sync -- RECORD messages
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_record_messages_ingested(adapter):
    record_msg = json.dumps(
        {
            "type": "RECORD",
            "stream": "issues",
            "record": {"data": {"title": "Bug report", "body": "Details here", "url": "https://example.com"}},
        }
    )
    proc = _make_process_mock([record_msg])
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch.object(adapter, "_ingest_content", new=AsyncMock()) as mock_ingest:
            with patch.object(adapter, "_load_state", new=AsyncMock(return_value=None)):
                result = await adapter.sync(incremental=False)
    assert result.added == 1
    assert not result.errors
    mock_ingest.assert_called_once()


@pytest.mark.asyncio
async def test_sync_state_messages_persisted(adapter):
    state_msg = json.dumps(
        {
            "type": "STATE",
            "state": {"data": {"cursor": "2026-01-01T00:00:00Z"}},
        }
    )
    proc = _make_process_mock([state_msg])
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch.object(adapter, "_save_state", new=AsyncMock()) as mock_save:
            with patch.object(adapter, "_load_state", new=AsyncMock(return_value=None)):
                result = await adapter.sync(incremental=False)
    mock_save.assert_called_once_with({"cursor": "2026-01-01T00:00:00Z"})


@pytest.mark.asyncio
async def test_sync_trace_messages_recorded_as_errors(adapter):
    trace_msg = json.dumps(
        {
            "type": "TRACE",
            "trace": {"error": {"message": "Connection refused"}},
        }
    )
    proc = _make_process_mock([trace_msg])
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch.object(adapter, "_load_state", new=AsyncMock(return_value=None)):
            result = await adapter.sync(incremental=False)
    assert any("Connection refused" in e for e in result.errors)


@pytest.mark.asyncio
async def test_sync_incremental_passes_state_arg(adapter):
    saved_state = {"cursor": "abc123"}
    proc = _make_process_mock([])
    captured_cmd = []

    async def capture(*args, **kwargs):
        captured_cmd.extend(args)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=capture):
        with patch.object(adapter, "_load_state", new=AsyncMock(return_value=saved_state)):
            await adapter.sync(incremental=True)

    assert "--state" in captured_cmd


# ------------------------------------------------------------------
# field_map conversion
# ------------------------------------------------------------------


def test_convert_record_maps_title_and_body(adapter):
    data = {"title": "My Issue", "body": "Description", "url": "https://github.com/issue/1"}
    content = adapter._convert_record("issues", data)
    assert content is not None
    assert "My Issue" in content.content
    assert "Description" in content.content
    assert content.metadata.get("url") == "https://github.com/issue/1"


def test_convert_record_unmapped_fields_appended_as_json(adapter):
    data = {"title": "My Issue", "body": "Body", "extra_field": "surprise_value"}
    content = adapter._convert_record("issues", data)
    assert content is not None
    assert "surprise_value" in content.content


def test_convert_record_returns_none_for_empty_data(adapter):
    content = adapter._convert_record("issues", {})
    assert content is None


# ------------------------------------------------------------------
# discover_sources
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_sources_filters_by_selected_streams(adapter):
    catalog_msg = json.dumps(
        {
            "type": "CATALOG",
            "catalog": {
                "streams": [
                    {"stream": {"name": "issues", "json_schema": {}}},
                    {"stream": {"name": "pull_requests", "json_schema": {}}},
                ]
            },
        }
    )
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(
            (catalog_msg + "\n").encode("utf-8"),
            b"",
        )
    )
    proc.kill = MagicMock()
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        sources = await adapter.discover_sources()
    # Only "issues" is in selected_streams
    assert len(sources) == 1
    assert sources[0].name == "issues"


# ------------------------------------------------------------------
# fetch_content
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_content_raises_not_implemented(adapter):
    with pytest.raises(NotImplementedError):
        await adapter.fetch_content("any-source-id")


# ------------------------------------------------------------------
# detect_changes
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_changes_returns_empty_list(adapter):
    changes = await adapter.detect_changes()
    assert changes == []
