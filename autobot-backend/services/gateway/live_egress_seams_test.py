# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Egress governance on the seams that actually send to people (#14270).

#14067 put the control on ``Gateway.send_message``, which is dormant — Gateway
init is commented out at ``initialization/lifespan.py`` — so the modules that
really put bytes on the wire crossed no gate and left no record.

Every test here drives the **producer**, not the governor. A test that asserts
``egress_governor`` is imported would pass while a new branch bypasses it; these
patch the governor to deny and assert nothing reaches the transport.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.gateway.egress_governor import EgressVerdict


def _deny(**_kwargs):
    return EgressVerdict(allowed=False, reason="denied by test", rule="approver")


def _allow(**_kwargs):
    return EgressVerdict(allowed=True, reason="ok", rule="audit-only")


class TestTelegramSeam:
    @pytest.mark.asyncio
    async def test_a_denied_send_never_reaches_the_transport(self):
        from services.telegram_bot_service import TelegramBotService

        svc = TelegramBotService.__new__(TelegramBotService)
        svc.bot_token = "t"
        svc.base_url = "https://example.invalid/botT"

        with patch("services.telegram_bot_service.egress_governor.evaluate", new=AsyncMock(side_effect=_deny)):
            with patch("services.telegram_bot_service.get_http_client") as http:
                result = await svc.send_message(chat_id="c1", text="hello")

        http.assert_not_called(), "a denied Telegram message was handed to the HTTP client"
        assert result["ok"] is False
        assert result["error"] == "egress_denied"

    @pytest.mark.asyncio
    async def test_the_alert_exemption_is_passed_through_not_ignored(self):
        """notification_service sends alerts through this same method.

        If the exemption were dropped, arming the policy would silence outage
        alerts and deadlock APPROVAL_NEEDED — the notification that an approval
        is needed would itself await approval.
        """
        from services.telegram_bot_service import TelegramBotService

        svc = TelegramBotService.__new__(TelegramBotService)
        svc.bot_token = "t"
        svc.base_url = "https://example.invalid/botT"

        spy = AsyncMock(side_effect=_allow)
        with patch("services.telegram_bot_service.egress_governor.evaluate", new=spy):
            with patch("services.telegram_bot_service.get_http_client"):
                await svc.send_message(chat_id="c1", text="alert", require_approval=False)

        assert spy.await_args.kwargs["require_approval"] is False


class TestWhatsAppSeam:
    def _integration(self):
        from integrations.base import IntegrationConfig
        from integrations.whatsapp_integration import WhatsAppIntegration

        return WhatsAppIntegration(
            IntegrationConfig(name="wa", provider="whatsapp", api_key="k", extra={"phone_number_id": "p"})
        )

    @pytest.mark.asyncio
    async def test_a_denied_text_message_never_reaches_the_api(self):
        wa = self._integration()
        wa.check_opt_in_status = AsyncMock(return_value={"opted_in": True})
        wa._make_request = AsyncMock()

        with patch("integrations.whatsapp_integration.egress_governor.evaluate", new=AsyncMock(side_effect=_deny)):
            result = await wa.send_text_message({"to": "+15551234567", "body": "hi"})

        wa._make_request.assert_not_awaited()
        assert result["error"] == "egress_denied"

    @pytest.mark.asyncio
    async def test_media_and_template_sends_are_governed_too(self):
        """#14270 named only send_text_message; three senders reach the wire."""
        wa = self._integration()
        wa.check_opt_in_status = AsyncMock(return_value={"opted_in": True})
        wa._make_request = AsyncMock()

        with patch("integrations.whatsapp_integration.egress_governor.evaluate", new=AsyncMock(side_effect=_deny)):
            media = await wa.send_media_message(
                {"to": "+15551234567", "media_type": "image", "media_url": "https://e.invalid/i.png"}
            )
            template = await wa.send_template_message({"to": "+15551234567", "template_name": "t"})

        wa._make_request.assert_not_awaited()
        assert media["error"] == "egress_denied"
        assert template["error"] == "egress_denied"

    @pytest.mark.asyncio
    async def test_the_recipient_is_masked_in_the_audit_record(self):
        """A phone number is PII and the audit record outlives the send."""
        wa = self._integration()
        wa.check_opt_in_status = AsyncMock(return_value={"opted_in": True})
        wa._make_request = AsyncMock()

        spy = AsyncMock(side_effect=_allow)
        with patch("integrations.whatsapp_integration.egress_governor.evaluate", new=spy):
            await wa.send_text_message({"to": "+15551234567", "body": "hi"})

        assert "5551234567" not in spy.await_args.kwargs["channel_id"]
        assert spy.await_args.kwargs["channel_id"].endswith("4567")

    @pytest.mark.asyncio
    async def test_mark_message_read_is_deliberately_not_governed(self):
        """Pins the exclusion so it stays a decision rather than drift.

        A read receipt is control traffic, not a message to a person. Gating it
        would make an armed policy stop acknowledging inbound messages.
        """
        wa = self._integration()
        wa._make_request = AsyncMock(return_value={"status_code": 200, "body": {}})

        spy = AsyncMock(side_effect=_deny)
        with patch("integrations.whatsapp_integration.egress_governor.evaluate", new=spy):
            await wa.mark_message_read({"message_id": "m1"})

        spy.assert_not_awaited()


