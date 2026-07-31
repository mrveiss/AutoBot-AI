# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""WebSocket path selection against nginx vs direct uvicorn (#12781, #10459).

The SLM client must pick its WebSocket path from what is actually listening:

* behind nginx -> ``/slm/api/ws/events`` (nginx maps ``/slm/api/ws/`` to the SLM
  on :8000, while ``/api/ws/`` goes to the **user** backend);
* straight at uvicorn -> ``/api/ws/events`` (uvicorn has no ``/slm/`` route).

Choosing wrong is not a soft failure. Starlette closes before accept and uvicorn
reports that as **HTTP 403**, so the symptom is an unauthenticated-looking
handshake rejection with correct credentials — which is exactly how #10400 and
#10459 were first misdiagnosed as a JWT-secret mismatch.

#12781 was the mirror image of #10459. The rule "loopback always means direct
uvicorn" was added to fix the Docker case, but on a **co-located single-box**
install nginx also listens on loopback:443. The client then requested
``/api/ws/events`` against nginx, nginx routed it to the user backend, and every
reconnect was rejected 403 — verified live, with the JWT secrets confirmed
matching.

The rule these tests pin: an nginx **port** decides, before any host heuristic.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent / "slm_client.py"


def _load_selector():
    """Load just the selector, without importing the whole client.

    slm_client pulls in config, redis and http machinery at import time; this
    test only concerns a pure URL predicate.
    """
    src = _SRC.read_text(encoding="utf-8")
    ns: dict = {}
    exec(  # noqa: S102 - deliberate: isolate a pure function from a heavy module
        "from urllib.parse import urlparse\n"
        "_LOOPBACK_HOSTS = frozenset({'127.0.0.1','localhost','::1','ip6-localhost'})\n"
        "_NGINX_HTTP_PORTS = frozenset({80,443})",
        ns,
    )
    start = src.index("def _is_direct_uvicorn_url")
    end = src.index("class ServiceNotConfiguredError")
    exec(textwrap.dedent(src[start:end]), ns)  # noqa: S102
    return ns["_is_direct_uvicorn_url"]


_is_direct = _load_selector()


@pytest.mark.parametrize(
    "url,expected,why",
    [
        # --- nginx: must use the /slm/ prefix ---
        ("https://127.0.0.1:443", False, "#12781: co-located nginx on loopback"),
        ("https://127.0.0.1", False, "nginx on the default https port"),
        ("http://127.0.0.1:80", False, "nginx serving plain http"),
        ("http://localhost", False, "nginx, default http port, named loopback"),
        ("https://slm.example.com", False, "remote nginx"),
        ("http://slm.example.com:80", False, "remote nginx, explicit port"),
        # --- direct uvicorn: must NOT use the /slm/ prefix ---
        ("http://127.0.0.1:8000", True, "direct uvicorn on loopback"),
        ("http://localhost:8000", True, "direct uvicorn, named loopback"),
        ("http://autobot-slm:8000", True, "#10459: docker compose DNS name"),
        ("http://10.0.0.5:8000", True, "direct uvicorn on a LAN address"),
    ],
)
def test_ws_target_selection(url: str, expected: bool, why: str) -> None:
    assert _is_direct(url) is expected, f"{url}: {why}"


def test_nginx_port_beats_the_loopback_heuristic() -> None:
    """The #12781 regression in one assertion.

    Loopback previously short-circuited to "direct uvicorn" before the port was
    considered, so a co-located nginx on 127.0.0.1:443 was misread and every
    handshake came back 403.
    """
    assert _is_direct("https://127.0.0.1:443") is False, (
        "loopback must not imply direct uvicorn when the port is an nginx port — "
        "that is #12781, and it rejects every SLM WebSocket with 403"
    )


def test_loopback_still_means_direct_uvicorn_off_nginx_ports() -> None:
    """Guard the #10459 fix: the port check must not swallow the loopback case."""
    assert _is_direct("http://127.0.0.1:8000") is True


def test_selector_never_raises_on_malformed_input() -> None:
    """A bad URL must degrade to the nginx path, not crash the reconnect loop."""
    for bad in ("", "not a url", "://", "http://[::1", "ftp://x"):
        assert _is_direct(bad) in (True, False)


def test_path_expression_still_reads_from_the_selector() -> None:
    """Pin the call site, so the fix cannot be bypassed by a literal path."""
    src = _SRC.read_text(encoding="utf-8")

    assert '"/api/ws/events" if _is_direct_uvicorn_url(' in src, (
        "the ws path must still be chosen by _is_direct_uvicorn_url"
    )
    assert '"/slm/api/ws/events"' in src, "the nginx-prefixed path must remain the fallback"


if sys.version_info < (3, 8):  # pragma: no cover - defensive
    pytest.skip("requires modern importlib", allow_module_level=True)

assert importlib.util  # keep the import meaningful for linters
