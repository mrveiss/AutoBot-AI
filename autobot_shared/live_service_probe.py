# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Precondition probes for tests that drive a *live* AutoBot service (#14930).

Several suites under the ``integration`` / ``performance`` markers issue real
HTTP to a running backend, TTS worker or embedding provider. On a GitHub-hosted
runner none of those are up, so the tests did not report "not exercised here" —
they reported ``ConnectionRefusedError`` as a test failure, or (when the URL
fixture did not exist at all) as a setup error. 38 such results made the
marker-excluded suite permanently red and therefore unread.

The distinction this module draws is deliberately narrow:

* **Nothing is listening on the endpoint** — the service under test is absent,
  so the test was never exercised. That is a ``skip`` with a stated reason.
* **Anything else** — a connected service answering wrongly, a bad URL, a
  programming error — is a real result and propagates untouched.

That boundary is the whole point. A guard that swallowed *any* exception would
be a test that cannot fail, which is the defect class this repo keeps paying
for; ``endpoint_is_listening`` therefore catches ``OSError`` (every network
condition: refused, unreachable, timed out, DNS failure) and nothing wider.
A ``TypeError`` from a malformed argument still raises.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlsplit

__all__ = [
    "DEFAULT_PROBE_TIMEOUT_SECONDS",
    "endpoint_is_listening",
    "reset_probe_cache",
    "require_live_endpoint",
    "split_endpoint",
]

# Env-var-backed module constant rather than a literal at the call site: a
# fleet run may need longer than a loopback run, and no caller should hardcode
# its own budget. Kept short — this runs before every guarded test, and a
# refused loopback connect returns in well under a millisecond.
DEFAULT_PROBE_TIMEOUT_SECONDS = float(os.getenv("AUTOBOT_LIVE_PROBE_TIMEOUT_SECONDS", "1.0"))

_DEFAULT_PORTS = {"http": 80, "https": 443, "redis": 6379, "rediss": 6379, "ws": 80, "wss": 443}

# Probing once per endpoint per process keeps an autouse guard from opening a
# socket for every test in a 19-test module.
_PROBE_CACHE: dict[tuple[str, int], bool] = {}


def reset_probe_cache() -> None:
    """Forget every cached probe result.

    Exposed for tests of this module itself: without it a cached ``False`` from
    one case would decide the next one.
    """
    _PROBE_CACHE.clear()


def split_endpoint(target: str, port: int | None = None) -> tuple[str, int]:
    """Return ``(host, port)`` for a URL or a bare host.

    Raises ``ValueError`` when no port can be determined, rather than guessing —
    a probe against the wrong port would report a live service as absent and
    silently skip a suite that should have run.
    """
    if not isinstance(target, str) or not target.strip():
        raise ValueError(f"endpoint target must be a non-empty string, got {target!r}")

    target = target.strip()
    parts = urlsplit(target if "//" in target else f"//{target}")
    host = parts.hostname
    if not host:
        raise ValueError(f"could not determine a host from endpoint {target!r}")

    resolved_port = port or parts.port or _DEFAULT_PORTS.get((parts.scheme or "").lower())
    if not resolved_port:
        raise ValueError(f"could not determine a port from endpoint {target!r}; pass port= explicitly")

    return host, int(resolved_port)


def endpoint_is_listening(
    target: str,
    port: int | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    use_cache: bool = True,
) -> bool:
    """True when a TCP connection to *target* is accepted.

    This asks exactly one question — *is a process accepting connections here* —
    and answers it without sending a byte of protocol. It says nothing about
    whether that process is healthy, which is the tests' job to assert.

    Only ``OSError`` is treated as "not listening". ``ValueError`` from
    :func:`split_endpoint` propagates: a target this module cannot parse is a
    bug in the caller, and reporting it as "absent" would skip a live suite.
    """
    host, resolved_port = split_endpoint(target, port)
    key = (host, resolved_port)

    if use_cache and key in _PROBE_CACHE:
        return _PROBE_CACHE[key]

    try:
        with socket.create_connection((host, resolved_port), timeout=timeout):
            listening = True
    except OSError:
        listening = False

    if use_cache:
        _PROBE_CACHE[key] = listening
    return listening


def require_live_endpoint(target: str, what: str, port: int | None = None) -> None:
    """Skip the calling test iff nothing is listening on *target*.

    *what* names the missing service in the skip reason, so a skipped run says
    which part of the stack was absent instead of reading as an unexplained
    non-result.
    """
    host, resolved_port = split_endpoint(target, port)
    if endpoint_is_listening(target, port):
        return

    import pytest

    pytest.skip(f"{what} is not listening on {host}:{resolved_port} — this test drives a live service")
