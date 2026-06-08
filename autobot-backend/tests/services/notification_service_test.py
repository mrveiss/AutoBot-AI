# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for NotificationService, NotificationStore, and helpers (#2157)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.notification_service import (
    NotificationChannel,
    NotificationConfig,
    NotificationEvent,
    NotificationService,
    NotificationStore,
)
from tests.fixtures.mocks import make_async_redis

# ===========================================================================
# Helpers
# ===========================================================================


def _make_config(**kwargs) -> NotificationConfig:
    """Return a NotificationConfig with sensible defaults."""
    defaults = dict(
        workflow_id="wf-test",
        channels={},
        email_recipients=[],
        slack_webhook_url=None,
        webhook_url=None,
        user_id=None,
    )
    defaults.update(kwargs)
    return NotificationConfig(**defaults)


# ===========================================================================
# NotificationChannel enum
# ===========================================================================


class TestNotificationChannel:
    def test_email_value(self):
        assert NotificationChannel.EMAIL.value == "email"

    def test_slack_value(self):
        assert NotificationChannel.SLACK.value == "slack"

    def test_webhook_value(self):
        assert NotificationChannel.WEBHOOK.value == "webhook"

    def test_in_app_value(self):
        assert NotificationChannel.IN_APP.value == "in_app"


# ===========================================================================
# NotificationEvent enum
# ===========================================================================


class TestNotificationEvent:
    def test_workflow_completed_value(self):
        assert NotificationEvent.WORKFLOW_COMPLETED.value == "workflow_completed"

    def test_workflow_failed_value(self):
        assert NotificationEvent.WORKFLOW_FAILED.value == "workflow_failed"

    def test_step_failed_value(self):
        assert NotificationEvent.STEP_FAILED.value == "step_failed"

    def test_approval_needed_value(self):
        assert NotificationEvent.APPROVAL_NEEDED.value == "approval_needed"


# ===========================================================================
# render_template
# ===========================================================================


class TestRenderTemplate:
    def _svc(self):
        return NotificationService()

    def test_workflow_completed_default(self):
        svc = self._svc()
        result = svc.render_template(
            NotificationEvent.WORKFLOW_COMPLETED.value,
            {"workflow_id": "wf-42"},
        )
        assert "wf-42" in result

    def test_workflow_failed_includes_error(self):
        svc = self._svc()
        result = svc.render_template(
            NotificationEvent.WORKFLOW_FAILED.value,
            {"workflow_id": "wf-99", "error": "timeout"},
        )
        assert "timeout" in result
        assert "wf-99" in result

    def test_step_failed_includes_step_name(self):
        svc = self._svc()
        result = svc.render_template(
            NotificationEvent.STEP_FAILED.value,
            {"workflow_id": "wf-1", "step_name": "deploy", "error": "oops"},
        )
        assert "deploy" in result

    def test_approval_needed_includes_workflow_id(self):
        svc = self._svc()
        result = svc.render_template(
            NotificationEvent.APPROVAL_NEEDED.value,
            {"workflow_id": "wf-approval", "step_name": "review"},
        )
        assert "wf-approval" in result

    def test_unknown_event_returns_fallback(self):
        svc = self._svc()
        result = svc.render_template("unknown_event", {"workflow_id": "wf-x"})
        assert "wf-x" in result

    def test_missing_key_does_not_raise(self):
        """safe_substitute leaves unreplaced placeholders as-is; no KeyError."""
        svc = self._svc()
        result = svc.render_template(
            NotificationEvent.WORKFLOW_FAILED.value,
            {"workflow_id": "wf-1"},  # missing 'error'
        )
        assert isinstance(result, str)


# ===========================================================================
# NotificationService.send — channel dispatch
# ===========================================================================