class TestIntegrationCommunicationSeam:
    @pytest.mark.asyncio
    async def test_a_denied_send_is_refused_before_either_branch(self):
        """Covers the Teams webhook fallback as well as the MessagingProtocol path."""
        from fastapi import HTTPException

        from api import integration_communication as ic

        message = type("M", (), {"channel_id": "C1", "text": "hi"})()
        adapter = AsyncMock()

        with patch.object(ic, "_build_messaging_adapter", return_value=adapter):
            with patch.object(ic, "_create_config", return_value=object()):
                with patch.object(ic.egress_governor, "evaluate", new=AsyncMock(side_effect=_deny)):
                    with pytest.raises(HTTPException) as exc:
                        await ic.send_message("slack", "tok", message)

        assert exc.value.status_code == 403
        adapter.send_message.assert_not_awaited()
        adapter.execute_action.assert_not_awaited()


class TestNotificationAlertsAreAuditedButNeverBlocked:
    @pytest.mark.asyncio
    async def test_a_webhook_alert_is_recorded_with_the_exemption(self):
        from services.notification_service import NotificationService

        svc = NotificationService()
        spy = AsyncMock(side_effect=_allow)
        with patch("services.notification_service.egress_governor.evaluate", new=spy):
            with patch("autobot_shared.http_client.get_http_client"):
                try:
                    await svc._send_webhook("https://hooks.example.invalid/x", {"text": "workflow failed"})
                except Exception:
                    pass  # transport is stubbed; the governance call is what matters

        assert spy.await_args.kwargs["require_approval"] is False

    @pytest.mark.asyncio
    async def test_the_telegram_alert_path_passes_the_exemption_to_the_service(self):
        """The wiring, not the mechanism.

        ``TestTelegramSeam`` proves the service honours ``require_approval=False``
        when it is passed. Nothing there proves notification_service *passes* it —
        and dropping it is invisible until someone arms the policy and outage
        alerts stop. Caught by mutation: removing the kwarg left all other tests
        green.
        """
        from services.notification_service import NotificationService

        svc = NotificationService()
        service = AsyncMock()
        with patch("services.telegram_bot_service.TelegramBotService.from_redis", new=AsyncMock(return_value=service)):
            await svc._send_telegram("chat-1", "workflow failed")

        assert service.send_message.await_args.kwargs["require_approval"] is False, (
            "notification_service dropped the alert exemption — arming the policy would "
            "silence outage alerts and deadlock APPROVAL_NEEDED"
        )

    @pytest.mark.asyncio
    async def test_the_audit_record_names_the_host_not_the_full_url(self):
        from services.notification_service import NotificationService

        svc = NotificationService()
        spy = AsyncMock(side_effect=_allow)
        with patch("services.notification_service.egress_governor.evaluate", new=spy):
            with patch("autobot_shared.http_client.get_http_client"):
                try:
                    await svc._send_webhook("https://hooks.example.invalid/secret-token-path", {"t": 1})
                except Exception:
                    pass

        assert spy.await_args.kwargs["channel_id"] == "hooks.example.invalid"
        assert "secret-token-path" not in spy.await_args.kwargs["channel_id"]


