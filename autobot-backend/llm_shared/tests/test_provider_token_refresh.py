# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Single-flight refresh and failure backoff for signed-in provider tokens (#19241, PR #19259 review).

- N concurrent calls on an expiring token make exactly ONE refresh POST.
- A worker that loses the cross-worker lease waits for the holder's write and makes no POST.
- A failed refresh is backed off (no re-POST while cached) and falls through to the next source.
- ``invalid_grant`` flags the stored token as needing a new sign-in.
- The refresh runs the public-egress check before any POST.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.connectors.oauth_flow import OAuthProvider, TokenEndpointError
from llm_shared import provider_oauth_credentials as creds
from llm_shared import provider_token_refresh as refresh_mod
from llm_shared.llm_oauth_registry import LlmOAuthClient
from llm_shared.provider_auth import OAuthAuth

_TOKEN_URL = "https://auth.openai.com/oauth/token"  # nosec B105  # an allowlisted endpoint URL, not a credential
_CLIENT = LlmOAuthClient(
    provider=OAuthProvider(
        name="openai",
        authorize_url="https://auth.openai.com/authorize",
        token_url=_TOKEN_URL,
        client_id_setting="openai_client_id",
        client_secret_setting="AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_SECRET",  # nosec B106  # pragma: allowlist secret
    ),
    client_id="cid",
)
_USER = "user:u-1"


def _expired(access="old", refresh="rt-1"):
    return {"access_token": access, "refresh_token": refresh, "expires_at": time.time() - 10, "created_by": "u-1"}


class _Vault:
    """The system vault, keyed by subject; writes land where every reader sees them."""

    def __init__(self, tokens):
        self.tokens = dict(tokens)

    async def read(self, session, *, provider_name, subject, owner_vault_str):
        data = self.tokens.get(subject)
        return dict(data) if data else None

    async def write(self, session, *, provider_name, subject, owner_vault_str, token_data, created_by_id):
        self.tokens[subject] = dict(token_data)


class _Lease:
    def __init__(self, acquired=True):
        self.update_leadership = AsyncMock(return_value=acquired)


