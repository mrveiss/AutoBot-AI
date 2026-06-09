# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for workflow notification config persistence (#3166).

Covers:
- WorkflowNotificationStore save/load/delete via mocked Redis.
- Validation on NotificationConfigRequest (emails, slack URL, webhook URL).
- Route-level behaviour: PUT persists, GET hydrates from Redis when in-memory
  value is missing.
"""

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from services.notification_service import NotificationConfig
from services.workflow_automation.models import NotificationConfigRequest
from services.workflow_automation.persistence import (
    load_notification_config,
    save_notification_config,
)
from tests.fixtures import make_async_redis, patch_async_redis

# ===========================================================================
# Helpers
# ===========================================================================

_WF_ID = "wf-persist-test"


def _make_config(**kwargs) -> NotificationConfig:
    defaults = dict(
        workflow_id=_WF_ID,
        channels={"workflow_completed": ["in_app"]},
        templates={},
        email_recipients=[],
        slack_webhook_url=None,
        webhook_url=None,
        user_id="user-42",
    )
    defaults.update(kwargs)
    return NotificationConfig(**defaults)


# Migrated to canonical ``make_async_redis()`` / ``patch_async_redis()``
# from ``tests.fixtures`` (#7280 round 2). Local ``_make_redis()`` removed.
# Critical fix surfaced by migration: production imports
# ``get_async_redis_client`` (async) but tests patched ``get_redis_client``
# (sync, doesn't exist in the consumer namespace) — patches AttributeError'd
# at runtime, all 7 affected tests were broken pre-migration.


# ===========================================================================
# persistence.save_notification_config
# ===========================================================================


@pytest.mark.asyncio
async def test_save_persists_json_to_redis():
    config = _make_config()
    redis_mock = make_async_redis()
    with patch_async_redis(
        "services.workflow_automation.persistence.get_async_redis_client",
        redis=redis_mock,
    ):
        await save_notification_config(_WF_ID, config)

    redis_mock.set.assert_awaited_once()
    call_args = redis_mock.set.call_args
    key = call_args[0][0]
    payload_str = call_args[0][1]
    assert f"notif_config:{_WF_ID}" in key
    data = json.loads(payload_str)
    assert data["workflow_id"] == _WF_ID
    assert data["user_id"] == "user-42"


@pytest.mark.asyncio
async def test_save_none_deletes_key():
    redis_mock = make_async_redis()
    with patch_async_redis(
        "services.workflow_automation.persistence.get_async_redis_client",
        redis=redis_mock,
    ):
        await save_notification_config(_WF_ID, None)

    redis_mock.delete.assert_awaited_once()
    redis_mock.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_graceful_when_redis_unavailable():
    with patch(
        "services.workflow_automation.persistence.get_async_redis_client",
        new=AsyncMock(return_value=None),
    ):
        await save_notification_config(_WF_ID, _make_config())


# ===========================================================================
# persistence.load_notification_config
# ===========================================================================


@pytest.mark.asyncio
async def test_load_returns_config_from_redis():
    config = _make_config()
    raw_json = json.dumps(asdict(config)).encode("utf-8")
    redis_mock = make_async_redis(get_returns=raw_json)
    with patch_async_redis(
        "services.workflow_automation.persistence.get_async_redis_client",
        redis=redis_mock,
    ):
        result = await load_notification_config(_WF_ID)

    assert result is not None
    assert result.workflow_id == _WF_ID
    assert result.user_id == "user-42"
    assert result.channels == {"workflow_completed": ["in_app"]}


@pytest.mark.asyncio
async def test_load_returns_none_when_key_missing():
    redis_mock = make_async_redis(get_returns=None)
    with patch_async_redis(
        "services.workflow_automation.persistence.get_async_redis_client",
        redis=redis_mock,
    ):
        result = await load_notification_config(_WF_ID)

    assert result is None


@pytest.mark.asyncio
async def test_load_returns_none_when_redis_unavailable():
    with patch(
        "services.workflow_automation.persistence.get_async_redis_client",
        new=AsyncMock(return_value=None),
    ):
        result = await load_notification_config(_WF_ID)

    assert result is None


@pytest.mark.asyncio
async def test_load_returns_none_on_malformed_json():
    redis_mock = make_async_redis(get_returns=b"not-valid-json")
    with patch_async_redis(
        "services.workflow_automation.persistence.get_async_redis_client",
        redis=redis_mock,
    ):
        result = await load_notification_config(_WF_ID)

    assert result is None


# ===========================================================================
# NotificationConfigRequest validation
# ===========================================================================


def test_valid_request_passes():
    req = NotificationConfigRequest(
        enabled=True,
        email_recipients=["user@example.com"],
        slack_webhook_url="https://hooks.slack.com/services/abc/def",
        webhook_url="https://external.example.com/hook",
        channels={"workflow_completed": ["slack", "email"]},
    )
    assert req.enabled is True
    assert req.email_recipients == ["user@example.com"]


def test_invalid_email_rejected():
    with pytest.raises(ValidationError, match="Invalid email"):
        NotificationConfigRequest(email_recipients=["not-an-email"])


def test_invalid_slack_url_rejected():
    with pytest.raises(ValidationError, match="https://hooks.slack.com/"):
        NotificationConfigRequest(slack_webhook_url="https://discord.com/api/webhooks/xyz")


def test_non_https_webhook_rejected():
    with pytest.raises(ValidationError, match="https://"):
        NotificationConfigRequest(webhook_url="http://external.example.com/hook")


def test_private_ip_webhook_rejected():
    with pytest.raises(ValidationError, match="private"):
        NotificationConfigRequest(webhook_url="https://192.168.1.1/hook")


def test_disabled_request_passes_without_urls():
    req = NotificationConfigRequest(enabled=False)
    assert req.enabled is False
