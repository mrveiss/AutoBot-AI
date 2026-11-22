# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20760: the SLM's proxies call the main backend through ONE client, and answer the same way."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from services import main_backend_client as backend

_API = Path(__file__).resolve().parents[2] / "api"
_PROXIES = ("voice_proxy.py", "personality_proxy.py", "memory_lifecycle_proxy.py")


class _Client:
    def __init__(self, result) -> None:
        self.result, self.calls = result, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _install(monkeypatch, result, key: str = "k") -> _Client:
    client = _Client(result)
    if key:
        monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", key)
    else:
        monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY", raising=False)
    monkeypatch.setattr(backend, "backend_url", lambda: "https://backend/")
    monkeypatch.setattr(backend.node_proxy, "node_client", lambda **_k: client)
    return client


class _Request:
    method, headers = "POST", {"Content-Type": "application/json"}

    async def body(self) -> bytes:
        return b'{"x": 1}'


@pytest.mark.asyncio
async def test_a_passthrough_returns_the_backends_answer_as_is(monkeypatch) -> None:
    answer = SimpleNamespace(content=b"nope", status_code=401, headers={"content-type": "application/json"})
    client = _install(monkeypatch, answer)
    response = await backend.forward_to_main_backend(_Request(), "voice/speak", "Voice")
    assert (response.status_code, response.body) == (401, b"nope")
    method, url, kwargs = client.calls[0]
    assert (method, url, kwargs["content"]) == ("POST", "https://backend/api/voice/speak", b'{"x": 1}')
    assert kwargs["headers"]["X-Internal-API-Key"] == "k"  # pragma: allowlist secret -- a fixture value


@pytest.mark.asyncio
@pytest.mark.parametrize("service", ["Voice", "Personality"])
async def test_a_missing_key_is_the_same_503_on_every_passthrough(monkeypatch, service: str) -> None:
    client = _install(monkeypatch, None, key="")
    with pytest.raises(HTTPException) as refused:
        await backend.forward_to_main_backend(_Request(), "x", service)
    assert refused.value.status_code == 503
    assert refused.value.detail == f"{service} service not configured (missing internal API key)"
    assert client.calls == [], "nothing is sent without the key"


@pytest.mark.asyncio
async def test_a_transport_failure_is_the_shared_classification(monkeypatch) -> None:
    _install(monkeypatch, httpx.ConnectError("refused"))
    with pytest.raises(backend.MainBackendUnavailable) as unavailable:
        await backend.call_main_backend("GET", "memory/lifecycle")
    assert unavailable.value.reason == backend.node_proxy.REASON_UNREACHABLE


def test_no_proxy_keeps_its_own_copy_of_the_call() -> None:
    """One client: no `_proxy_to_main_backend`, and every proxy reaches the backend through the client."""
    for name in _PROXIES:
        source = (_API / name).read_text(encoding="utf-8")
        defined = {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.AsyncFunctionDef)}
        assert "_proxy_to_main_backend" not in defined, name
        assert "services.main_backend_client" in source, name
        assert "node_proxy.internal_headers" not in source, f"{name} builds its own request again"


@pytest.mark.asyncio
async def test_a_timeout_is_a_504(monkeypatch) -> None:
    _install(monkeypatch, httpx.TimeoutException("slow"))
    with pytest.raises(HTTPException) as refused:
        await backend.forward_to_main_backend(_Request(), "voice/speak", "Voice")
    assert refused.value.status_code == 504


@pytest.mark.asyncio
async def test_an_unset_backend_url_is_a_503_not_configured(monkeypatch) -> None:
    """resolve_node_url returns "" when neither AUTOBOT_BACKEND_URL nor the authority base is set."""
    client = _install(monkeypatch, None)
    monkeypatch.setattr(backend, "backend_url", lambda: "")
    with pytest.raises(HTTPException) as refused:
        await backend.forward_to_main_backend(_Request(), "voice/speak", "Voice")
    assert (refused.value.status_code, refused.value.detail) == (503, "Voice service not configured")
    assert client.calls == []


@pytest.mark.asyncio
async def test_the_personality_root_keeps_its_trailing_slash(monkeypatch) -> None:
    from api import personality_proxy

    answer = SimpleNamespace(content=b"{}", status_code=200, headers={"content-type": "application/json"})
    client = _install(monkeypatch, answer)
    root = next(route.endpoint for route in personality_proxy.router.routes if route.path.endswith("/personality/"))
    await root(request=_Request(), current_user={"admin": True})
    assert client.calls[0][1] == "https://backend/api/personality/"


@pytest.mark.asyncio
async def test_the_memory_proxy_names_a_missing_key_as_config(monkeypatch) -> None:
    from api import memory_lifecycle_proxy

    _install(monkeypatch, None, key="")
    monkeypatch.setattr(memory_lifecycle_proxy, "backend_url", lambda: "https://backend")
    body = await memory_lifecycle_proxy.get_memory_lifecycle(limit=5, _user=None)
    assert body["degraded"] is True
    assert body["nodes"][0]["error"] == backend.node_proxy.REASON_KEY_NOT_CONFIGURED


@pytest.mark.asyncio
@pytest.mark.parametrize("status, reported", [(401, True), (403, False), (500, False), (200, False)])
async def test_a_refused_internal_key_is_reported_once_whichever_proxy_met_it(monkeypatch, status, reported) -> None:
    """#20750's finding, in the one client: a 401 on the internal key reports; any other answer doesn't."""
    from unittest.mock import AsyncMock

    report = AsyncMock()
    monkeypatch.setattr(backend, "report_backend_refused_internal_key", report)
    answer = SimpleNamespace(content=b"{}", status_code=status, headers={"content-type": "application/json"})
    _install(monkeypatch, answer)
    response = await backend.forward_to_main_backend(_Request(), "personality/toggle", "Personality")
    assert response.status_code == status, "the backend's answer still goes back unchanged"
    await asyncio.gather(*backend._pending_reports)  # the report runs in the background
    if reported:
        report.assert_awaited_once_with("/api/personality/toggle")
    else:
        report.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failing_report_never_costs_the_caller_its_answer(monkeypatch) -> None:
    """The report runs in the background: a reporter that raises still leaves the 401 returned, and is logged."""

    async def broken(_path):
        raise RuntimeError("db down")

    monkeypatch.setattr(backend, "report_backend_refused_internal_key", broken)
    answer = SimpleNamespace(content=b"{}", status_code=401, headers={"content-type": "application/json"})
    _install(monkeypatch, answer)
    response = await backend.forward_to_main_backend(_Request(), "voice/speak", "Voice")
    assert response.status_code == 401
    await asyncio.gather(*backend._pending_reports, return_exceptions=True)
    assert not backend._pending_reports, "the finished task is released"
