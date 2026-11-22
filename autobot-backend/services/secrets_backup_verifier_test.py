# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``verify_backup`` is True only for a completed, recent, intact secrets backup (#18281).

The SLM is faked at the transport (``httpx.MockTransport``), so the real request -- URL,
internal-key header -- and the real parsing are what is tested. One test per failing condition.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from services import secrets_backup_verifier as verifier

pytestmark = pytest.mark.asyncio

KEY = "k" * 64


def _record(**over):
    base = {
        "status": "completed",
        "service_type": "secrets",
        "completed_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "integrity_ok": True,
    }
    base.update(over)
    return base


@pytest.fixture
def slm(monkeypatch):
    """Install a fake SLM; returns the list of requests it served."""
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", KEY)
    served: list[httpx.Request] = []

    def install(handler):
        def _handler(request):
            served.append(request)
            return handler(request)

        monkeypatch.setattr(verifier, "node_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(_handler)))

    install.served = served
    return install


def _answer(body, status=200):
    return lambda request: httpx.Response(status, json=body)


async def test_passes_for_a_completed_recent_intact_secrets_backup(slm):
    slm(_answer(_record()))
    assert await verifier.verify_backup("bk1") is True
    request = slm.served[0]
    assert request.url.path.endswith("/api/stateful/secrets-backups/bk1")
    assert request.headers["X-Internal-API-Key"] == KEY


async def test_a_naive_completed_at_is_read_as_utc(slm):
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None).isoformat()
    slm(_answer(_record(completed_at=stamp)))
    assert await verifier.verify_backup("bk1") is True


async def test_missing_row_is_refused(slm):
    slm(_answer({"detail": "Backup not found"}, 404))
    assert await verifier.verify_backup("nope") is False


@pytest.mark.parametrize("state", ["pending", "in_progress", "failed"])
async def test_not_completed_is_refused(slm, state):
    slm(_answer(_record(status=state)))
    assert await verifier.verify_backup("bk1") is False


@pytest.mark.parametrize("kind", ["redis", "postgres", None])
async def test_wrong_service_type_is_refused(slm, kind):
    slm(_answer(_record(service_type=kind)))
    assert await verifier.verify_backup("bk1") is False


async def test_too_old_is_refused(slm):
    old = datetime.now(timezone.utc) - timedelta(seconds=verifier.SECRETS_BACKUP_MAX_AGE_S + 60)
    slm(_answer(_record(completed_at=old.isoformat())))
    assert await verifier.verify_backup("bk1") is False


async def test_no_completion_time_or_a_future_one_is_refused(slm):
    slm(_answer(_record(completed_at=None)))
    assert await verifier.verify_backup("bk1") is False
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    slm(_answer(_record(completed_at=future.isoformat())))
    assert await verifier.verify_backup("bk1") is False


@pytest.mark.parametrize("flag", [False, None, "true"])
async def test_failed_integrity_is_refused(slm, flag):
    slm(_answer(_record(integrity_ok=flag)))
    assert await verifier.verify_backup("bk1") is False


async def test_a_timeout_fails_closed(slm):
    def _timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    slm(_timeout)
    assert await verifier.verify_backup("bk1") is False


async def test_a_transport_error_fails_closed(slm):
    def _down(request):
        raise httpx.ConnectError("down", request=request)

    slm(_down)
    assert await verifier.verify_backup("bk1") is False


@pytest.mark.parametrize("status", [401, 403, 500])
async def test_a_non_200_fails_closed(slm, status):
    slm(_answer(_record(), status))
    assert await verifier.verify_backup("bk1") is False


async def test_an_unparsable_answer_fails_closed(slm):
    slm(lambda request: httpx.Response(200, content=b"<html>proxy error</html>"))
    assert await verifier.verify_backup("bk1") is False


async def test_no_internal_key_never_calls_the_slm(slm, monkeypatch):
    slm(_answer(_record()))
    monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY")
    assert await verifier.verify_backup("bk1") is False
    assert slm.served == []


async def test_an_empty_reference_is_refused_and_a_path_reference_is_encoded(slm):
    slm(_answer(_record()))
    assert await verifier.verify_backup("") is False
    await verifier.verify_backup("../../admin")
    assert "..%2F..%2Fadmin" in str(slm.served[0].url)