class TestTheSiblingSendersReviewFound:
    """The gaps that shipped in the first version of #14270.

    Every seam below reaches a real recipient and was ungoverned while a sibling
    in the same file was carefully gated — which is the shape that makes a
    bypass invisible: the governor's name appears in the module, so a reader
    checking for coverage finds it and stops.

    `send_photo` and `send_document` matter most: both are reachable from the
    agent-response dispatcher this control exists to protect, so an agent
    answering with an image bypassed the gate entirely.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method,kwargs",
        [
            ("send_photo", {"chat_id": "c-1", "photo": "file-id"}),
            ("send_document", {"chat_id": "c-1", "document": "file-id"}),
        ],
    )
    async def test_a_denied_verdict_stops_the_telegram_upload(self, method, kwargs):
        from services.telegram_bot_service import TelegramBotService

        svc = TelegramBotService(bot_token="t")
        http = MagicMock()
        with patch("services.telegram_bot_service.egress_governor.evaluate", new=AsyncMock(side_effect=_deny)):
            with patch("services.telegram_bot_service.get_http_client", return_value=http) as client:
                result = await getattr(svc, method)(**kwargs)

        assert result["error"] == "egress_denied"
        client.assert_not_called()
        http.tracked_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_denied_verdict_stops_the_teams_webhook_endpoint(self):
        """`send_webhook_message` is a sibling route, not a branch of
        `send_message` — governing that function left this one open."""
        from fastapi import HTTPException

        from api.integration_communication import send_webhook_message

        integration = MagicMock()
        integration.execute_action = AsyncMock()
        with patch("api.integration_communication.egress_governor.evaluate", new=AsyncMock(side_effect=_deny)):
            with patch("api.integration_communication.TeamsIntegration", return_value=integration):
                with pytest.raises(HTTPException) as raised:
                    await send_webhook_message(
                        provider="teams",
                        webhook=MagicMock(text="hello", title=None, webhook_url="https://example.invalid/hook"),
                    )

        assert raised.value.status_code == 403
        integration.execute_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_email_seam_is_audited(self):
        """SMTP reaches a real external recipient. It was the one notification
        channel left out while its siblings were wired."""
        from services.notification_service import NotificationService

        svc = NotificationService()
        spy = AsyncMock(side_effect=_allow)
        with patch("services.notification_service.egress_governor.evaluate", new=spy):
            with patch("smtplib.SMTP"), patch("smtplib.SMTP_SSL"):
                try:
                    await svc._send_email("someone@example.invalid", "subj", "body")
                except Exception:
                    pass

        spy.assert_awaited(), "the email seam sent without an audit record"
        assert spy.await_args.kwargs["platform"] == "email"


class TestTheNotificationSeamsHonourADenial:
    """Flagged by security review as fail-open gates.

    Both notification seams awaited the governor and discarded the verdict.
    That is *currently* equivalent to checking it — `_decide` returns allowed
    unconditionally when `require_approval=False` — so it was not a reachable
    bypass. It was a dependency on the governor's present shape that nothing in
    the calling file recorded, which is the same trap as reusing a flag that
    happens to answer a different question.

    These tests force a denial through, so the seams cannot go back to ignoring
    one if `_decide` ever grows a non-approval rule.
    """

    @pytest.mark.asyncio
    async def test_a_denied_verdict_stops_the_email(self):
        from services.notification_service import NotificationService

        svc = NotificationService()
        with patch("services.notification_service.egress_governor.evaluate", new=AsyncMock(side_effect=_deny)):
            with patch("smtplib.SMTP") as smtp, patch("smtplib.SMTP_SSL") as smtp_ssl:
                await svc._send_email("someone@example.invalid", "subj", "body")

        smtp.assert_not_called()
        smtp_ssl.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_denied_verdict_stops_the_webhook_post(self):
        from services.notification_service import NotificationService

        svc = NotificationService()
        http = MagicMock()
        with patch("services.notification_service.egress_governor.evaluate", new=AsyncMock(side_effect=_deny)):
            with patch("autobot_shared.http_client.get_http_client", return_value=http) as client:
                await svc._send_webhook("https://hooks.example.invalid/x", {"t": 1})

        client.assert_not_called()
        http.tracked_request.assert_not_called()
