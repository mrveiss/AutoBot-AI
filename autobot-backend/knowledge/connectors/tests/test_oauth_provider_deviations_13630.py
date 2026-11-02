# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""OAuthProvider deviation fields (#13630): defaults are byte-identical, each deviation is honoured."""

import base64
import dataclasses
from types import SimpleNamespace

import pytest

from knowledge.connectors import oauth_flow

pytestmark = pytest.mark.asyncio


class _Capture:
    """Stands in for aiohttp.ClientSession and records the one POST it receives."""

    posts: list = []

    def __init__(self, *a, **k):
        pass

    def post(self, url, **kwargs):
        _Capture.posts.append((url, kwargs))
        return self

    async def json(self, content_type=None):
        return self.body

    status = 200
    body: dict = {"access_token": "at"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def capture(monkeypatch):
    _Capture.posts = []
    _Capture.body = {"access_token": "at"}
    monkeypatch.setattr(oauth_flow.aiohttp, "ClientSession", _Capture)
    return _Capture


def _provider(**overrides):
    return dataclasses.replace(oauth_flow.get_provider("google"), **overrides)


async def _exchange(provider):
    return await oauth_flow.exchange_code(provider, "cid", "csec", "code1", "https://app/cb", "ver")


async def test_every_registered_provider_posts_the_pre_change_request():
    assert len(oauth_flow.OAUTH_PROVIDERS) >= 3, "an empty registry would make this loop pass vacuously"
    for provider in oauth_flow.OAUTH_PROVIDERS.values():
        assert provider.token_endpoint_auth_method == "client_secret_post" and provider.token_request_encoding == "form"
        _Capture.posts.clear()
        await _exchange(provider)
        await oauth_flow.refresh_access_token(provider.token_url, "cid", "csec", "rt", provider=provider)
        (xurl, xkw), (rurl, rkw) = _Capture.posts
        assert xurl == rurl == provider.token_url
        assert list(xkw["data"].items()) == [
            ("grant_type", "authorization_code"),
            ("code", "code1"),
            ("redirect_uri", "https://app/cb"),
            ("client_id", "cid"),
            ("client_secret", "csec"),
            ("code_verifier", "ver"),
        ]
        assert list(rkw["data"].items()) == [
            ("grant_type", "refresh_token"),
            ("refresh_token", "rt"),
            ("client_id", "cid"),
            ("client_secret", "csec"),
        ]
        assert xkw["headers"] == rkw["headers"] == {"Accept": "application/json"}
        assert "json" not in xkw and xkw["allow_redirects"] is False


async def test_the_golden_comparison_can_fail():
    """Contrast case: a deviating provider must NOT produce the golden request."""
    _Capture.posts.clear()
    await _exchange(_provider(token_endpoint_auth_method="client_secret_basic", token_request_encoding="json"))
    _, kw = _Capture.posts[0]
    assert "data" not in kw and "Authorization" in kw["headers"]


async def test_separate_refresh_url_applies_to_refresh_only():
    provider = _provider(refresh_url="https://example.test/refresh")
    await _exchange(provider)
    await oauth_flow.refresh_access_token(provider.token_url, "cid", "csec", "rt", provider=provider)
    assert [url for url, _ in _Capture.posts] == [provider.token_url, "https://example.test/refresh"]


async def test_basic_auth_moves_credentials_to_the_header():
    provider = _provider(token_endpoint_auth_method="client_secret_basic")
    await _exchange(provider)
    _, kw = _Capture.posts[0]
    assert "client_id" not in kw["data"] and "client_secret" not in kw["data"]
    assert kw["headers"]["Authorization"] == "Basic " + base64.b64encode(b"cid:csec").decode()


async def test_public_client_sends_id_only():
    await _exchange(_provider(token_endpoint_auth_method="none"))
    data = _Capture.posts[0][1]["data"]
    assert data["client_id"] == "cid" and "client_secret" not in data


async def test_unknown_auth_method_is_refused_not_silently_posted():
    with pytest.raises(ValueError, match="token_endpoint_auth_method"):
        await _exchange(_provider(token_endpoint_auth_method="private_key_jwt"))
    assert _Capture.posts == []


async def test_json_encoding_sends_a_json_body():
    await _exchange(_provider(token_request_encoding="json"))
    kw = _Capture.posts[0][1]
    assert kw["json"]["code"] == "code1" and "data" not in kw


async def test_per_grant_renames_are_independent():
    provider = _provider(exchange_param_names={"code": "auth_code"}, refresh_param_names={"refresh_token": "rtok"})
    await _exchange(provider)
    await oauth_flow.refresh_access_token(provider.token_url, "cid", "csec", "rt", provider=provider)
    (_, xkw), (_, rkw) = _Capture.posts
    assert "auth_code" in xkw["data"] and "code" not in xkw["data"] and "rtok" not in xkw["data"]
    assert "rtok" in rkw["data"] and "refresh_token" not in rkw["data"]


async def test_response_envelope_is_unwrapped_and_a_missing_one_fails_loudly():
    provider = _provider(token_response_envelope_key="data")
    _Capture.body = {"code": 0, "data": {"access_token": "inner"}, "message": "ok"}
    assert (await _exchange(provider))["access_token"] == "inner"
    _Capture.body = {"access_token": "bare"}
    with pytest.raises(RuntimeError, match="no 'data' object"):
        await _exchange(provider)


def test_scope_separator_default_and_comma():
    args = ("cid", "https://app/cb", "st", "chal", ("a", "b"))
    assert "scope=a+b" in oauth_flow.build_authorize_url(_provider(), *args)
    assert "scope=a%2Cb" in oauth_flow.build_authorize_url(_provider(scope_separator=","), *args)


def test_extra_client_config_must_be_set_before_authorization(monkeypatch):
    auth = SimpleNamespace(google_oauth_client_id="i", google_oauth_client_secret="s", tenant_fixture="")
    monkeypatch.setattr(oauth_flow, "config", SimpleNamespace(auth=auth))
    provider = _provider(extra_client_config_settings=("tenant_fixture",))
    with pytest.raises(ValueError, match="tenant_fixture"):
        oauth_flow.resolve_client_credentials(provider)
    auth.tenant_fixture = "t1"
    assert oauth_flow.resolve_client_credentials(provider) == ("i", "s")
    assert oauth_flow.resolve_extra_client_config(provider) == {"tenant_fixture": "t1"}
    assert oauth_flow.resolve_client_credentials(_provider()) == ("i", "s")