class TestSendDispatch:
    def _svc(self):
        return NotificationService()

    @pytest.mark.asyncio
    async def test_no_channels_configured_does_nothing(self):
        svc = self._svc()
        config = _make_config(channels={})
        # Should return without error
        await svc.send(
            event=NotificationEvent.WORKFLOW_COMPLETED,
            workflow_id="wf-0",
            payload={},
            config=config,
        )

    @pytest.mark.asyncio
    async def test_email_channel_calls_send_email(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.WORKFLOW_COMPLETED.value: [NotificationChannel.EMAIL.value]},
            email_recipients=["user@example.com"],
        )
        with patch.object(svc, "_send_email", new_callable=AsyncMock) as mock_email:
            await svc.send(
                event=NotificationEvent.WORKFLOW_COMPLETED,
                workflow_id="wf-email",
                payload={},
                config=config,
            )
        mock_email.assert_awaited_once()
        _, kwargs = mock_email.call_args
        assert kwargs["to"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_slack_channel_calls_send_slack(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.WORKFLOW_FAILED.value: [NotificationChannel.SLACK.value]},
            slack_webhook_url="https://hooks.slack.com/T123",
        )
        with patch.object(svc, "_send_slack", new_callable=AsyncMock) as mock_slack:
            await svc.send(
                event=NotificationEvent.WORKFLOW_FAILED,
                workflow_id="wf-slack",
                payload={"error": "crash"},
                config=config,
            )
        mock_slack.assert_awaited_once()
        args = mock_slack.call_args[0]
        assert args[0] == "https://hooks.slack.com/T123"

    @pytest.mark.asyncio
    async def test_webhook_channel_calls_send_webhook(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.STEP_FAILED.value: [NotificationChannel.WEBHOOK.value]},
            webhook_url="https://myapp.example.com/notify",
        )
        with patch.object(svc, "_send_webhook", new_callable=AsyncMock) as mock_wh:
            await svc.send(
                event=NotificationEvent.STEP_FAILED,
                workflow_id="wf-wh",
                payload={"step_name": "build", "error": "fail"},
                config=config,
            )
        mock_wh.assert_awaited_once()
        url_arg = mock_wh.call_args[0][0]
        assert url_arg == "https://myapp.example.com/notify"

    @pytest.mark.asyncio
    async def test_in_app_channel_calls_send_in_app(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.APPROVAL_NEEDED.value: [NotificationChannel.IN_APP.value]},
            user_id="user-007",
        )
        with patch.object(svc, "_send_in_app", new_callable=AsyncMock) as mock_ia:
            await svc.send(
                event=NotificationEvent.APPROVAL_NEEDED,
                workflow_id="wf-ia",
                payload={"step_name": "review"},
                config=config,
            )
        mock_ia.assert_awaited_once()
        _, kwargs = mock_ia.call_args
        assert kwargs["user_id"] == "user-007"

    @pytest.mark.asyncio
    async def test_multiple_email_recipients_each_get_email(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.WORKFLOW_COMPLETED.value: [NotificationChannel.EMAIL.value]},
            email_recipients=["a@x.com", "b@x.com"],
        )
        with patch.object(svc, "_send_email", new_callable=AsyncMock) as mock_email:
            await svc.send(
                event=NotificationEvent.WORKFLOW_COMPLETED,
                workflow_id="wf-multi",
                payload={},
                config=config,
            )
        assert mock_email.await_count == 2

    @pytest.mark.asyncio
    async def test_unknown_channel_is_skipped_without_raising(self):
        svc = self._svc()
        config = _make_config(channels={NotificationEvent.WORKFLOW_COMPLETED.value: ["carrier_pigeon"]})
        await svc.send(
            event=NotificationEvent.WORKFLOW_COMPLETED,
            workflow_id="wf-unknown",
            payload={},
            config=config,
        )  # must not raise

    @pytest.mark.asyncio
    async def test_channel_failure_does_not_block_others(self):
        """If EMAIL fails, IN_APP must still be dispatched."""
        svc = self._svc()
        config = _make_config(
            channels={
                NotificationEvent.WORKFLOW_FAILED.value: [
                    NotificationChannel.EMAIL.value,
                    NotificationChannel.IN_APP.value,
                ]
            },
            email_recipients=["err@x.com"],
            user_id="user-fallback",
        )
        with patch.object(svc, "_send_email", new_callable=AsyncMock, side_effect=OSError("SMTP down")):
            with patch.object(svc, "_send_in_app", new_callable=AsyncMock) as mock_ia:
                await svc.send(
                    event=NotificationEvent.WORKFLOW_FAILED,
                    workflow_id="wf-fault",
                    payload={"error": "crash"},
                    config=config,
                )
        mock_ia.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_slack_missing_webhook_url_skips_silently(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.WORKFLOW_COMPLETED.value: [NotificationChannel.SLACK.value]},
            slack_webhook_url=None,
        )
        with patch.object(svc, "_send_slack", new_callable=AsyncMock) as mock_slack:
            await svc.send(
                event=NotificationEvent.WORKFLOW_COMPLETED,
                workflow_id="wf-no-slack",
                payload={},
                config=config,
            )
        mock_slack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_webhook_missing_url_skips_silently(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.WORKFLOW_COMPLETED.value: [NotificationChannel.WEBHOOK.value]},
            webhook_url=None,
        )
        with patch.object(svc, "_send_webhook", new_callable=AsyncMock) as mock_wh:
            await svc.send(
                event=NotificationEvent.WORKFLOW_COMPLETED,
                workflow_id="wf-no-wh",
                payload={},
                config=config,
            )
        mock_wh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_in_app_missing_user_id_skips_silently(self):
        svc = self._svc()
        config = _make_config(
            channels={NotificationEvent.APPROVAL_NEEDED.value: [NotificationChannel.IN_APP.value]},
            user_id=None,
        )
        with patch.object(svc, "_send_in_app", new_callable=AsyncMock) as mock_ia:
            await svc.send(
                event=NotificationEvent.APPROVAL_NEEDED,
                workflow_id="wf-no-uid",
                payload={},
                config=config,
            )
        mock_ia.assert_not_awaited()


