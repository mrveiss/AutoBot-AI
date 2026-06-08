# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ApiKeyService (GH#8218)."""

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.services.api_key import ApiKeyService, _hash_key


def _make_key_record(revoked: bool = False) -> MagicMock:
    record = MagicMock()
    record.id = uuid.uuid4()
    record.agent_id = "agent-001"
    record.company_id = "company-001"
    record.name = "test-key"
    record.revoked_at = datetime.now(timezone.utc) if revoked else None
    record.created_at = datetime.now(timezone.utc)
    return record


def _make_session(scalar=None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    session.execute.return_value = result
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_issue_key_returns_plaintext() -> None:
    session = _make_session()
    svc = ApiKeyService()
    record, plaintext = await svc.issue_key(session, "agent-001", "co-001", "mykey")
    assert plaintext.startswith("llc_")
    assert len(plaintext) > 10


@pytest.mark.asyncio
async def test_issue_key_stores_hash() -> None:
    session = _make_session()
    svc = ApiKeyService()
    record, plaintext = await svc.issue_key(session, "agent-001", "co-001", "mykey")
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.key_hash == hashlib.sha256(plaintext.encode()).hexdigest()


@pytest.mark.asyncio
async def test_revoke_key_not_found_raises() -> None:
    session = _make_session(scalar=None)
    svc = ApiKeyService()
    with pytest.raises(KeyError):
        await svc.revoke_key(session, "agent-001", uuid.uuid4())


@pytest.mark.asyncio
async def test_validate_key_valid() -> None:
    record = _make_key_record()
    session = _make_session(scalar=record)
    svc = ApiKeyService()
    result = await svc.validate_key(session, "llc_sometoken")
    assert result is record


@pytest.mark.asyncio
async def test_validate_key_revoked_returns_none() -> None:
    session = _make_session(scalar=None)  # DB returns None for revoked key
    svc = ApiKeyService()
    result = await svc.validate_key(session, "llc_sometoken")
    assert result is None


def test_hash_key_deterministic() -> None:
    h1 = _hash_key("llc_test")
    h2 = _hash_key("llc_test")
    assert h1 == h2


def test_hash_key_different_for_different_keys() -> None:
    assert _hash_key("llc_a") != _hash_key("llc_b")


@pytest.mark.asyncio
async def test_issue_key_sets_expires_at() -> None:
    # GH#9623: ephemeral run-scoped keys carry a TTL backstop.
    session = _make_session()
    svc = ApiKeyService()
    exp = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await svc.issue_key(session, "agent-001", "co-001", "ephemeral", expires_at=exp)
    added = session.add.call_args[0][0]
    assert added.expires_at == exp


@pytest.mark.asyncio
async def test_issue_key_defaults_no_expiry() -> None:
    # GH#9623: long-lived keys still default to no expiry (NULL).
    session = _make_session()
    svc = ApiKeyService()
    await svc.issue_key(session, "agent-001", "co-001", "longlived")
    added = session.add.call_args[0][0]
    assert added.expires_at is None
