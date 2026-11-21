# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A share or unshare whose audit record cannot be written is refused and changes nothing (#18890 AC3)."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.session_share import SessionShare, SessionShareAdoption
from security import session_shares
from security.session_ownership import SessionOwnershipValidator

SESSION_ID = "0123456789abcdef0123456789abcdef"
ACTOR = {"user_id": "11111111-1111-1111-1111-111111111111", "username": "alice", "ip": "203.0.113.7"}
SINK_MESSAGE = "audit sink unreachable at sentinel-host-7"


class _Redis:
    """Adoption already recorded, so only the table is exercised."""

    async def exists(self, _key):
        return 1


@pytest.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    async with engine.begin() as conn:
        await conn.run_sync(SessionShare.__table__.create)
        await conn.run_sync(SessionShareAdoption.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine (test-local)
    monkeypatch.setattr(session_shares, "_factory", lambda: factory)

    async def adopted(_redis):
        return None

    monkeypatch.setattr(session_shares, "ensure_adopted", adopted)
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.redis = _Redis()
    async with factory() as db:
        db.add(SessionShare(session_id=SESSION_ID, user_id="bob", shared_by="alice"))
        await db.commit()
    yield validator, factory
    await engine.dispose()


async def _rows(factory):
    async with factory() as db:
        return sorted((await db.execute(select(SessionShare.user_id))).scalars().all())


def _failing_audit():
    return patch("services.audit.audit.audit_record", side_effect=ConnectionError(SINK_MESSAGE))


@pytest.mark.asyncio
async def test_a_share_whose_audit_cannot_be_written_is_refused_and_adds_no_row(env):
    validator, factory = env
    with _failing_audit(), pytest.raises(session_shares.ShareAuditError):
        await validator.share_session(SESSION_ID, ["carol"], "alice", ACTOR)
    assert await _rows(factory) == ["bob"]


@pytest.mark.asyncio
async def test_an_unshare_whose_audit_cannot_be_written_is_refused_and_removes_no_row(env):
    validator, factory = env
    with _failing_audit(), pytest.raises(session_shares.ShareAuditError):
        await validator.unshare_session(SESSION_ID, "bob", ACTOR)
    assert await _rows(factory) == ["bob"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["share", "unshare"])
async def test_the_routes_answer_a_fixed_503_when_the_audit_fails(env, route):
    from api.chat_session_sharing import share_session, unshare_session
    from api.schemas_chat import SessionShareRequest

    validator, factory = env
    request = MagicMock()
    request.method, request.url.path = "POST", "/x"
    ownership = {"reason": "owner_match", "user_data": {"user_id": ACTOR["user_id"], "username": "alice"}}
    with _failing_audit(), patch("api.chat_session_sharing.SessionOwnershipValidator", return_value=validator):
        with patch("api.chat_session_sharing.get_redis_client", AsyncMock(return_value=_Redis())):
            with pytest.raises(HTTPException) as refused:
                if route == "share":
                    await share_session(SESSION_ID, SessionShareRequest(share_with=["carol"]), request, ownership)
                else:
                    await unshare_session(SESSION_ID, "bob", request, ownership)
    assert refused.value.status_code == 503
    assert refused.value.detail == "Service unavailable"
    assert await _rows(factory) == ["bob"]


@pytest.mark.asyncio
async def test_the_audit_failure_log_carries_the_class_only_never_the_message(env, caplog):
    validator, _ = env
    with caplog.at_level(logging.DEBUG), _failing_audit(), pytest.raises(session_shares.ShareAuditError) as err:
        await validator.share_session(SESSION_ID, ["carol"], "alice", ACTOR)
    assert "ConnectionError" in caplog.text
    assert "sentinel-host-7" not in caplog.text
    assert "sentinel-host-7" not in str(err.value) and err.value.__cause__ is None


@pytest.mark.asyncio
async def test_a_working_audit_still_shares_and_unshares(env):
    validator, factory = env
    with patch("services.audit.audit.audit_record") as audit:
        assert await validator.share_session(SESSION_ID, ["carol"], "alice", ACTOR)
        assert await validator.unshare_session(SESSION_ID, "bob", ACTOR)
    assert [c.kwargs["action"].value for c in audit.call_args_list] == ["session.share", "session.unshare"]
    assert await _rows(factory) == ["carol"]
