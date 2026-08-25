# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether code execution is actually containerised, reported (#14872).

The Docker SDK is guard-imported by four modules and, until #14872, declared in
no requirements file. Each of them degrades on its own terms, and none of them
was observable:

* ``secure_sandbox_executor.py:126`` raises when the SDK is absent — and
  ``_create_secure_sandbox`` (:964-967) catches that, logs
  ``"Command execution will proceed without sandboxing - SECURITY RISK"``, and
  returns ``None``. The result is cached by ``lazy_optional_singleton``, so that
  line is emitted **once per process**, at first touch. An operator who was not
  reading logs at that moment has no way to discover the state afterwards.
* ``services/execution/docker_backend.py:92`` raises from its constructor, and
  ``execution_manager.py:111-114`` catches it, logs a warning and moves to the
  next backend — which is ``LocalBackend``, direct subprocess execution.
  ``ExecutionResult`` carries no field naming the backend that ran, so the
  caller cannot tell either.
* ``api/sandbox.py``'s ``/stats`` reported ``"network_isolation": True`` as a
  hardcoded literal, true or not.

"Is this sandbox containerised?" was therefore inferable only from a log line
nobody keeps. This probe answers it directly, on
``GET /api/system/health`` alongside every other component, and its three
booleans are measured rather than asserted:

``docker_sdk``       the SDK imports (the #14872 declaration is what makes this
                     reliably true rather than accidentally true)
``daemon_reachable`` the daemon answers a ping — an installed SDK with no
                     daemon is still an uncontainerised sandbox
``containerised``    both of the above, i.e. what an operator actually asked

Kept in its own module rather than added to ``secure_sandbox_executor.py`` or
``services/execution/docker_backend.py``: both sit at their file-size ceiling in
``scripts/python_file_size_known_large.py``, which only ever shrinks, so a
grandfathered file may not grow by even one line (#14236).

Deliberately does NOT import ``secure_sandbox_executor``. That module builds a
Docker client and pulls the whole execution stack; a health probe runs on every
poll of the aggregator and has no business doing either. ``find_spec`` answers
the SDK question without importing, and the daemon ping is the only I/O.
"""

from __future__ import annotations

import asyncio
import importlib.util
import time

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_PROBE_NAME = KnownProbes.SANDBOX.value

#: Bound on the daemon ping. The aggregator gives every probe 2s
#: (``HEALTH_PROBE_TIMEOUT_S``); a docker ping against an unreachable socket can
#: sit far longer than that, and blowing the aggregator's budget to answer this
#: question would make the health page worse, not better.
_PING_TIMEOUT_S = 1.0


def _docker_sdk_present() -> bool:
    """Is the Docker SDK importable, without importing it?

    ``find_spec`` rather than a ``try: import docker``: importing the SDK on
    every health poll is real work for a boolean, and it is the shape this
    module exists to stop trusting.
    """
    try:
        return importlib.util.find_spec("docker") is not None
    except (ImportError, ValueError):
        # ValueError: a parent package exists but has no __spec__ — a broken
        # install, which for this question means the same as absent.
        return False


def _ping_daemon() -> bool:
    """Does the Docker daemon answer? Blocking; call it off the event loop."""
    import docker  # noqa: PLC0415 — only reached when find_spec said it exists

    client = docker.from_env()
    try:
        return bool(client.ping())
    finally:
        client.close()


async def _daemon_reachable() -> tuple[bool, str | None]:
    """(reachable, reason it is not). A ping that cannot run is not a ping that passed."""
    try:
        reachable = await asyncio.wait_for(asyncio.to_thread(_ping_daemon), timeout=_PING_TIMEOUT_S)
        return reachable, None if reachable else "daemon returned a falsy ping"
    except asyncio.TimeoutError:
        return False, f"daemon did not answer within {_PING_TIMEOUT_S}s"
    except Exception as exc:
        # Broad on purpose: the SDK raises a family of connection, permission
        # and API errors here, and every one of them means the same thing for
        # this probe. The reason is reported rather than swallowed.
        return False, f"{type(exc).__name__}: {exc}"


def _status(sdk: bool, reachable: bool) -> str:
    """Degraded, not down: uncontainerised execution still runs, less safely.

    ``down`` would say code execution is unavailable, which is not what is
    happening — it is available and unsandboxed, and conflating the two is how
    this went unnoticed.
    """
    return "ok" if sdk and reachable else "degraded"


@register_health_probe(_PROBE_NAME)
async def probe_sandbox(request: Request | None = None) -> ComponentHealth:
    """Report whether sandboxed code execution is actually containerised (#14872)."""
    start = time.monotonic()
    sdk = _docker_sdk_present()

    if not sdk:
        detail = "docker SDK is not installed - code execution runs UNSANDBOXED, as a local subprocess"
        logger.warning("sandbox health: %s", detail)
        return ComponentHealth(
            name=_PROBE_NAME,
            status="degraded",
            detail=detail,
            latency_ms=round((time.monotonic() - start) * 1000, 1),
            data={"docker_sdk": False, "daemon_reachable": False, "containerised": False},
        )

    reachable, reason = await _daemon_reachable()
    detail = None
    if not reachable:
        detail = (
            f"docker SDK present but the daemon is unreachable ({reason}) - "
            "code execution runs UNSANDBOXED"
        )
    if detail:
        logger.warning("sandbox health: %s", detail)

    return ComponentHealth(
        name=_PROBE_NAME,
        status=_status(sdk, reachable),
        detail=detail,
        latency_ms=round((time.monotonic() - start) * 1000, 1),
        data={"docker_sdk": True, "daemon_reachable": reachable, "containerised": reachable},
    )
