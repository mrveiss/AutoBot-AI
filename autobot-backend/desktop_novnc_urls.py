# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Viewer URL pieces for a desktop session's websockify listener (#22146)."""

import ipaddress

from autobot_shared.ssot_config import config
from constants.network_constants import NetworkConstants

#: websockify runs with ``--ssl-only`` (see ``_start_novnc``), so the URL scheme is https.
NOVNC_URL_SCHEME = "https"


def _url_host(host: str) -> str:
    """*host* as a URL authority host: an IPv6 literal is bracketed, anything else is unchanged."""
    try:
        return f"[{host}]" if ipaddress.ip_address(host).version == 6 else host
    except ValueError:
        return host


def novnc_client_host() -> str:
    """The host a viewer dials for a session's websockify listener (#22146), ready for a URL.

    The listener binds ``config.misc.novnc_bind_host`` (loopback unless set, never the API bind):
    loopback is only reachable from this host, so the URL says localhost; bind-all is dialed at the
    externally reachable host; a specific address accepts connections only on that address, so the
    URL uses it (an IPv6 literal bracketed).
    """
    bind = config.misc.novnc_bind_host.strip("[]")
    try:
        address = ipaddress.ip_address(bind)
    except ValueError:
        return NetworkConstants.LOCALHOST_NAME if bind == NetworkConstants.LOCALHOST_NAME else bind
    if address.is_loopback:
        return NetworkConstants.LOCALHOST_NAME
    if address.is_unspecified:
        return _url_host(config.misc.vnc_host or config.vm.main)
    return _url_host(bind)
