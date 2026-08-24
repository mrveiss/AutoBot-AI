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
# #13312 — the unit gate never touches the network, the system, or the install
# ---------------------------------------------------------------------------
# Two escape hatches in api/code_sync.py turn a forgotten mock into real I/O:
#
#   * _wait_component_healthy probes a component's HTTP health URL every
#     _HEALTH_POLL_INTERVAL seconds until _HEALTH_POLL_TIMEOUT (180s) or
#     _FAST_HEALTH_POLL_TIMEOUT (60s) expires, swallowing every per-attempt
#     error.  Unmocked, that is ~90 live requests and the whole window as dead
#     wait on a runner where nothing listens.
#   * _snapshot_component / _rollback_component / _is_systemd_unit_failed and
#     friends shell out through asyncio.create_subprocess_exec — a deleting
#     rsync against the deployed tree, systemctl against real units.  rsync
#     creates its destination before failing, so an unmocked snapshot litters
#     the live snapshot store with empty directories on any host where the test
#     user can write there.
#
# Both have now been patched test-by-test several times over (#11462, #11467,
# #13312) and both keep coming back, so the guards live here for the whole
# tests/api package rather than in individual files.  Neither masks anything:
# httpx.AsyncClient is used by exactly one place in api/code_sync.py (the health
# poll), and every test that legitimately drives either path installs its own
# stand-in inside the test body, whose inner patch wins over these guards.
#
# The guards raise through pytest.fail (an OutcomeException, i.e. a
# BaseException) precisely because the code under test wraps these calls in
# broad ``except Exception`` handlers — a plain error would be swallowed and the
# poll would keep spinning for the full window, which is the failure mode being
# prevented.
#
# A runtest hook rather than an autouse fixture.  #13320 had no choice: an
# autouse fixture requesting monkeypatch registers a finalizer for every test in
# the package, and that reordered the async session fixture in
# test_slm_endpoints_12515.py enough to break its session close (9 teardown
# errors).  That tripwire is fixed — the fixture now closes its session
# explicitly and no longer patches the shared asyncio module, and the module
# carries an autouse ``finalizer_ordering_guard`` that keeps it fixed (#13329) —
# so the constraint no longer applies.  The hookwrapper stays because it is
# still the better scope: it adds no fixture and no finalizer, and wraps only
# the call phase, which is where the I/O being guarded happens.
_LIVE_POLL_MESSAGE = (
    "unit test attempted a live component health poll via httpx.AsyncClient. "
    "api.code_sync._wait_component_healthy polls until its timeout window "
    "expires, so an unmocked poll costs up to 180s of dead wait and performs "
    "real network I/O (#13312). Patch 'api.code_sync._wait_component_healthy' "
    "when the test is about post-sync orchestration, or install an "
    "httpx.AsyncClient stand-in when the poll itself is under test."
)

_LIVE_SUBPROCESS_MESSAGE = (
    "unit test spawned the real subprocess {argv} via "
    "asyncio.create_subprocess_exec (#13312). api/code_sync.py shells out to "
    "rsync, systemctl and ansible against the live install; rsync creates its "
    "destination before failing, so this leaves debris behind wherever the test "
    "user can write. Patch the helper that owns the call — "
    "'api.code_sync._snapshot_component', '..._rollback_component', "
    "'..._is_systemd_unit_failed' — or patch asyncio.create_subprocess_exec "
    "with a fake when the invocation itself is under test."
)


class _LiveHealthPollBlocked:
    """httpx.AsyncClient stand-in that refuses to perform a real probe."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pytest.fail(_LIVE_POLL_MESSAGE, pytrace=False)


def _blocked_subprocess_exec(*cmd: object, **kwargs: object):
    """asyncio.create_subprocess_exec stand-in that refuses to spawn."""
    argv = " ".join(str(c) for c in cmd[:3]) or "<no argv>"
    pytest.fail(_LIVE_SUBPROCESS_MESSAGE.format(argv=argv), pytrace=False)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """Fail fast instead of dead-waiting or touching the host."""
    try:
        import asyncio

        import httpx
    except ImportError:
        # _wait_component_healthy short-circuits to "healthy" without httpx, so
        # there is no live poll to block.
        yield
        return
    saved_client = httpx.AsyncClient
    saved_exec = asyncio.create_subprocess_exec
    httpx.AsyncClient = _LiveHealthPollBlocked
    asyncio.create_subprocess_exec = _blocked_subprocess_exec
    try:
        yield
    finally:
        httpx.AsyncClient = saved_client
        asyncio.create_subprocess_exec = saved_exec
