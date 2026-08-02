# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Conftest for api-level unit tests.

Dev-host workaround: the system `multipart` package (0.0.27 installed by mcp)
conflicts with starlette's import of `python_multipart.multipart`.  Pytest
loads conftest modules before collecting test files, so this is the correct
place to install the stub — by the time any test module does
`from api.code_sync import ...` the starlette cache is already clean.

This does NOT affect CI (where the correct packages are installed in the venv).

It also carries the live-health-poll guard for the ``test_code_sync_*`` modules
(#13312) — see ``_block_live_code_sync_health_polls``.
"""

import sys
import types

import pytest

if "multipart" not in sys.modules or not hasattr(sys.modules.get("multipart"), "parse_options_header"):
    # Stub multipart.multipart.parse_options_header so starlette.formparsers loads
    _mp_inner = types.ModuleType("multipart.multipart")
    _mp_inner.parse_options_header = lambda *a, **kw: (b"", {})  # type: ignore[attr-defined]
    _mp = types.ModuleType("multipart")
    _mp.multipart = _mp_inner  # type: ignore[attr-defined]
    sys.modules.setdefault("multipart", _mp)
    sys.modules.setdefault("multipart.multipart", _mp_inner)

if "python_multipart" not in sys.modules:
    _pymp_inner = types.ModuleType("python_multipart.multipart")
    _pymp_inner.parse_options_header = lambda *a, **kw: (b"", {})  # type: ignore[attr-defined]
    _pymp = types.ModuleType("python_multipart")
    _pymp.multipart = _pymp_inner  # type: ignore[attr-defined]
    sys.modules.setdefault("python_multipart", _pymp)
    sys.modules.setdefault("python_multipart.multipart", _pymp_inner)


# ---------------------------------------------------------------------------
# #13312 — no live health polls from the unit gate
# ---------------------------------------------------------------------------
# api.code_sync._wait_component_healthy probes a component's HTTP health URL
# every _HEALTH_POLL_INTERVAL seconds until _HEALTH_POLL_TIMEOUT (180s) or
# _FAST_HEALTH_POLL_TIMEOUT (60s).  A _run_post_sync_steps test that does not
# mock the poll therefore performs real outbound requests and burns the whole
# window as dead wait — on a runner where nothing listens on the health port
# that is ~180s per test.  This has now been fixed three times test-by-test
# (#11462, #11467, #13312), so the guard lives here instead of in each file.
#
# httpx.AsyncClient is used by exactly one place in api/code_sync.py — the
# health poll — so replacing it for the code-sync modules cannot mask anything
# else.  Tests that legitimately exercise the poll install their own
# httpx.AsyncClient stand-in inside the test body; that inner patch wins over
# this fixture, so they are unaffected.
#
# The guard raises through pytest.fail (an OutcomeException, i.e. a
# BaseException) precisely because _wait_component_healthy wraps the probe in a
# broad ``except Exception`` — a plain error would be swallowed and the loop
# would keep spinning for the full window, which is the failure mode being
# prevented.
_CODE_SYNC_MODULE_PREFIX = "test_code_sync_"

_LIVE_POLL_MESSAGE = (
    "unit test attempted a live component health poll via httpx.AsyncClient. "
    "api.code_sync._wait_component_healthy polls until its timeout window "
    "expires, so an unmocked poll costs up to 180s of dead wait and performs "
    "real network I/O (#13312). Patch 'api.code_sync._wait_component_healthy' "
    "when the test is about post-sync orchestration, or install an "
    "httpx.AsyncClient stand-in when the poll itself is under test."
)


class _LiveHealthPollBlocked:
    """httpx.AsyncClient stand-in that refuses to perform a real probe."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pytest.fail(_LIVE_POLL_MESSAGE, pytrace=False)


@pytest.fixture(autouse=True)
def _block_live_code_sync_health_polls(request, monkeypatch):
    """Fail fast instead of dead-waiting when a code-sync test polls for real."""
    module_name = getattr(request.module, "__name__", "")
    if not module_name.rpartition(".")[2].startswith(_CODE_SYNC_MODULE_PREFIX):
        return
    try:
        import httpx
    except ImportError:
        # _wait_component_healthy short-circuits to "healthy" without httpx, so
        # there is no live poll to block.
        return
    monkeypatch.setattr(httpx, "AsyncClient", _LiveHealthPollBlocked)
