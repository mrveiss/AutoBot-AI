# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for LLC outbound PM sync (GH#8257)."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llc.sync.outbound_sync import (
    LLCOutboundSyncService,
    map_status,
    map_work_item_type,
    _DEFAULT_STATUS_MAP,
)


# ──────────────────────────────────────────────────────────────────────────────
# Field mapping
# ──────────────────────────────────────────────────────────────────────────────


class TestMapWorkItemType:
    def test_jira_epic(self):
        assert map_work_item_type("jira", "epic") == "Epic"

    def test_jira_pbi(self):
        assert map_work_item_type("jira", "pbi") == "Story"

    def test_jira_task(self):
        assert map_work_item_type("jira", "task") == "Task"

    def test_jira_bug(self):
        assert map_work_item_type("jira", "bug") == "Bug"

    def test_jira_subtask(self):
        assert map_work_item_type("jira", "subtask") == "Sub-task"

    def test_trello_all_map_to_card(self):
        for wt in ("epic", "feature", "pbi", "task", "bug", "subtask", "spike", "risk"):
            assert map_work_item_type("trello", wt) == "card"

    def test_asana_all_map_to_task(self):
        for wt in ("epic", "feature", "pbi", "task", "bug"):
            assert map_work_item_type("asana", wt) == "task"

    def test_azure_epic(self):
        assert map_work_item_type("azure_devops", "epic") == "Epic"

    def test_azure_pbi(self):
        assert map_work_item_type("azure_devops", "pbi") == "Product Backlog Item"

    def test_unknown_pm_type_returns_task(self):
        assert map_work_item_type("unknown_pm", "task") == "Task"

    def test_unknown_llc_type_returns_task(self):
        assert map_work_item_type("jira", "unknown_type") == "Task"


class TestMapStatus:
    def test_default_done(self):
        assert map_status({}, "done") == "Done"

    def test_default_in_progress(self):
        assert map_status({}, "in_progress") == "In Progress"

    def test_custom_map_overrides_default(self):
        cfg = {"status_map": {"done": "Resolved"}}
        assert map_status(cfg, "done") == "Resolved"

    def test_custom_map_missing_key_falls_back(self):
        cfg = {"status_map": {"done": "Resolved"}}
        assert map_status(cfg, "in_review") == _DEFAULT_STATUS_MAP["in_review"]

    def test_unknown_status_passthrough(self):
        assert map_status({}, "some_custom_status") == "some_custom_status"


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_jira_create():
    from llc.sync.outbound_sync import _dispatch_to_jira

    pm_config = {
        "base_url": "https://example.atlassian.net",
        "username": "user@example.com",
        "api_key": "api_key_here",
        "project_key": "PROJ",
    }
    payload = {"title": "Fix bug", "description": "Details", "type": "task"}

    with patch(
        "llc.sync.outbound_sync.JiraIntegration"
    ) as MockJira:
        instance = AsyncMock()
        instance.execute_action = AsyncMock(return_value={"issue": {"key": "PROJ-1"}})
        MockJira.return_value = instance

        await _dispatch_to_jira(pm_config, "created", payload)

        instance.execute_action.assert_called_once_with(
            "create_issue",
            {
                "project_key": "PROJ",
                "summary": "Fix bug",
                "description": "Details",
                "issue_type": "Task",
            },
        )


@pytest.mark.asyncio
async def test_dispatch_trello_create():
    from llc.sync.outbound_sync import _dispatch_to_trello

    pm_config = {
        "api_key": "trello_key",
        "token": "trello_token",
        "list_id": "list_abc",
    }
    payload = {"title": "New card", "description": "desc", "type": "task"}

    with patch("llc.sync.outbound_sync.TrelloIntegration") as MockTrello:
        instance = AsyncMock()
        instance.execute_action = AsyncMock(return_value={"card": {}})
        MockTrello.return_value = instance

        await _dispatch_to_trello(pm_config, "created", payload)

        instance.execute_action.assert_called_once_with(
            "create_card",
            {"list_id": "list_abc", "name": "New card", "description": "desc"},
        )


