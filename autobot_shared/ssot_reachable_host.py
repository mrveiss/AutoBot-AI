# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A client-facing host is never an unspecified bind address (#18810).

``AUTOBOT_BACKEND_HOST`` is the address clients dial; the address the server listens on is
``AUTOBOT_BACKEND_BIND_HOST``. An install whose env still carries the bind-all value as the
client host would build client URLs on the unspecified address, which the egress guard rightly refuses, so
the value is replaced by loopback and the misconfiguration is logged loudly.
"""

import ipaddress
import logging

logger = logging.getLogger(__name__)

#: What an unspecified client host becomes: the single-host reachable address.
REACHABLE_FALLBACK_HOST = "127.0.0.1"


def is_unspecified_host(host: str) -> bool:
    """True for ``0.0.0.0``, ``::`` and an empty host (bind-all sentinels, never dialable)."""
    candidate = str(host).strip().strip("[]")
    if not candidate:
        return True
    try:
        return ipaddress.ip_address(candidate).is_unspecified
    except ValueError:
        return False  # a DNS name


def reachable_host(host: str) -> str:
    """*host* unchanged, or loopback (logged at ERROR) when it is an unspecified bind address."""
    if not is_unspecified_host(host):
        return host
    logger.error(
        "AUTOBOT_BACKEND_HOST=%r is a bind address, not a host clients can dial; using %s. "
        "Set AUTOBOT_BACKEND_BIND_HOST for the listen address (#18810).",
        host,
        REACHABLE_FALLBACK_HOST,
    )
    return REACHABLE_FALLBACK_HOST
