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


def novnc_client_host() -> str:
    """The host a viewer dials for a session's websockify listener (#22146).

    The listener binds ``config.misc.novnc_bind_host`` (loopback unless set, never the API bind):
    loopback is only reachable from this host, so the URL says localhost; bind-all is dialed at the
    externally reachable host; a specific address accepts connections only on that address, so the
    URL uses it.
    """
    bind = config.misc.novnc_bind_host
    try:
        address = ipaddress.ip_address(bind)
    except ValueError:
        return NetworkConstants.LOCALHOST_NAME if bind == NetworkConstants.LOCALHOST_NAME else bind
    if address.is_loopback:
        return NetworkConstants.LOCALHOST_NAME
    if address.is_unspecified:
        return config.misc.vnc_host or config.vm.main
    return bind