# ===========================================================================
# _send_webhook
# ===========================================================================


class TestSendWebhook:
    def _svc(self):
        return NotificationService()

    @pytest.mark.asyncio
    async def test_posts_json_payload(self):
        svc = self._svc()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.notification_service.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            await svc._send_webhook("https://example.com/hook", {"key": "val"})

        mock_session.post.assert_called_once()
        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs["json"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_raises_on_4xx_response(self):
        import aiohttp as _aiohttp

        svc = self._svc()
        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.text = AsyncMock(return_value="Bad Request")
        mock_resp.raise_for_status = MagicMock(side_effect=_aiohttp.ClientResponseError(None, None, status=400))
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.notification_service.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            with pytest.raises(_aiohttp.ClientResponseError):
                await svc._send_webhook("https://example.com/hook", {})


# ===========================================================================
# _send_slack delegates to _send_webhook
# ===========================================================================


class TestSendSlack:
    @pytest.mark.asyncio
    async def test_slack_delegates_to_webhook(self):
        svc = NotificationService()
        with patch.object(svc, "_send_webhook", new_callable=AsyncMock) as mock_wh:
            await svc._send_slack("https://hooks.slack.com/abc", "hello")
        mock_wh.assert_awaited_once_with("https://hooks.slack.com/abc", {"text": "hello"})


# ===========================================================================
# NotificationStore.store
# ===========================================================================


class TestNotificationStoreStore:
    @pytest.mark.asyncio
    async def test_returns_notification_id_on_success(self):
        store = NotificationStore()
        mock_redis = make_async_redis()
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await store.store(
                user_id="u1",
                event="workflow_completed",
                workflow_id="wf-1",
                message="Done",
            )
        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_calls_lpush_with_list_key(self):
        store = NotificationStore()
        mock_redis = make_async_redis()
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await store.store(
                user_id="u2",
                event="workflow_completed",
                workflow_id="wf-2",
                message="Done",
            )
        assert mock_redis.lpush.called
        key_arg = mock_redis.lpush.call_args[0][0]
        assert key_arg == "notifications:u2"

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_unavailable(self):
        store = NotificationStore()
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await store.store(
                user_id="u3",
                event="workflow_failed",
                workflow_id="wf-3",
                message="Fail",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self):
        store = NotificationStore()
        mock_redis = make_async_redis()
        mock_redis.lpush = AsyncMock(side_effect=ConnectionError("redis gone"))
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await store.store(user_id="u4", event="step_failed", workflow_id="wf-4", message="Err")
        assert result is None

    @pytest.mark.asyncio
    async def test_stored_record_contains_expected_fields(self):
        store = NotificationStore()
        stored_records: list = []

        async def _capture_set(key, value, **kwargs):
            if key.startswith("notification:"):
                stored_records.append(json.loads(value))
            return True

        mock_redis = make_async_redis()
        mock_redis.set = AsyncMock(side_effect=_capture_set)

        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await store.store(
                user_id="u5",
                event="approval_needed",
                workflow_id="wf-5",
                message="Approve",
            )

        assert len(stored_records) == 1
        rec = stored_records[0]
        assert rec["user_id"] == "u5"
        assert rec["event"] == "approval_needed"
        assert rec["workflow_id"] == "wf-5"
        assert rec["message"] == "Approve"
        assert rec["read"] is False
        assert "id" in rec
        assert "timestamp" in rec


# ===========================================================================
# NotificationStore.list
# ===========================================================================


class TestNotificationStoreList:
    @pytest.mark.asyncio
    async def test_returns_parsed_records(self):
        store = NotificationStore()
        record = {
            "id": "n1",
            "user_id": "u1",
            "event": "workflow_completed",
            "workflow_id": "wf-1",
            "message": "Done",
            "timestamp": 1000.0,
            "read": False,
        }
        raw = [json.dumps(record).encode()]
        mock_redis = make_async_redis(lrange_returns=raw)
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            results = await store.list("u1")
        assert len(results) == 1
        assert results[0]["id"] == "n1"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_redis_unavailable(self):
        store = NotificationStore()
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=None,
        ):
            results = await store.list("u1")
        assert results == []

    @pytest.mark.asyncio
    async def test_limit_is_passed_to_lrange(self):
        store = NotificationStore()
        mock_redis = make_async_redis()
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await store.list("u1", limit=10)
        mock_redis.lrange.assert_awaited_once_with("notifications:u1", 0, 9)

    @pytest.mark.asyncio
    async def test_malformed_record_is_skipped(self):
        store = NotificationStore()
        raw = [b"not-json", json.dumps({"id": "ok"}).encode()]
        mock_redis = make_async_redis(lrange_returns=raw)
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            results = await store.list("u1")
        assert len(results) == 1
        assert results[0]["id"] == "ok"

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_redis_error(self):
        store = NotificationStore()
        mock_redis = make_async_redis()
        mock_redis.lrange = AsyncMock(side_effect=ConnectionError("redis gone"))
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            results = await store.list("u1")
        assert results == []


