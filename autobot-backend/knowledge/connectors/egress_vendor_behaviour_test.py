# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The four vendor connectors, exercised end to end through the real guard (#17576).

``egress_policy_test.py`` proves the policy is *written* at every call site. These
tests prove it *behaves*: the shared client's real ``guard_egress`` runs, only the
network below it is faked, so a call that is refused never reaches the session.

For each connector: the default vendor host is allowed (DNS faked to a public
address); an operator-overridden base pointing at the cloud-metadata endpoint, a
loopback address or a private address is refused, and the session is never touched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.connectors.gdrive import GoogleDriveConnector
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.notion import NotionConnector
from knowledge.connectors.onedrive import OneDriveConnector
from knowledge.connectors.slack import SlackConnector

_PUBLIC_ADDRINFO = [(2, 1, 6, "", ("142.250.74.10", 0))]
_FORBIDDEN_BASES = [
    "http://169.254.169.254/latest",  # cloud metadata
    "http://127.0.0.1:8080",  # loopback
    "http://10.0.0.5/api",  # RFC-1918, and the opt-in is off
]


def _config(extra: dict) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="egress-behaviour",
        connector_type="test",
        name="egress",
        config={"token": "test-fake-credential", **extra},
        enabled=True,
        verification_mode="collaborative",
    )


# connector, override key, call(connector) -> awaitable
_CASES = {
    "gdrive": (GoogleDriveConnector, "api_base", lambda c: c._drive_request("GET", c._api_base + "/files")),
    "onedrive": (OneDriveConnector, "graph_api_base", lambda c: c._graph_request("GET", c._graph_url + "/me/drive")),
    "notion": (NotionConnector, "notion_api_base", lambda c: c._notion_request("GET", "/users/me")),
    "slack": (SlackConnector, "slack_api_base", lambda c: c._slack_post("/auth.test")),
}


def _fake_session() -> MagicMock:
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={"ok": True})
    resp.read = AsyncMock(return_value=b"")
    resp.release = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request = AsyncMock(return_value=resp)
    return session


async def _run(name: str, base: str | None, session: MagicMock):
    from autobot_shared.http_client import get_http_client

    cls, key, call = _CASES[name]
    connector = cls(_config({key: base} if base else {}))
    with (
        patch.object(type(get_http_client()), "get_session", AsyncMock(return_value=session)),
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
    ):
        return await call(connector)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(_CASES))
async def test_the_default_vendor_host_is_allowed(name):
    session = _fake_session()

    result = await _run(name, None, session)

    session.request.assert_awaited_once()
    assert result["status_code"] == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("base", _FORBIDDEN_BASES)
@pytest.mark.parametrize("name", sorted(_CASES))
async def test_an_internal_or_metadata_base_is_refused_before_any_request(name, base):
    session = _fake_session()

    result = await _run(name, base, session)

    session.request.assert_not_called()
    assert result["status_code"] != 200
    assert "disallowed address" in str(result)
