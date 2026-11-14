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
from urllib.parse import urlparse

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
    "http://[::1]/",  # IPv6 loopback
    "http://[::ffff:169.254.169.254]/",  # v4-mapped cloud metadata
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


# --- a server-supplied next-page link must not take the bearer token elsewhere (#17576)

_GRAPH = "https://graph.microsoft.com/v1.0"
_PAGE_ONE = f"{_GRAPH}/me/drive/root/children"


def _paging_session(first_body: dict, second_body: dict | None = None) -> MagicMock:
    """A session answering the first listing with *first_body*, any later URL with *second_body*."""
    session = MagicMock()
    calls: list[tuple[str, dict]] = []

    async def _request(method, url, **kwargs):
        calls.append((url, kwargs.get("headers", {})))
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=first_body if len(calls) == 1 else (second_body or {}))
        resp.release = MagicMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    session.request = AsyncMock(side_effect=_request)
    session.calls = calls
    return session


async def _list_files(session: MagicMock, method: str = "_list_all_files"):
    from autobot_shared.http_client import get_http_client

    connector = OneDriveConnector(_config({}))
    with (
        patch.object(type(get_http_client()), "get_session", AsyncMock(return_value=session)),
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO),
    ):
        if method == "_list_all_files":
            return await connector._list_all_files()
        return await connector._list_folder_recursive("folder-1")


def _file(name: str) -> dict:
    return {"id": name, "name": f"{name}.md", "file": {}, "size": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["_list_all_files", "_list_folder_recursive"])
@pytest.mark.parametrize(
    "evil",
    [
        "https://attacker.example.com/steal",  # public, so the egress guard alone would allow it
        "https://graph.microsoft.com.attacker.example.com/v1.0/x",  # prefix lookalike
        "https://graph.microsoft.com@attacker.example.com/v1.0/x",  # userinfo trick
        "http://graph.microsoft.com/v1.0/x",  # scheme downgrade
        f"{_GRAPH}/../evil",  # parent segment
        f"{_GRAPH}/%2e%2e/evil",  # encoded parent segment
        f"{_GRAPH}/%2E%2e/evil",  # mixed-case encoded parent segment
        f"{_GRAPH}/%252e%252e/evil",  # double-encoded parent segment
        f"{_GRAPH}/..\\evil",  # backslash variant
        f"{_GRAPH}/%2e%2e%5cevil",  # encoded backslash variant
        "https://graph.microsoft.com:8443/v1.0/x",  # different port
        "https://user@graph.microsoft.com/v1.0/x",  # userinfo host
        "https://graph.microsoft.com:bad/v1.0/x",  # malformed port
    ],
)
async def test_an_off_graph_next_link_is_never_requested(method, evil):
    session = _paging_session({"value": [_file("a")], "@odata.nextLink": evil}, {"value": [_file("b")]})

    files = await _list_files(session, method)

    requested = [url for url, _ in session.calls]
    assert len(requested) == 1, requested
    assert all(urlparse(u).hostname == "graph.microsoft.com" for u in requested)
    assert [f["id"] for f in files] == ["a"], "pages already read are kept"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["_list_all_files", "_list_folder_recursive"])
async def test_an_on_graph_next_link_is_still_followed(method):
    nxt = f"{_GRAPH}/me/drive/root/children?$skiptoken=abc"
    await _assert_followed(method, nxt)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["_list_all_files", "_list_folder_recursive"])
async def test_a_deeper_on_base_next_link_is_still_followed(method):
    await _assert_followed(method, f"{_GRAPH}/drives/b!x/items/y/children?$skiptoken=a..b")


async def _assert_followed(method, nxt):
    session = _paging_session({"value": [_file("a")], "@odata.nextLink": nxt}, {"value": [_file("b")]})

    files = await _list_files(session, method)

    assert [url for url, _ in session.calls][1] == nxt
    assert session.calls[1][1]["Authorization"].startswith("Bearer ")
    assert [f["id"] for f in files] == ["a", "b"]


@pytest.mark.asyncio
async def test_contrast_the_unchecked_link_would_have_been_requested_with_the_token():
    """Without the check the same off-host link passes the egress guard and is sent the token."""
    evil = "https://attacker.example.com/steal"
    session = _paging_session({"value": [], "@odata.nextLink": evil}, {"value": []})
    with patch("knowledge.connectors.onedrive.next_link_on_base", lambda link, base, log: link):
        await _list_files(session)

    assert [url for url, _ in session.calls][1:] == [evil]
    assert session.calls[1][1]["Authorization"].startswith("Bearer ")
