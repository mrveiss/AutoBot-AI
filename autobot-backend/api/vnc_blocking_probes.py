# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Blocking desktop probes for the VNC endpoints (#7444).

Every function here blocks, and each one used to run on the event loop inside an
``async def`` handler in ``api/vnc_manager.py``. They live in their own module so
that "this blocks, schedule it" is a property of the import rather than a comment
somebody has to notice: an async caller reaches them through
``asyncio.to_thread``, and nothing in here imports ``asyncio``.

The combined ceiling was roughly twelve seconds of stalled event loop per request
to the quality-metrics endpoint -- two ``pgrep`` calls at ``timeout=5`` and a
socket connect at ``settimeout(2)``.
"""

import socket
import subprocess  # nosec B404
from datetime import datetime, timezone
from typing import Dict

from autobot_shared.logging_manager import get_logger
from constants.network_constants import NetworkConstants

logger = get_logger(__name__)


def is_vnc_running() -> bool:
    """Check if VNC server is running on the canonical desktop display. Blocking."""
    try:
        # Check for Xtigervnc process on the canonical display (Issue #11579)
        result = subprocess.run(  # nosec B603 B607  # fixed argv, no user input
            ["pgrep", "-f", f"Xtigervnc {NetworkConstants.DESKTOP_DISPLAY}"],
            capture_output=True,
            timeout=5,
        )
        # pgrep returns 0 if process found, 1 if not found
        return result.returncode == 0
    except Exception as e:
        logger.error("Error checking VNC status: %s", e)
        return False


def run_clipboard_write(payload: bytes) -> subprocess.CompletedProcess:
    """Write *payload* to the desktop clipboard. Blocking -- call via ``asyncio.to_thread``."""
    return subprocess.run(  # nosec B603 B607  # fixed argv, no user input
        ["xclip", "-selection", "clipboard"],
        input=payload,
        capture_output=True,
        env={"DISPLAY": NetworkConstants.DESKTOP_DISPLAY},
        timeout=5,
    )


def probe_connection_quality() -> Dict[str, object]:
    """Every blocking probe for the quality endpoint, in one place.

    All three of these block, and they were on the event loop: ``is_vnc_running()``
    shells out to ``pgrep`` with ``timeout=5``, the socket connect allows
    ``settimeout(2)``, and the websockify ``pgrep`` allows another 5 — so a single
    request to this endpoint could stall every other request for up to twelve
    seconds.

    Gathered into one sync function rather than wrapped individually: the probes are
    sequential anyway, so three ``to_thread`` hops would buy nothing over one.

    NOTE for whoever widens `tools/lint/check_no_blocking_io_in_async.py`: only the
    websockify call was visible to that guard's detector after this change's own
    widening. ``is_vnc_running`` is a **sync** function called from async, and the
    guard resets its async depth for sync bodies -- correctly, since a sync helper
    may have sync callers. A blocking sync helper reached *only* from async is
    therefore a blind spot in the detector's design, not a gap in its call list, and
    widening the list does not reach it.
    """
    metrics: Dict[str, object] = {"vnc_running": is_vnc_running()}

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        start_time = datetime.now(tz=timezone.utc)
        result = sock.connect_ex(("localhost", 5901))
        latency_ms = (datetime.now(tz=timezone.utc) - start_time).total_seconds() * 1000
        sock.close()

        metrics["vnc_port_reachable"] = result == 0
        metrics["latency_ms"] = round(latency_ms, 2)
    except Exception as e:
        logger.warning("Failed to check VNC connectivity: %s", e)
        metrics["vnc_port_reachable"] = False

    try:
        completed = subprocess.run(  # nosec B603 B607  # fixed argv, no user input
            ["pgrep", "-a", "websockify"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        metrics["websockify_running"] = completed.returncode == 0
        if completed.returncode == 0:
            metrics["websockify_processes"] = len(completed.stdout.strip().split("\n"))
    except Exception as e:
        logger.warning("Failed to check websockify: %s", e)

    return metrics
