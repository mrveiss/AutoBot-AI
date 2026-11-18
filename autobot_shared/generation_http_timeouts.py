# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Per-call HTTP timeouts for the image/video generation plugins (#12979).

The pooled session default is ``ClientTimeout(total=30, connect=5,
sock_read=10)`` (``http_client_manager.py``). The raw ``aiohttp.ClientSession()``
these plugins used before #12979 ran on aiohttp's default (total 300s, no
``sock_read`` cap), so a synchronous generation call (e.g. Stability SDXL
returns the image in the POST response) that takes more than 10s to send its
first bytes would fail on the pooled default. Every plugin call therefore
passes one of these explicitly.

Sizing:

* ``generation`` -- submit/synchronous-generate calls. Total and ``sock_read``
  match the old aiohttp default (300s): the provider holds the connection
  silent while it renders, so ``sock_read`` must be as long as ``total``.
* ``poll`` -- status polls and async-job submits that only enqueue work. These
  return in well under a second normally; 30s is generous without letting a
  wedged poll stall the 2s polling loop for minutes.
* connect -- 10s for both, double the pooled default so a slow TLS handshake
  to a remote provider is not mistaken for an outage.
"""

from __future__ import annotations

import aiohttp

from autobot_shared.env_utils import env_float_clamped

# ``positive_finite``: aiohttp reads 0 and NaN as "no timer", a negative as
# "already expired" and inf can overflow the timer, so a bad override falls back
# to the default (with a warning) instead of silently disabling the timeout.
GENERATION_TIMEOUT_S: float = env_float_clamped("AUTOBOT_GENERATION_REQUEST_TIMEOUT_S", 300.0, positive_finite=True)
POLL_TIMEOUT_S: float = env_float_clamped("AUTOBOT_GENERATION_POLL_TIMEOUT_S", 30.0, positive_finite=True)
CONNECT_TIMEOUT_S: float = env_float_clamped("AUTOBOT_GENERATION_CONNECT_TIMEOUT_S", 10.0, positive_finite=True)


def generation_timeout() -> aiohttp.ClientTimeout:
    """Timeout for a call that blocks while the provider renders."""
    return aiohttp.ClientTimeout(total=GENERATION_TIMEOUT_S, connect=CONNECT_TIMEOUT_S, sock_read=GENERATION_TIMEOUT_S)


def poll_timeout() -> aiohttp.ClientTimeout:
    """Timeout for a short status poll or an enqueue-only submit."""
    return aiohttp.ClientTimeout(total=POLL_TIMEOUT_S, connect=CONNECT_TIMEOUT_S, sock_read=POLL_TIMEOUT_S)
