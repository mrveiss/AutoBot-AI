# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test topology detection for SLM self-sync (#9195).

Verifies that code_sync routes to SSH rsync for remote code sources
and Ansible for local sources, fixing the multi-server regression.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.code_sync import sync_node
from models.database import Node
from models.schemas import NodeSyncRequest


@pytest.mark.asyncio
async def test_sync_node_remote_code_source_uses_ssh_rsync():
    """Test that sync_node uses SSH rsync when code source is remote (#9195)."""
    # Mock database and node
    mock_db = MagicMock()
    mock_node = Node(
        node_id="slm-node-1",
        hostname="slm.example.com",
        ip_address="10.0.1.10",
        ssh_user="autobot",
        ssh_port=22,
    )
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_node)))

    # Mock settings
    with patch("api.code_sync.settings") as mock_settings:
        mock_settings.external_url = "http://10.0.1.10"

        # Mock code source connection info (remote)
        with patch("api.code_sync._fetch_code_source_connection_info") as mock_fetch:
            mock_fetch.return_value = (
                "192.168.1.100",  # remote IP
                "autobot",
                "/home/autobot/code",
            )

            # Mock is_local_ip to return False (remote)
            with patch("autobot_shared.network_utils.is_local_ip", return_value=False):
                # Mock _sync_slm_from_code_source to verify it's called
                with patch("api.code_sync.asyncio.create_task") as mock_create_task:
                    request = NodeSyncRequest(restart=True)

                    # Call sync_node
                    response = await sync_node(
                        node_id="slm-node-1",
                        request=request,
                        db=mock_db,
                        _={"username": "admin"},
                    )

                    # Verify _sync_slm_from_code_source was scheduled (not _ansible_self_update)
                    mock_create_task.assert_called_once()
                    task_coro = mock_create_task.call_args[0][0]
                    assert (
                        task_coro.__name__ == "_sync_slm_from_code_source"
                    ), "Expected _sync_slm_from_code_source for remote code source"

                    assert response.success is True
                    assert "remote code source" in response.message


@pytest.mark.asyncio
async def test_sync_node_local_code_source_uses_ansible():
    """Test that sync_node uses Ansible when code source is local (#9195)."""
    # Mock database and node
    mock_db = MagicMock()
    mock_node = Node(
        node_id="slm-node-1",
        hostname="slm.example.com",
        ip_address="10.0.1.10",
        ssh_user="autobot",
        ssh_port=22,
    )
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_node)))

    # Mock settings
    with patch("api.code_sync.settings") as mock_settings:
        mock_settings.external_url = "http://10.0.1.10"

        # Mock code source connection info (local)
        with patch("api.code_sync._fetch_code_source_connection_info") as mock_fetch:
            mock_fetch.return_value = (
                "10.0.1.10",  # local IP (same as SLM)
                "autobot",
                "/opt/autobot/code_source",
            )

            # Mock is_local_ip to return True (local)
            with patch("autobot_shared.network_utils.is_local_ip", return_value=True):
                # Mock _ansible_self_update to verify it's called
                with patch("api.code_sync.asyncio.create_task") as mock_create_task:
                    request = NodeSyncRequest(restart=True)

                    # Call sync_node
                    response = await sync_node(
                        node_id="slm-node-1",
                        request=request,
                        db=mock_db,
                        _={"username": "admin"},
                    )

                    # Verify _ansible_self_update was scheduled
                    mock_create_task.assert_called_once()
                    task_coro = mock_create_task.call_args[0][0]
                    assert (
                        task_coro.__name__ == "_ansible_self_update"
                    ), "Expected _ansible_self_update for local code source"

                    assert response.success is True
                    assert "Ansible" in response.message
