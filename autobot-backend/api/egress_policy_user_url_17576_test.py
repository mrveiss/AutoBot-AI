# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""User-supplied URLs in ``api/`` are public-only: an internal origin is refused (#17576, AC4 slice 2).

``provider_auth`` (device authorization / token URLs) and ``marketplace_sources`` (catalog URL) fetch a URL
the requester chose. ``EGRESS_POLICY`` would trust an AutoBot-internal origin, letting the requester aim the
server at its own services; these sites use the public-only ``assert_public_egress``. Everything the
function does after the guard (connector, session) is stubbed, and the validators that run *before* the guard
are bypassed, so the guard is the only thing that can refuse.
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api import marketplace_sources, provider_auth, schemas_llm_auth
from autobot_shared import egress_allowlist as al
from autobot_shared.ssot_config import config

PUBLIC_URL = "https://api.example.test/oauth"
PUBLIC_IP = "93.184.216.34"
INTERNAL_URLS = [
    pytest.param(lambda: config.backend_url + "/api/x", id="ssot_backend_origin"),
    pytest.param(lambda: config.ollama_url + "/api/x", id="ssot_ollama_origin"),
    pytest.param(lambda: "http://127.0.0.1:8001/api/x", id="loopback"),
    pytest.param(lambda: "http://10.1.2.3:8001/api/x", id="private"),
    pytest.param(lambda: "http://169.254.169.254/latest/meta-data/", id="metadata"),
]


class _Reached(Exception):
    """Raised by the stubbed session constructor: the guard let the request through."""


@pytest.fixture(autouse=True)
def _clean_allowlist():
    al.reset_internal_origin_state()
    yield
    al.reset_internal_origin_state()


@pytest.fixture
def stubs(monkeypatch):
    """Bypass every pre-guard validator and make session construction the observable 'request left'."""
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
    )
    monkeypatch.setattr(provider_auth, "_validate_outbound_url", lambda url: None)
    monkeypatch.setattr(provider_auth, "_pinned_connector", AsyncMock(return_value=None))
    monkeypatch.setattr(provider_auth, "get_redis_client", lambda database="main": None)
    monkeypatch.setattr(marketplace_sources, "_validate_url_scheme", lambda url: None)
    monkeypatch.setattr(marketplace_sources, "resolve_safe_ip_async", AsyncMock(return_value=PUBLIC_IP))
    session_ctor = MagicMock(side_effect=_Reached)
    monkeypatch.setattr("aiohttp.ClientSession", session_ctor)
    return session_ctor


async def _catalog(url):
    await marketplace_sources._fetch_catalog_document(url)


#: (site, status of the refusal). provider_auth.device_initiate / device_poll are NOT listed: since
#: #19241/#19259 they take no caller URL (the device and token URLs are operator config, validated server-side
#: by ``_validate_outbound_url`` and guarded by ``assert_public_egress`` in ``_post_form``, api/provider_auth.py),
#: so the user-URL surface is closed -- see ``test_device_flow_requests_reject_a_caller_url`` below.
#: The catalog fetch maps an egress refusal to 400 with its other URL rejections.
SITES = [
    pytest.param(_catalog, 400, id="marketplace_sources.fetch_catalog"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("site,refusal_status", SITES)
@pytest.mark.parametrize("make_url", INTERNAL_URLS)
async def test_internal_or_private_user_url_is_refused_before_a_session_exists(site, refusal_status, make_url, stubs):
    with pytest.raises(HTTPException) as refused:
        await site(make_url())
    assert refused.value.status_code == refusal_status
    stubs.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("site,refusal_status", SITES)
async def test_public_user_url_passes_the_guard(site, refusal_status, stubs):
    with pytest.raises(_Reached):
        await site(PUBLIC_URL)
    stubs.assert_called_once()


@pytest.mark.asyncio
async def test_internal_origin_is_trusted_by_policy_but_not_here(stubs):
    """The key property: the same origin ``EGRESS_POLICY`` waves through is refused for a user-supplied URL."""
    from autobot_shared.http_egress_guard import assert_egress_policy

    await assert_egress_policy(config.backend_url + "/api/x")
    with pytest.raises(HTTPException):
        await _catalog(config.backend_url + "/api/x")


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (schemas_llm_auth.DeviceInitiateRequest, {"provider_name": "p", "scope": "user"}),
        (schemas_llm_auth.DevicePollRequest, {"provider_name": "p", "device_code": "d"}),
    ],
    ids=["device_initiate", "device_poll"],
)
@pytest.mark.parametrize("field", ["device_authorization_url", "token_url"])
def test_device_flow_requests_reject_a_caller_url(model, kwargs, field):
    """Contrast for the removed cases: the surface is closed (#19241/#19259), not the test dropped."""
    model(**kwargs)  # control: the model is valid without the extra field
    with pytest.raises(ValidationError) as rejected:
        model(**kwargs, **{field: PUBLIC_URL})
    assert rejected.value.errors()[0]["type"] == "extra_forbidden"