# ===========================================================================
# NotificationStore.mark_read
# ===========================================================================


class TestNotificationStoreMarkRead:
    def _make_record(self, notification_id: str = "n1") -> bytes:
        return json.dumps(
            {
                "id": notification_id,
                "user_id": "u1",
                "event": "workflow_completed",
                "workflow_id": "wf-1",
                "message": "Done",
                "timestamp": 1000.0,
                "read": False,
            }
        ).encode()

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        store = NotificationStore()
        mock_redis = make_async_redis(get_returns=self._make_record())
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await store.mark_read("n1")
        assert result is True

    @pytest.mark.asyncio
    async def test_updated_record_has_read_true(self):
        store = NotificationStore()
        written_records: list = []

        async def _capture_set(key, value, **kwargs):
            written_records.append(json.loads(value))
            return True

        mock_redis = make_async_redis(get_returns=self._make_record())
        mock_redis.set = AsyncMock(side_effect=_capture_set)

        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await store.mark_read("n1")

        assert len(written_records) == 1
        assert written_records[0]["read"] is True

    @pytest.mark.asyncio
    async def test_returns_false_when_record_not_found(self):
        store = NotificationStore()
        mock_redis = make_async_redis(get_returns=None)
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await store.mark_read("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_redis_unavailable(self):
        store = NotificationStore()
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await store.mark_read("n1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_redis_error(self):
        store = NotificationStore()
        mock_redis = make_async_redis(get_returns=self._make_record())
        mock_redis.set = AsyncMock(side_effect=ConnectionError("redis gone"))
        with patch(
            "services.notification_service.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await store.mark_read("n1")
        assert result is False


# ===========================================================================
# _send_in_app integration (NotificationService -> NotificationStore)
# ===========================================================================


class TestSendInApp:
    @pytest.mark.asyncio
    async def test_delegates_to_store(self):
        mock_store = AsyncMock(spec=NotificationStore)
        mock_store.store = AsyncMock(return_value="notif-id-1")
        svc = NotificationService(store=mock_store)

        await svc._send_in_app(
            user_id="u1",
            event=NotificationEvent.WORKFLOW_COMPLETED.value,
            workflow_id="wf-1",
            message="Done",
        )

        mock_store.store.assert_awaited_once_with(
            user_id="u1",
            event=NotificationEvent.WORKFLOW_COMPLETED.value,
            workflow_id="wf-1",
            message="Done",
        )

    @pytest.mark.asyncio
    async def test_handles_store_returning_none(self):
        mock_store = AsyncMock(spec=NotificationStore)
        mock_store.store = AsyncMock(return_value=None)
        svc = NotificationService(store=mock_store)

        # Must not raise
        await svc._send_in_app(
            user_id="u2",
            event=NotificationEvent.WORKFLOW_FAILED.value,
            workflow_id="wf-2",
            message="Fail",
        )
