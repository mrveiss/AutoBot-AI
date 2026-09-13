# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No node proxy may hold its own opinion about TLS, timeouts or keys (#14886).

The defect this guards is not a bug in any one proxy. It is that there were
three of them, each free to answer the same question differently — and one
already did: `memory_lifecycle_proxy` shipped a `"false"`-defaulted TLS flag to
review (#14653), inverting verification on the channel carrying the internal
API key. So the assertions come in two halves:

* the **policy** half — the shared client's defaults, asserted directly, because
  a default that has to be opted into is not a default;
* the **spread** half — a sweep of `autobot-slm-backend/api/` proving no proxy
  reads that policy for itself. Its population floor is checked first: a sweep
  that matches nothing reports "no private switches" in the same words as a
  clean tree, which is how a guard becomes decoration.
"""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from autobot_shared import node_proxy

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROXY_DIR = _REPO_ROOT / "autobot-slm-backend" / "api"

#: A module is a node proxy if it uses the shared client, or if it still spells
#: the internal-key header itself — the shape a fourth copy-pasted proxy has.
#: Matching both is what lets the sweep catch one that has not migrated.
_PROXY_MARKERS = ('"X-Internal-API-Key"', "node_proxy")

#: voice, personality, memory_lifecycle. Only ever raised when a proxy is added.
_MIN_NODE_PROXIES = 3


def _node_proxy_sources() -> dict[str, str]:
    """Every ``api/*.py`` that talks to a node, by relative path."""
    return {
        path.name: source
        for path in sorted(_PROXY_DIR.glob("*.py"))
        for source in [path.read_text(encoding="utf-8", errors="replace")]
        if any(marker in source for marker in _PROXY_MARKERS)
    }


def _env_reads(source: str) -> set[str]:
    """Environment variable names read anywhere in *source*, from the AST.

    Read from the AST and not the text because a module's comment may name a
    variable in order to explain why it is gone — #14653's rejected
    ``AUTOBOT_NODE_PROXY_VERIFY_TLS`` is documented in exactly that way.
    """
    return {
        node.args[0].value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"getenv", "get"}
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------


def test_tls_verification_is_on_by_default(monkeypatch) -> None:
    """#14653 in one assertion. A default that must be opted into is not one."""
    monkeypatch.delenv("AUTOBOT_SKIP_TLS_VERIFY", raising=False)
    assert node_proxy.verify_tls() is True, "TLS verification ships OFF — the #14653 inversion is back"


@pytest.mark.parametrize("value,expected", [("true", False), ("TRUE", False), ("false", True), ("", True)])
def test_only_the_documented_opt_out_disables_verification(monkeypatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("AUTOBOT_SKIP_TLS_VERIFY", value)
    assert node_proxy.verify_tls() is expected


def test_the_timeout_is_configurable_and_defaults(monkeypatch) -> None:
    """The env-backed form came from memory_lifecycle_proxy; the other two had 15.0."""
    monkeypatch.delenv("AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS", raising=False)
    assert node_proxy.node_timeout() == node_proxy.DEFAULT_TIMEOUT_SECONDS

    monkeypatch.setenv("AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS", "42")
    assert node_proxy.node_timeout() == 42.0

    monkeypatch.setenv("AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS", "not-a-number")
    assert node_proxy.node_timeout() == node_proxy.DEFAULT_TIMEOUT_SECONDS, "a bad value must not crash a proxy"


def test_the_explicit_url_wins_over_the_authority_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_BACKEND_URL", "https://node.internal:8443/")
    assert node_proxy.resolve_node_url("https://authority.internal") == "https://node.internal:8443"

    monkeypatch.delenv("AUTOBOT_BACKEND_URL", raising=False)
    assert node_proxy.resolve_node_url("https://authority.internal/") == "https://authority.internal"
    assert node_proxy.resolve_node_url("") == "", "an unconfigured node must be reported, not requested"


def test_headers_always_carry_the_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", "k")
    assert node_proxy.internal_headers() == {"X-Internal-API-Key": "k"}
    assert node_proxy.internal_headers("audio/wav")["Content-Type"] == "audio/wav"


@pytest.mark.parametrize(
    "exc,reason,code",
    [
        (httpx.TimeoutException("slow"), node_proxy.REASON_TIMEOUT, 504),
        (httpx.ConnectError("refused"), node_proxy.REASON_UNREACHABLE, 503),
        (httpx.ReadError("mid-flight"), node_proxy.REASON_UNREACHABLE, 503),
    ],
)
def test_every_transport_failure_is_mapped(exc: Exception, reason: str, code: int) -> None:
    """The catch-all only memory_lifecycle_proxy had. A ReadError used to escape
    voice_proxy and personality_proxy as an unhandled 500."""
    failure = node_proxy.classify_transport_error(exc)
    assert (failure.reason, failure.status_code) == (reason, code)
    assert failure.detail == node_proxy.FAILURE_DETAIL[reason]


# ---------------------------------------------------------------------------
# The spread
# ---------------------------------------------------------------------------


def test_no_node_proxy_reads_the_policy_for_itself() -> None:
    sources = _node_proxy_sources()
    assert len(sources) >= _MIN_NODE_PROXIES, (
        f"FIX THE SWEEP: {len(sources)} node proxies found under {_PROXY_DIR.name}/, "
        f"expected at least {_MIN_NODE_PROXIES} (voice, personality, memory_lifecycle). "
        f"Markers searched: {_PROXY_MARKERS}. A sweep that matches nothing reports "
        "a clean tree in the same words as a clean tree."
    )

    offenders: dict[str, list[str]] = {}
    for name, source in sources.items():
        private = sorted(v for v in _env_reads(source) if "TLS" in v or "TIMEOUT" in v or "INTERNAL_API_KEY" in v)
        if private:
            offenders[name] = private
    assert offenders == {}, (
        f"node proxies reading policy themselves: {offenders}. Every one of those "
        "is a place a security default can silently invert (#14653) — take it "
        "from autobot_shared.node_proxy instead."
    )


def test_no_node_proxy_builds_its_own_http_client() -> None:
    sources = _node_proxy_sources()
    assert len(sources) >= _MIN_NODE_PROXIES, f"FIX THE SWEEP: only {len(sources)} node proxies reached"

    offenders = sorted(name for name, source in sources.items() if "httpx.AsyncClient(" in source)
    assert offenders == [], (
        f"{offenders} construct their own httpx client, so verify= and timeout= "
        "are theirs to get wrong again — use node_proxy.node_client()."
    )


def test_every_node_proxy_uses_the_shared_client() -> None:
    sources = _node_proxy_sources()
    assert len(sources) >= _MIN_NODE_PROXIES, f"FIX THE SWEEP: only {len(sources)} node proxies reached"

    unmigrated = sorted(name for name, source in sources.items() if "node_proxy." not in source)
    assert unmigrated == [], f"{unmigrated} still hand-roll the node call — #14886"
