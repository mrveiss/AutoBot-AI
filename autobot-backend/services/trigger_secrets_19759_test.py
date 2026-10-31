# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Webhook trigger secrets fail closed and legacy plaintext is reported, not rewritten (#19759)."""

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.triggers import create_trigger
from autobot_shared.ssot_constants import TTL_1_HOUR
from services import trigger_secrets
from services.trigger_secrets import EncryptionUnavailableError, find_plaintext_secret_trigger_ids
from services.trigger_service import TriggerConfig, TriggerService, TriggerType
from services.trigger_service_test import _fake_redis_store

LEGACY = "ab" * 32
_PREFIX = trigger_secrets.SECRET_PREFIX


@pytest.fixture()
def no_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger_secrets, "_encryption_service", None)
    monkeypatch.setattr("encryption_service.EncryptionService", MagicMock(side_effect=ValueError("no key")))


@pytest.fixture()
def with_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    from encryption_service import EncryptionService

    monkeypatch.setattr(trigger_secrets, "_encryption_service", EncryptionService(master_key="k" * 48))


def _webhook() -> TriggerConfig:
    return TriggerConfig(trigger_type=TriggerType.WEBHOOK, workflow_id="wf-1", config={})


@pytest.mark.asyncio
async def test_register_webhook_without_encryption_raises_and_stores_nothing(no_encryption) -> None:
    redis = _fake_redis_store()
    svc = TriggerService()
    with patch("services.trigger_service.get_redis_client", return_value=redis):
        with pytest.raises(EncryptionUnavailableError):
            await svc.register_trigger(_webhook())
    redis.setex.assert_not_called()
    redis.sadd.assert_not_called()
    assert svc._webhook_secrets == {}


@pytest.mark.asyncio
async def test_non_webhook_trigger_needs_no_encryption(no_encryption) -> None:
    cfg = TriggerConfig(trigger_type=TriggerType.CRON, workflow_id="wf", config={"cron_expression": "* * * * *"})
    with patch("services.trigger_service.get_redis_client", return_value=_fake_redis_store()):
        assert await TriggerService().register_trigger(cfg)


@pytest.mark.asyncio
async def test_stored_secret_is_ciphertext(with_encryption) -> None:
    redis = _fake_redis_store()
    with patch("services.trigger_service.get_redis_client", return_value=redis):
        svc = TriggerService()
        tid = await svc.register_trigger(_webhook())
    stored = redis.get(f"{_PREFIX}{tid}")
    assert stored != svc._webhook_secrets[tid]
    assert not trigger_secrets.is_legacy_plaintext(stored)


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", ["with_encryption", "no_encryption"])
async def test_legacy_plaintext_secret_still_verifies(fixture, request) -> None:
    request.getfixturevalue(fixture)
    redis = _fake_redis_store()
    redis.setex(f"{_PREFIX}t1", TTL_1_HOUR, LEGACY)
    body = b"{}"
    sig = "sha256=" + hmac.new(LEGACY.encode(), body, hashlib.sha256).hexdigest()
    with patch("services.trigger_service.get_redis_client", return_value=redis):
        assert await TriggerService().validate_webhook_signature("t1", body, sig)


@pytest.mark.asyncio
async def test_create_trigger_api_maps_unavailable_encryption_to_503() -> None:
    service = MagicMock()
    service.register_trigger = AsyncMock(side_effect=EncryptionUnavailableError("internal detail: key missing"))
    request = MagicMock(trigger_type=TriggerType.WEBHOOK, workflow_id="wf", config={}, conditions=[], enabled=True)
    with patch("api.triggers.get_trigger_service", return_value=service):
        with pytest.raises(HTTPException) as exc:
            await create_trigger(request, current_user={"username": "u"})
    assert exc.value.status_code == 503
    assert "internal detail" not in exc.value.detail


def test_detector_lists_only_plaintext_ids_and_never_values(with_encryption, caplog) -> None:
    redis = _fake_redis_store()
    redis.scan_iter = lambda match: iter([f"{_PREFIX}b".encode(), f"{_PREFIX}a", f"{_PREFIX}c"])
    ciphertext = trigger_secrets.encrypt_secret(LEGACY)
    values = {f"{_PREFIX}a": LEGACY, f"{_PREFIX}b": "cd" * 32, f"{_PREFIX}c": ciphertext}
    redis.get.side_effect = values.get
    assert find_plaintext_secret_trigger_ids(redis) == ["a", "b"]
    assert LEGACY not in caplog.text and "cd" * 32 not in caplog.text
    redis.setex.assert_not_called()
    redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_proposal_carries_ids_only_and_rewrites_nothing() -> None:
    redis = _fake_redis_store()
    redis.scan_iter = lambda match: iter([f"{_PREFIX}t1"])
    redis.get.side_effect = {f"{_PREFIX}t1": LEGACY}.get
    request_approval = AsyncMock(return_value="approval")
    with patch("llc.services.approval.ApprovalService.request_approval", request_approval):
        result = await trigger_secrets.propose_plaintext_secret_rewrite(MagicMock(), redis)
    assert result == "approval"
    payload = request_approval.call_args.kwargs["payload"]
    assert payload["trigger_ids"] == ["t1"]
    assert LEGACY not in repr(payload)
    redis.setex.assert_not_called()
    redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_no_plaintext_means_no_proposal() -> None:
    redis = _fake_redis_store()
    redis.scan_iter = lambda match: iter([])
    assert await trigger_secrets.propose_plaintext_secret_rewrite(MagicMock(), redis) is None
