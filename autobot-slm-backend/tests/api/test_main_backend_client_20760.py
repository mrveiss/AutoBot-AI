# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20760: the SLM's proxies call the main backend through ONE client, and answer the same way."""

from __future__ import annotations

import ast
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
