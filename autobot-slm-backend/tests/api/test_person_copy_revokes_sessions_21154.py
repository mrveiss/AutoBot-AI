# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21154: a person deactivated in the main app loses the SLM sessions already issued.

The push to the SLM's person-copy route flips ``is_active``, but the SLM's request gate reads the
epoch store, never ``is_active``. A real HS256 token goes through the real ``decode_token_async``;
the real route handler receives the push. Only storage is stood in for: the epoch store, the jti
denylist, and the session's commit.
"""

import importlib.util
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.user_management import password_epoch
from testkit.fake_async_session import FakeAsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "_first_admin_internal_21154", Path(__file__).parents[2] / "api" / "first_admin_internal.py"
)
route = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(route)

_REAL_AUTH = load_real_auth("s" * 40, expire_minutes=60 * 24)
auth_service = _REAL_AUTH.auth_service
_OLD_HASH = "hash-before"  # pragma: allowlist secret
_NEW_HASH = "hash-after"  # pragma: allowlist secret
_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000154")


@pytest.fixture()
def epochs():
    store: dict[str, int] = {}
    events: list[int] = []  # commits already made on the session each time an epoch was written
    session = FakeAsyncSession()
    fail = {"on": False}

    async def get_epoch(subject):
        return store.get(subject)

    async def set_epoch(subject, *, now=None):
        if fail["on"]:
            return None
        events.append(session.commits)
        store[subject] = int(time.time()) if now is None else now
        return store[subject]

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    with patch.object(_REAL_AUTH, "is_jti_revoked", AsyncMock(return_value=False)):
        yield SimpleNamespace(store=store, events=events, fail=fail, session=session)
    password_epoch.reset_epoch_store()


def _token() -> str:
    return auth_service.create_access_token({"sub": "alice", "iat": int(time.time()) - 60})


async def _push(epochs, *, is_active: bool, user=None, password_hash: str = "h") -> SimpleNamespace:
    user = user or SimpleNamespace(username="alice", password_hash="h", is_active=True)
    body = route.PersonCopyRequest(slm_user_id=_USER_ID, password_hash=password_hash, is_active=is_active)
    with patch.object(route, "verify_internal_api_key", return_value=True):
        epochs.session.on_get = lambda _model, _pk: user
        await route.update_person_copy(body, epochs.session, "key")
    return user


@pytest.mark.asyncio
async def test_a_live_persons_token_decodes(epochs):
    assert (await auth_service.decode_token_async(_token()))["sub"] == "alice"


@pytest.mark.asyncio
async def test_a_deactivation_push_refuses_the_sessions_already_issued(epochs):
    token = _token()
    user = await _push(epochs, is_active=False)

    assert user.is_active is False
    assert await auth_service.decode_token_async(token) is None


@pytest.mark.asyncio
async def test_the_epoch_is_written_after_the_commit(epochs):
    await _push(epochs, is_active=False)
    assert epochs.events == [1], "the commit came first"


@pytest.mark.asyncio
async def test_a_push_of_an_active_person_revokes_nothing(epochs):
    token = _token()
    await _push(epochs, is_active=True)

    assert epochs.store == {}
    assert (await auth_service.decode_token_async(token))["sub"] == "alice"


@pytest.mark.asyncio
async def test_the_next_push_completes_a_revocation_whose_epoch_write_failed(epochs):
    token = _token()
    user = SimpleNamespace(username="alice", password_hash="h", is_active=True)
    epochs.fail["on"] = True
    with patch("autobot_shared.user_management.password_epoch.asyncio.sleep", AsyncMock()):
        with pytest.raises(password_epoch.PasswordEpochWriteError):
            await _push(epochs, is_active=False, user=user)
    assert user.is_active is False, "the deactivation committed; only the revocation is outstanding"
    assert (await auth_service.decode_token_async(token))["sub"] == "alice"

    epochs.fail["on"] = False
    await _push(epochs, is_active=False, user=user)  # the main app's periodic pass; no field differs now

    assert await auth_service.decode_token_async(token) is None


@pytest.mark.asyncio
async def test_a_token_minted_after_a_reactivation_works(epochs):
    await _push(epochs, is_active=False)
    await _push(epochs, is_active=True)
    fresh = auth_service.create_access_token({"sub": "alice", "iat": int(time.time()) + 5})

    assert (await auth_service.decode_token_async(fresh))["sub"] == "alice"


@pytest.mark.asyncio
async def test_a_pushed_password_change_refuses_the_sessions_already_issued(epochs):
    token = _token()
    user = SimpleNamespace(username="alice", password_hash=_OLD_HASH, is_active=True)
    await _push(epochs, is_active=True, user=user, password_hash=_NEW_HASH)

    assert user.password_hash == _NEW_HASH
    assert await auth_service.decode_token_async(token) is None


@pytest.mark.asyncio
async def test_a_push_that_changes_nothing_revokes_nothing(epochs):
    token = _token()
    await _push(epochs, is_active=True)

    assert epochs.store == {}
    assert (await auth_service.decode_token_async(token))["sub"] == "alice"


@pytest.mark.asyncio
async def test_a_token_minted_after_a_pushed_password_change_works(epochs):
    user = SimpleNamespace(username="alice", password_hash=_OLD_HASH, is_active=True)
    await _push(epochs, is_active=True, user=user, password_hash=_NEW_HASH)
    fresh = auth_service.create_access_token({"sub": "alice", "iat": int(time.time()) + 1})

    assert (await auth_service.decode_token_async(fresh))["sub"] == "alice"
