# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Backend↔worker TTS route contract (Issue #12886).

The backend's ``services/tts_client.py`` posted to ``/tts/clone-voice`` for as
long as the route existed, while the worker template never served it — every
voice-clone request 404'd, and nothing failed until a user tried it. Nothing
compared the two sides.

These tests are that comparison: every route the client calls must be served by
the worker template. They are static (source parsing only, no running worker),
so a backend that starts calling a route the worker does not serve fails in CI
rather than at first use.
"""

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_CLIENT = _REPO_ROOT / "autobot-backend" / "services" / "tts_client.py"
_TEMPLATE = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "tts-worker" / "templates" / "tts-worker.py.j2"

# ``async with session.post(f"{self.base_url}/tts/synthesize", data=data)``
_CLIENT_CALL = re.compile(r"session\.(get|post|delete|put|patch)\(\s*f?\"\{self\.base_url\}(/[^\"]*)\"")
# ``@app.post("/tts/synthesize")``
_WORKER_ROUTE = re.compile(r"@app\.(get|post|delete|put|patch)\(\"([^\"]+)\"")


def _client_calls() -> set[tuple[str, str]]:
    """(method, path) pairs the backend's TTS client issues against the worker."""
    return {(m.lower(), p) for m, p in _CLIENT_CALL.findall(_CLIENT.read_text(encoding="utf-8"))}


def _worker_routes() -> set[tuple[str, str]]:
    """(method, path) pairs the worker template serves."""
    return {(m.lower(), p) for m, p in _WORKER_ROUTE.findall(_TEMPLATE.read_text(encoding="utf-8"))}


def test_sources_are_present():
    """Guard against the regexes silently matching nothing after a file move."""
    assert _CLIENT.is_file(), f"TTS client not found at {_CLIENT}"
    assert _TEMPLATE.is_file(), f"worker template not found at {_TEMPLATE}"
    assert _client_calls(), "no client calls parsed — the extraction regex has rotted"
    assert _worker_routes(), "no worker routes parsed — the extraction regex has rotted"


def test_every_client_call_is_served_by_the_worker():
    """The defect in #12886: /tts/clone-voice was called but never served."""
    unserved = sorted(_client_calls() - _worker_routes())

    assert (
        not unserved
    ), "tts_client.py calls routes the worker template does not serve — these 404 at runtime: " + ", ".join(
        f"{method.upper()} {path}" for method, path in unserved
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/health"),
        ("post", "/tts/synthesize"),
        ("post", "/tts/synthesize/stream"),
        ("post", "/tts/clone-voice"),
        ("get", "/voices"),
        ("post", "/voices/create"),
        ("delete", "/voices/{voice_id}"),
    ],
)
def test_known_contract_routes_present_on_both_sides(method, path):
    """Pin the contract itself, so dropping a route on EITHER side is caught."""
    assert (method, path) in _worker_routes(), f"worker no longer serves {method.upper()} {path}"
    assert (method, path) in _client_calls(), f"client no longer calls {method.upper()} {path}"
