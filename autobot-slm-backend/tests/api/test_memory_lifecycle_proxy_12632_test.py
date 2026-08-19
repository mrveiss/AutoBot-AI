# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM aggregator degrades and composes (#12632, umbrella #12630).

Two properties carry the weight:

* **It never raises to the client.** A monitoring surface that 5xxs when a node is
  down tells an operator less than one that says which node it could not read.
* **`degraded` composes.** The node reports its own partial reads (#12631). A proxy
  that only surfaced transport failures would show a node whose decay section is
  broken as perfectly healthy — the node would be shouting and the operator's
  screen would be calm.

The second is the one worth testing hardest, because the first fails loudly and
the second fails silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

pytest.importorskip("httpx")

from api import memory_lifecycle_proxy as proxy  # noqa: E402


class _Response:
    def __init__(self, status_code: int, payload: Any = None, *, bad_json: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self) -> Any:
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


class _Client:
    """Stands in for httpx.AsyncClient, returning a scripted response or raising."""

    def __init__(self, result):
        self._result = result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, *_a, **_k):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _install(monkeypatch, result, *, key: str = "k", url: str = "https://node") -> None:
    monkeypatch.setattr(proxy, "_INTERNAL_API_KEY", key)
    monkeypatch.setattr(proxy, "_NODE_URL", url)
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **_k: _Client(result))


_HEALTHY: Dict[str, Any] = {
    "reinforcement": {"hot": [{"fact_id": "a"}], "cold": [{"fact_id": "b"}]},
    "decay": {"last_run": "2026-08-19T00:00:00Z", "config": {"epoch_set": True}, "prune_preview": []},
    "degraded": False,
}


@pytest.mark.asyncio
async def test_a_healthy_node_is_reported_healthy(monkeypatch):
    _install(monkeypatch, _Response(200, _HEALTHY))
    body = await proxy.get_memory_lifecycle(limit=5, _user=None)

    assert body["degraded"] is False
    assert body["nodes"][0]["reinforcement"]["hot"] == [{"fact_id": "a"}]


@pytest.mark.asyncio
async def test_a_partially_degraded_node_is_not_reported_healthy(monkeypatch):
    """The composition property. This is the one that fails silently."""
    _install(monkeypatch, _Response(200, {**_HEALTHY, "degraded": True}))
    body = await proxy.get_memory_lifecycle(limit=5, _user=None)

    assert body["degraded"] is True, "a degraded node was reported as healthy by the aggregator"
    assert body["nodes"][0]["degraded"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected",
    [
        (proxy.httpx.ConnectError("refused"), "node_unreachable"),
        (proxy.httpx.TimeoutException("slow"), "node_timeout"),
        (_Response(403), "node_status_403"),
        (_Response(404), "node_status_404"),
        (_Response(200, None, bad_json=True), "node_bad_payload"),
    ],
)
async def test_every_failure_mode_degrades_rather_than_raising(monkeypatch, failure, expected):
    """Each cause is reported distinctly.

    403 means the key is wrong, 404 means the node predates #12631, a timeout
    means it is alive but slow — an operator acts differently on each, so
    collapsing them all into "unreachable" would throw away the diagnosis.
    """
    _install(monkeypatch, failure)
    body = await proxy.get_memory_lifecycle(limit=5, _user=None)

    assert body["degraded"] is True
    assert body["nodes"][0]["error"] == expected


@pytest.mark.asyncio
async def test_a_missing_internal_key_is_named_as_config_not_as_a_node_fault(monkeypatch):
    """Otherwise an operator checks the node when the fault is a variable here."""
    _install(monkeypatch, _Response(200, _HEALTHY), key="")
    body = await proxy.get_memory_lifecycle(limit=5, _user=None)

    assert body["degraded"] is True
    assert body["nodes"][0]["error"] == "internal_api_key_not_configured"


@pytest.mark.asyncio
async def test_an_unreachable_node_still_has_every_section_key(monkeypatch):
    """A consumer must never branch on whether a key exists.

    A missing `reinforcement` and an empty one mean the same thing to a reader
    and different things to code.
    """
    _install(monkeypatch, proxy.httpx.ConnectError("refused"))
    node = (await proxy.get_memory_lifecycle(limit=5, _user=None))["nodes"][0]

    assert node["reinforcement"] == {"hot": [], "cold": []}
    assert set(node["decay"]) >= {"last_run", "config", "prune_preview"}


@pytest.mark.asyncio
async def test_the_payload_nests_per_node(monkeypatch):
    """Fleet-aware in shape even at one node, so a second is a loop here rather
    than a breaking change to every consumer."""
    _install(monkeypatch, _Response(200, _HEALTHY))
    body = await proxy.get_memory_lifecycle(limit=5, _user=None)

    assert isinstance(body["nodes"], list)
    assert body["nodes"][0]["node"] == "https://node"


def test_tls_verification_is_on_unless_explicitly_disabled(monkeypatch):
    """Verify by default, opt out explicitly.

    An earlier revision read its own `AUTOBOT_NODE_PROXY_VERIFY_TLS` with a
    "false" default, shipping verification OFF unless an operator opted in — the
    inverse of the `voice_proxy` pattern this module cites, on the channel that
    carries the internal API key. Pinned by reloading the module under both env
    states, because the value is captured at import.
    """
    import importlib

    monkeypatch.delenv("AUTOBOT_SKIP_TLS_VERIFY", raising=False)
    assert importlib.reload(proxy)._VERIFY_TLS is True, "TLS verification is off by default"

    monkeypatch.setenv("AUTOBOT_SKIP_TLS_VERIFY", "true")
    assert importlib.reload(proxy)._VERIFY_TLS is False, "the documented opt-out no longer works"

    monkeypatch.delenv("AUTOBOT_SKIP_TLS_VERIFY", raising=False)
    importlib.reload(proxy)


def test_the_same_opt_out_variable_as_the_sibling_proxies(monkeypatch):
    """One switch for every node proxy, not a second one only this module reads.

    A per-module variable means an operator disabling verification for a
    self-signed dev node silently leaves this proxy verifying, or vice versa.
    """
    import ast

    source = (Path(__file__).resolve().parents[2] / "api" / "memory_lifecycle_proxy.py").read_text(encoding="utf-8")
    # Read from the AST, not the text: the module's own comment names the rejected
    # variable to explain why it is gone, and a substring check would trip on that
    # explanation rather than on any code.
    read_vars = {
        node.args[0].value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"getenv", "get"}
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert "AUTOBOT_SKIP_TLS_VERIFY" in read_vars, f"the shared opt-out is not read; found {sorted(read_vars)}"
    private = {v for v in read_vars if "VERIFY_TLS" in v and v != "AUTOBOT_SKIP_TLS_VERIFY"}
    assert not private, f"a private TLS switch was reintroduced: {sorted(private)}"