@pytest.mark.asyncio
async def test_dispatch_asana_completed():
    from llc.sync.outbound_sync import _dispatch_to_asana

    pm_config = {
        "token": "asana_token",
        "workspace_gid": "ws_gid",
    }
    payload = {"type": "task", "external_id": "task_gid_123"}

    with patch("llc.sync.outbound_sync.AsanaIntegration") as MockAsana:
        instance = AsyncMock()
        instance.execute_action = AsyncMock(return_value={"task": {}})
        MockAsana.return_value = instance

        await _dispatch_to_asana(pm_config, "completed", payload)

        instance.execute_action.assert_called_once_with(
            "update_task",
            {"task_gid": "task_gid_123", "completed": True},
        )


# ──────────────────────────────────────────────────────────────────────────────
# Service: sync failure is non-fatal
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_failure_is_logged_not_raised():
    """Connector exception must not propagate — only logged to activity log."""
    service = LLCOutboundSyncService()

    mock_org = MagicMock()
    mock_org.external_pm_type = "jira"
    mock_org.external_pm_config = "encrypted_blob"

    with (
        patch("llc.sync.outbound_sync.AsyncSessionLocal") as MockSession,
        patch("llc.sync.outbound_sync._decrypt_pm_config", return_value={"project_key": "P"}),
        patch("llc.sync.outbound_sync._dispatch_to_jira", side_effect=RuntimeError("boom")),
        patch("llc.sync.outbound_sync._log_sync_failed", new_callable=AsyncMock) as mock_log,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_result = MagicMock()
        mock_result.one_or_none = MagicMock(
            return_value=("jira", "encrypted_blob")
        )
        mock_session.execute = AsyncMock(return_value=mock_result)
        MockSession.return_value = mock_session

        await service._sync(
            company_id="00000000-0000-0000-0000-000000000001",
            work_item_id="wi_001",
            event="created",
            payload={"title": "Test"},
        )

        mock_log.assert_called_once()
        call_args = mock_log.call_args[0]
        assert call_args[0] == "00000000-0000-0000-0000-000000000001"
        assert "boom" in call_args[3]


@pytest.mark.asyncio
async def test_sync_skips_when_no_pm_configured():
    """Companies without PM config must be silently skipped."""
    service = LLCOutboundSyncService()

    with patch("llc.sync.outbound_sync.AsyncSessionLocal") as MockSession:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_result = MagicMock()
        mock_result.one_or_none = MagicMock(return_value=("none", None))
        mock_session.execute = AsyncMock(return_value=mock_result)
        MockSession.return_value = mock_session

        with patch("llc.sync.outbound_sync._DISPATCHER", {}) as mock_dispatcher:
            await service._sync(
                company_id="00000000-0000-0000-0000-000000000002",
                work_item_id="wi_002",
                event="created",
                payload={},
            )
            # No dispatcher call should have happened


# ──────────────────────────────────────────────────────────────────────────────
# Integration: create work item → verify outbound sync call
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_integration_create_triggers_jira_sync():
    """End-to-end: Redis message → Jira create_issue called with correct payload."""
    service = LLCOutboundSyncService()

    company_id = "00000000-0000-0000-0000-000000000003"
    work_item_id = "wi_003"
    pm_config = {
        "base_url": "https://example.atlassian.net",
        "username": "bot@example.com",
        "api_key": "secret",
        "project_key": "ABO",
    }

    message = {
        "channel": b"llc:work_item:created",
        "data": json.dumps(
            {
                "company_id": company_id,
                "work_item_id": work_item_id,
                "title": "Implement feature X",
                "type": "pbi",
                "description": "As a user…",
            }
        ).encode("utf-8"),
    }

    with (
        patch("llc.sync.outbound_sync.AsyncSessionLocal") as MockSession,
        patch(
            "llc.sync.outbound_sync._decrypt_pm_config",
            return_value=pm_config,
        ),
        patch("llc.sync.outbound_sync.JiraIntegration") as MockJira,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_result = MagicMock()
        mock_result.one_or_none = MagicMock(return_value=("jira", "blob"))
        mock_session.execute = AsyncMock(return_value=mock_result)
        MockSession.return_value = mock_session

        jira_instance = AsyncMock()
        jira_instance.execute_action = AsyncMock(return_value={"issue": {"key": "ABO-42"}})
        MockJira.return_value = jira_instance

        await service._handle_message(message)

        jira_instance.execute_action.assert_called_once()
        action, params = jira_instance.execute_action.call_args[0]
        assert action == "create_issue"
        assert params["project_key"] == "ABO"
        assert params["summary"] == "Implement feature X"
        assert params["issue_type"] == "Story"
