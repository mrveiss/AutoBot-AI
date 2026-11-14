# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which signed-in token an LLM call uses (#19241).

Order: the requesting user's own token, then the org/system token, then None
(the provider's API key). A user never receives another user's token, and an
unusable token falls through to the next source.
"""

import asyncio
import contextvars
import time

import pytest

from llm_shared import provider_auth
from llm_shared import provider_oauth_credentials as creds
from llm_shared.run_credentials import (
    get_llm_principal,
    llm_principal_scope,
    reset_llm_principal,
    set_llm_principal,
    stream_with_llm_principal,
)

_FRESH = time.time() + 3600


class _Vault:
    """Token store keyed by subject, standing in for the system vault."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.reads = []

    async def read(self, session, *, provider_name, subject, owner_vault_str):
        self.reads.append(subject)
        return self.tokens.get(subject)


@pytest.fixture
def vault(monkeypatch):
    def _install(tokens):
        fake = _Vault(tokens)
        monkeypatch.setattr(creds, "_vault_read", fake.read)
        return fake

    return _install


def _token(value, expires_at=_FRESH, refresh=None):
    data = {"access_token": value, "expires_at": expires_at}
    if refresh:
        data["refresh_token"] = refresh
    return data


@pytest.fixture(autouse=True)
def _fresh_backoff_cache():
    """The refresh backoff is process-wide; keep one test's failures out of the next."""
    from llm_shared import provider_token_refresh

    provider_token_refresh._unusable_until.clear()
    yield
    provider_token_refresh._unusable_until.clear()


def test_candidate_order_is_user_then_org_then_legacy():
    assert creds.candidate_subjects("u-1", "org-9") == [
        ("user", "user:u-1"),
        ("system", "org:org-9"),
        ("system", "global"),
    ]
    assert creds.candidate_subjects("", "") == [("system", "global")]


_STOP = {"legacy_fallback_stopped": True}


@pytest.mark.asyncio
async def test_org_a_revoke_leaves_org_b_on_the_legacy_token(vault):
    """Owner decision (#19241): one org's disconnect is a per-org stop marker, not a delete of "global"."""
    vault({"org:A": _STOP, "global": _token("legacy-at")})
    assert await creds.first_usable_token(None, "openai", "", "B") == "legacy-at"


@pytest.mark.asyncio
async def test_org_a_no_longer_resolves_the_legacy_token_after_its_revoke(vault):
    fake = vault({"org:A": _STOP, "global": _token("legacy-at")})
    assert await creds.first_usable_token(None, "openai", "u-1", "A") is None
    assert "global" not in fake.reads


@pytest.mark.asyncio
async def test_org_a_signing_in_again_replaces_the_marker(vault):
    vault({"org:A": _token("org-a-at"), "global": _token("legacy-at")})  # the new sign-in overwrote the marker
    assert await creds.first_usable_token(None, "openai", "", "A") == "org-a-at"


@pytest.mark.asyncio
async def test_after_a_superadmin_shared_revoke_orgs_on_the_legacy_token_fall_through_to_the_api_key(vault):
    """The shared revoke deletes "global": an org that had no token of its own now resolves none."""
    vault({"org:A": _token("org-a-at")})  # "global" is gone
    assert await creds.first_usable_token(None, "openai", "", "B") is None  # -> the provider's API key
    assert await creds.first_usable_token(None, "openai", "", "A") == "org-a-at"  # own tokens are untouched


@pytest.mark.asyncio
async def test_the_dual_read_honours_the_stop_marker(monkeypatch):
    store = {"org:A": _STOP, "global": {"access_token": "legacy-at"}}

    async def _read(session, *, provider_name, subject, owner_vault_str):
        return store.get(subject)

    monkeypatch.setattr(provider_auth, "_vault_read", _read)
    kwargs = {"provider_name": "openai", "owner_vault_str": "system"}
    assert await provider_auth._vault_read_dual(None, subject="org:A", **kwargs) is None
    assert (await provider_auth._vault_read_dual(None, subject="org:B", **kwargs))["access_token"] == "legacy-at"


@pytest.mark.asyncio
async def test_user_token_wins_over_system(vault):
    vault({"user:u-1": _token("user-at"), "org:org-9": _token("system-at")})
    assert await creds.first_usable_token(None, "openai", "u-1", "org-9") == "user-at"


@pytest.mark.asyncio
async def test_system_token_when_user_has_none(vault):
    vault({"org:org-9": _token("system-at")})
    assert await creds.first_usable_token(None, "openai", "u-1", "org-9") == "system-at"


@pytest.mark.asyncio
async def test_none_when_no_token_so_the_api_key_is_used(vault):
    vault({})
    assert await creds.first_usable_token(None, "openai", "u-1", "org-9") is None


@pytest.mark.asyncio
async def test_user_b_never_gets_user_a_token(vault):
    fake = vault({"user:u-A": _token("a-at")})
    assert await creds.first_usable_token(None, "openai", "u-B", "") is None
    assert "user:u-A" not in fake.reads


@pytest.mark.asyncio
async def test_expired_user_token_falls_through_to_system(vault):
    vault({"user:u-1": _token("stale", expires_at=time.time() - 10), "global": _token("system-at")})
    assert await creds.first_usable_token(None, "openai", "u-1", "") == "system-at"


@pytest.mark.asyncio
async def test_user_subject_never_dual_reads_the_legacy_global(monkeypatch):
    reads = []

    async def _read(session, *, provider_name, subject, owner_vault_str):
        reads.append(subject)
        return {"access_token": "shared"} if subject == "global" else None

    monkeypatch.setattr(provider_auth, "_vault_read", _read)
    got = await provider_auth._vault_read_dual(
        None, provider_name="openai", subject="user:u-1", owner_vault_str="system"
    )
    assert got is None
    assert reads == ["user:u-1"]


@pytest.mark.asyncio
async def test_unconfigured_provider_skips_the_lookup(monkeypatch):
    monkeypatch.setattr(creds, "sign_in_configured", lambda name: False)

    async def _boom(*a, **k):
        raise AssertionError("no vault lookup for an unconfigured provider")

    monkeypatch.setattr(creds, "first_usable_token", _boom)
    assert await creds.resolve_signed_in_token("openai") is None


def test_principal_comes_from_the_task_context_only():
    with llm_principal_scope("u-1", "org-9"):
        assert creds.request_principal() == ("u-1", "org-9")
    assert get_llm_principal() is None
    assert creds.request_principal() == ("", "")


@pytest.mark.asyncio
async def test_principal_does_not_outlive_its_scope():
    """M1: a task spawned after the scope ends, or a fresh context, sees no principal."""

    async def _seen():
        return get_llm_principal()

    with llm_principal_scope("u-1", "org-9"):
        inside = asyncio.create_task(_seen())
    after = asyncio.create_task(_seen())
    assert await inside == ("u-1", "org-9")
    assert await after is None
    assert contextvars.Context().run(get_llm_principal) is None


@pytest.mark.asyncio
async def test_stream_scope_ends_with_the_stream():
    async def _body():
        yield get_llm_principal()

    seen = [item async for item in stream_with_llm_principal(("u-1", ""), _body())]
    assert seen == [("u-1", "")]
    assert get_llm_principal() is None


def test_reset_from_another_context_does_not_raise():
    """An async generator finalised by the loop resets in a different Context."""
    token = set_llm_principal("u-1")
    try:
        contextvars.Context().run(reset_llm_principal, token)
    finally:
        reset_llm_principal(token)
    assert get_llm_principal() is None


def test_missing_expiry_is_not_treated_as_expired():
    """A token stored without expires_at (no expires_in sent) stays usable, matching /status."""
    auth = provider_auth.OAuthAuth(provider_name="openai", token_url="", client_id="", client_secret="")
    assert asyncio.run(auth._ensure_fresh(None, {"access_token": "at"})) == "at"