@pytest.fixture
def world(monkeypatch):
    """Fake vault + token endpoint; a lease that is always granted (one worker)."""
    refresh_mod._unusable_until.clear()
    refresh_mod._local_locks.clear()
    vault = _Vault({_USER: _expired(), "global": {"access_token": "system-at"}})
    posts = AsyncMock()

    async def _refresh_post(token_url, client_id, client_secret, refresh_token, *, connector=None, provider=None):
        await posts(refresh_token)
        await asyncio.sleep(0.01)  # keep the callers overlapping
        return {"access_token": "fresh-at", "refresh_token": "rt-2", "expires_in": 3600}

    monkeypatch.setattr(creds, "_vault_read", vault.read)
    monkeypatch.setattr(creds, "_vault_write", vault.write)
    monkeypatch.setitem(OAuthAuth._refresh.__globals__, "_vault_write", vault.write)
    monkeypatch.setattr(creds, "resolve_client", lambda name, flow=None: _CLIENT)
    monkeypatch.setattr("knowledge.connectors.oauth_flow.refresh_access_token", _refresh_post)
    monkeypatch.setattr("autobot_shared.security.ssrf_guard.pinned_connector", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(refresh_mod, "_lease", lambda provider, subject: _Lease(True))
    monkeypatch.setattr(refresh_mod, "_release", AsyncMock())
    yield vault, posts
    refresh_mod._unusable_until.clear()
    refresh_mod._local_locks.clear()


def _session():
    session = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_concurrent_calls_make_exactly_one_refresh_post(world):
    vault, posts = world
    results = await asyncio.gather(*(creds.first_usable_token(_session(), "openai", "u-1", "") for _ in range(8)))
    assert results == ["fresh-at"] * 8
    assert posts.await_count == 1
    assert vault.tokens[_USER]["refresh_token"] == "rt-2"  # the rotated pair was kept


@pytest.mark.asyncio
async def test_losing_the_lease_waits_for_the_holder_and_never_posts(world, monkeypatch):
    vault, posts = world
    monkeypatch.setattr(refresh_mod, "_lease", lambda provider, subject: _Lease(False))
    monkeypatch.setattr(refresh_mod, "_lease_is_held", AsyncMock(return_value=True))
    monkeypatch.setattr("knowledge.connectors.credential_store._refresh_poll_s", lambda: 0.01)
    monkeypatch.setattr("knowledge.connectors.credential_store._refresh_wait_s", lambda: 2.0)

    async def _other_worker_refreshes():
        await asyncio.sleep(0.05)
        vault.tokens[_USER] = {**_expired(), "access_token": "theirs", "expires_at": time.time() + 3600}

    holder = asyncio.create_task(_other_worker_refreshes())
    token = await creds.first_usable_token(_session(), "openai", "u-1", "")
    await holder
    assert token == "theirs"
    posts.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_refresh_is_backed_off_and_falls_through(world, monkeypatch):
    vault, _ = world
    calls = AsyncMock(side_effect=TokenEndpointError(503, {"error": "temporarily_unavailable"}))
    monkeypatch.setattr("knowledge.connectors.oauth_flow.refresh_access_token", calls)

    assert await creds.first_usable_token(_session(), "openai", "u-1", "") == "system-at"
    assert await creds.first_usable_token(_session(), "openai", "u-1", "") == "system-at"
    assert calls.await_count == 1  # the second call skipped straight to the system token
    assert refresh_mod.is_backed_off("openai", _USER)

    refresh_mod._unusable_until[("openai", _USER)] = time.monotonic() - 1  # the TTL has passed
    await creds.first_usable_token(_session(), "openai", "u-1", "")
    assert calls.await_count == 2


def test_the_backoff_window_is_at_least_sixty_seconds():
    assert refresh_mod.UNUSABLE_TTL_SECONDS >= 60


@pytest.mark.asyncio
async def test_invalid_grant_flags_the_token_for_a_new_sign_in(world, monkeypatch):
    vault, _ = world
    calls = AsyncMock(side_effect=TokenEndpointError(400, {"error": "invalid_grant"}))
    monkeypatch.setattr("knowledge.connectors.oauth_flow.refresh_access_token", calls)

    assert await creds.first_usable_token(_session(), "openai", "u-1", "") == "system-at"
    assert vault.tokens[_USER]["needs_reauth"] is True

    refresh_mod._unusable_until.clear()  # even with the process cache gone, the stored flag holds
    assert await creds.first_usable_token(_session(), "openai", "u-1", "") == "system-at"
    assert calls.await_count == 1


@pytest.mark.asyncio
async def test_a_failed_needs_reauth_write_falls_through_instead_of_raising(world, monkeypatch):
    """Review low: recording invalid_grant is best effort; the call still resolves the next source."""
    monkeypatch.setattr(
        "knowledge.connectors.oauth_flow.refresh_access_token",
        AsyncMock(side_effect=TokenEndpointError(400, {"error": "invalid_grant"})),
    )
    monkeypatch.setattr(creds, "_vault_write", AsyncMock(side_effect=RuntimeError("vault down")))
    session = _session()
    session.rollback = AsyncMock()
    assert await creds.first_usable_token(session, "openai", "u-1", "") == "system-at"
    session.rollback.assert_awaited_once()
    assert refresh_mod.is_backed_off("openai", _USER)


@pytest.mark.asyncio
async def test_refresh_runs_the_public_egress_check(world, monkeypatch):
    from autobot_shared.http_egress_guard import EgressBlockedError

    _, posts = world
    monkeypatch.setattr(
        "autobot_shared.http_egress_guard.assert_public_egress", AsyncMock(side_effect=EgressBlockedError("private"))
    )
    assert await creds.first_usable_token(_session(), "openai", "u-1", "") == "system-at"
    posts.assert_not_awaited()
