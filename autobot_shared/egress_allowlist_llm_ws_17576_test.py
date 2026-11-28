# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM websocket and the local LLM server origins are internal, exactly (#17576, AC4 slice 3).

Each origin is derived from its SSOT source (``config.slm_url`` with the scheme mapped, ``config.llm.lmstudio_host``,
``config.vllm_host``). For each: the exact origin is internal, another port is not, another host is not.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autobot_shared import egress_allowlist as al


@pytest.fixture(autouse=True)
def _ssot(monkeypatch):
    fake = SimpleNamespace(
        frontend_url="http://127.0.0.1:5173",
        vm=SimpleNamespace(main="127.0.0.1", browser="127.0.0.1"),
        port=SimpleNamespace(vnc=6080),
        slm_url="https://slm.test:443/slm",
        llm=SimpleNamespace(lmstudio_host="http://lms.test:1234"),
        vllm_host="http://vllm.test:8000",
    )
    monkeypatch.setattr("autobot_shared.ssot_config.config", fake)
    monkeypatch.setattr(al, "_ssot_service_urls", al._server_called_urls)
    al.reset_internal_origin_state()
    yield
    al.reset_internal_origin_state()


@pytest.mark.parametrize(
    "exact,other_port,other_host",
    [
        ("wss://slm.test:443/slm/api/ws/events", "wss://slm.test:8443/api/ws/events", "wss://other.test:443/x"),
        ("http://lms.test:1234/v1/models", "http://lms.test:1235/v1/models", "http://other.test:1234/v1/models"),
        ("http://vllm.test:8000/v1/models", "http://vllm.test:8001/v1/models", "http://other.test:8000/v1/models"),
    ],
    ids=["slm_websocket", "lmstudio", "vllm"],
)
@pytest.mark.asyncio
async def test_exact_origin_is_internal_other_port_and_host_are_not(exact, other_port, other_host):
    assert await al.is_internal_origin(exact)
    assert not await al.is_internal_origin(other_port)
    assert not await al.is_internal_origin(other_host)


@pytest.mark.asyncio
async def test_the_websocket_origin_is_the_slm_origin_with_only_the_scheme_mapped(monkeypatch):
    assert await al.is_internal_origin("wss://slm.test:443/x")
    assert not await al.is_internal_origin("ws://slm.test:443/x")  # scheme is part of the origin
    assert al._ws_scheme("http://h:80/p") == "ws://h:80/p"
    assert al._ws_scheme("https://h:8443") == "wss://h:8443"


@pytest.mark.asyncio
async def test_a_config_llm_base_url_is_not_internal():
    """OpenAI / Anthropic / custom base URLs stay public-only: no allowlist source reads them."""
    assert not await al.is_internal_origin("http://gateway.test:4000/v1")
