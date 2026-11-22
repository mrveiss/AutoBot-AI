# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Server-side LLM sign-in registry + its endpoints (#19241).

Proves the provider endpoints and client come from server config, a client can
no longer supply URLs or a client id, an unknown/unconfigured provider is a 4xx,
``redirect_uri`` must sit on the SSOT frontend origin, and GET /providers never
returns a secret.
"""

import types
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import provider_auth as mod
from api.provider_auth_scope import provider_caller_is_admin
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.ssot_config import config
from llm_shared import llm_oauth_registry as registry

# A sentinel the vault "returns"; asserted absent from every response.
_SENTINEL = "-".join(("sentinel", "vaulted", "19241"))
_REDIRECT = config.frontend_url + "/preferences/oauth/callback"


@pytest.fixture
def hf_configured(monkeypatch):
    """HuggingFace with an operator client id (its documented endpoints ship as defaults) and a vaulted secret."""
    monkeypatch.setattr(config.llm_oauth, "huggingface_client_id", "hf-client-id")
    monkeypatch.setattr(registry, "_resolve_client_secret", lambda name: _SENTINEL)


@pytest.fixture
def ctx(monkeypatch, single_use_fake_redis):
    monkeypatch.setattr(mod, "get_redis_client", lambda database="main": single_use_fake_redis)
    monkeypatch.setattr(mod, "_pinned_connector", AsyncMock(return_value=None))
    # The code exchange's public-egress check resolves DNS; the fake token host has none. That the
    # check runs and blocks is proved in test_provider_auth_hardening.py (#19241).
    monkeypatch.setattr(mod, "assert_public_egress", AsyncMock(return_value=None))
    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: types.SimpleNamespace(user_id="admin-1")
    app.dependency_overrides[provider_caller_is_admin] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    return TestClient(app), single_use_fake_redis


# --- registry resolution ----------------------------------------------------


def test_huggingface_defaults_are_its_documented_endpoints():
    provider = registry.build_provider("huggingface")
    assert provider.authorize_url == "https://huggingface.co/oauth/authorize"
    assert provider.token_url.endswith("huggingface.co/oauth/token")
    assert provider.device_authorization_url == "https://huggingface.co/oauth/device"
    assert registry.available_flows(provider) == ["redirect", "device"]


def test_no_client_id_ships_so_every_provider_starts_unconfigured(monkeypatch):
    for name in ("openai", "anthropic", "huggingface"):
        monkeypatch.setattr(config.llm_oauth, f"{name}_client_id", "")
    rows = {row["name"]: row for row in registry.describe_providers()}
    assert set(rows) == {"openai", "anthropic", "huggingface"}
    assert not any(row["configured"] for row in rows.values())
    assert "AUTOBOT_LLM_OAUTH_HUGGINGFACE_CLIENT_ID" in rows["huggingface"]["missing_settings"]
    # OpenAI ships no endpoints: the operator must fill them too.
    assert rows["openai"]["flows"] == []
    assert "AUTOBOT_LLM_OAUTH_OPENAI_AUTHORIZE_URL" in rows["openai"]["missing_settings"]


def test_resolve_client_reads_config_and_vault_secret(hf_configured):
    client = registry.resolve_client("huggingface", registry.FLOW_DEVICE)
    assert client.client_id == "hf-client-id"
    assert client.client_secret == _SENTINEL
    assert client.provider.token_endpoint_auth_method == "client_secret_post"
    assert _SENTINEL not in repr(client)


def test_resolve_client_without_secret_is_a_public_client(monkeypatch):
    monkeypatch.setattr(config.llm_oauth, "huggingface_client_id", "hf-client-id")
    monkeypatch.setattr(registry, "_resolve_client_secret", lambda name: "")
    client = registry.resolve_client("huggingface")
    assert client.provider.token_endpoint_auth_method == "none"


def test_resolve_client_unknown_and_unconfigured(monkeypatch):
    monkeypatch.setattr(config.llm_oauth, "openai_client_id", "")
    with pytest.raises(registry.UnknownProviderError):
        registry.resolve_client("acme")
    with pytest.raises(registry.ProviderNotConfiguredError, match="AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_ID"):
        registry.resolve_client("openai")


# --- endpoints ----------------------------------------------------------------


def test_providers_listing_never_returns_a_secret(ctx, hf_configured):
    tc, _ = ctx
    resp = tc.get("/api/llm-auth/providers")
    assert resp.status_code == 200, resp.text
    assert _SENTINEL not in resp.text
    assert "hf-client-id" not in resp.text  # setting names only, never values
    hf = next(row for row in resp.json() if row["name"] == "huggingface")
    assert hf == {
        "name": "huggingface",
        "label": "HuggingFace",
        "flows": ["redirect", "device"],
        "configured": True,
        "missing_settings": [],
    }


def test_initiate_rejects_client_supplied_urls_and_client_id(ctx, hf_configured):
    tc, fake_redis = ctx
    body = {
        "provider_name": "huggingface",
        "redirect_uri": _REDIRECT,
        "scope": "user",
        "authorize_url": "https://evil.example.net/authorize",
        "token_url": "https://evil.example.net/token",
        "client_id": "attacker-client",
    }
    resp = tc.post("/api/llm-auth/oauth/initiate", json=body)
    assert resp.status_code == 422
    assert not fake_redis.store


def test_device_initiate_rejects_client_supplied_url(ctx, hf_configured):
    tc, _ = ctx
    body = {
        "provider_name": "huggingface",
        "scope": "user",
        "device_authorization_url": "https://evil.example.net/device",
    }
    assert tc.post("/api/llm-auth/device/initiate", json=body).status_code == 422


def test_initiate_uses_the_registry_endpoint_and_client(ctx, hf_configured):
    tc, _ = ctx
    resp = tc.post(
        "/api/llm-auth/oauth/initiate",
        json={"provider_name": "huggingface", "redirect_uri": _REDIRECT, "scope": "user"},
    )
    assert resp.status_code == 200, resp.text
    url = resp.json()["authorize_url"]
    assert url.startswith("https://huggingface.co/oauth/authorize?")
    assert "client_id=hf-client-id" in url
    assert _SENTINEL not in url


def test_unknown_provider_is_404(ctx):
    tc, _ = ctx
    resp = tc.post(
        "/api/llm-auth/oauth/initiate", json={"provider_name": "acme", "redirect_uri": _REDIRECT, "scope": "user"}
    )
    assert resp.status_code == 404


def test_unconfigured_provider_is_400_naming_the_setting(ctx, monkeypatch):
    tc, fake_redis = ctx
    monkeypatch.setattr(config.llm_oauth, "openai_client_id", "")
    resp = tc.post(
        "/api/llm-auth/oauth/initiate", json={"provider_name": "openai", "redirect_uri": _REDIRECT, "scope": "user"}
    )
    assert resp.status_code == 400
    assert "AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_ID" in resp.json()["detail"]
    assert not fake_redis.store
    device = tc.post("/api/llm-auth/device/initiate", json={"provider_name": "openai", "scope": "user"})
    assert device.status_code == 400


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://evil.example.net/preferences/oauth/callback",
        "not-a-url",
        config.frontend_url.replace("://", "://x") + "/preferences/oauth/callback",
        config.frontend_url + "/somewhere/else",  # L2: right origin, wrong path
        config.frontend_url + "/preferences/oauth/callback?next=/admin",  # L2: exact path only
    ],
)
def test_redirect_uri_other_than_the_exact_callback_is_400(ctx, hf_configured, redirect_uri):
    tc, fake_redis = ctx
    body = {"provider_name": "huggingface", "redirect_uri": redirect_uri, "scope": "user"}
    resp = tc.post("/api/llm-auth/oauth/initiate", json=body)
    assert resp.status_code == 400
    assert not fake_redis.store
