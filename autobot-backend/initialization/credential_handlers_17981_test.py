# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An unreadable stored credential gets one answer on every route (#17981 review)."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.error_boundaries.types import PassThroughError
from autobot_shared.field_encryption import FieldDecryptionError
from initialization.credential_handlers import CREDENTIAL_UNREADABLE, register_credential_handlers

_UNREADABLE = FieldDecryptionError("redis:autobot:settings:telegram_bot_token: stored value cannot be decrypted")


def test_the_error_passes_through_the_route_decorator():
    """``with_error_handling`` would otherwise turn it into a generic 500 before the handler sees it."""
    assert issubclass(FieldDecryptionError, PassThroughError)

    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="t", error_code_prefix="T")
    async def route():
        raise _UNREADABLE

    with pytest.raises(FieldDecryptionError):
        import asyncio

        asyncio.run(route())


def test_the_telegram_config_view_answers_like_the_webhook():
    """It used to be a 500 here and a 503 on the webhook for the same stored token."""
    from api import telegram_bot

    app = FastAPI()
    register_credential_handlers(app)
    app.include_router(telegram_bot.router, prefix="/api")
    app.dependency_overrides[check_admin_permission] = lambda: True
    with patch.object(telegram_bot, "get_telegram_bot_token", AsyncMock(side_effect=_UNREADABLE)):
        response = TestClient(app, raise_server_exceptions=False).get("/api/telegram/config")
    assert response.status_code == 503
    assert response.json() == {"detail": CREDENTIAL_UNREADABLE}


@pytest.mark.asyncio
async def test_the_poller_idles_and_logs_once(caplog):
    from services import telegram_polling

    telegram_polling._token_unreadable_reported = False
    with (
        patch.object(telegram_polling, "get_ingest_mode", AsyncMock(return_value=telegram_polling.INGEST_MODE_POLLING)),
        patch.object(telegram_polling, "get_redis_client", AsyncMock(return_value=MagicMock())),
        patch.object(telegram_polling.TelegramBotService, "from_redis", AsyncMock(side_effect=_UNREADABLE)),
        caplog.at_level(logging.ERROR),
    ):
        assert await telegram_polling.poll_once(MagicMock()) is None
        assert await telegram_polling.poll_once(MagicMock()) is None
    assert sum("stored bot token unreadable" in r.getMessage() for r in caplog.records) == 1


@pytest.mark.asyncio
async def test_outbound_sync_records_why_it_failed():
    from llc.sync.outbound_sync import LLCOutboundSyncService

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    result = MagicMock()
    result.one_or_none = MagicMock(return_value=("jira", "fe1.sealed"))
    session.execute = AsyncMock(return_value=result)
    with (
        patch("user_management.database.get_async_session_factory") as factory,
        patch("llc.sync.outbound_sync.open_pm_config", side_effect=FieldDecryptionError("organization:x:pm: bad")),
        patch("llc.sync.outbound_sync._log_sync_failed", new_callable=AsyncMock) as logged,
    ):
        factory.return_value.return_value = session
        await LLCOutboundSyncService()._sync(
            company_id="00000000-0000-0000-0000-000000000001", work_item_id="wi", event="created", payload={}
        )
    reason = logged.await_args.args[3]
    assert reason.startswith("credential unreadable: ") and "organization:x:pm" in reason
