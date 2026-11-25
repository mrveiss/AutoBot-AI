# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend host settings: empty means the default, an unspecified address is a failure (#18810).

``AUTOBOT_BACKEND_HOST`` is the address clients dial; the address the server listens on is
``AUTOBOT_BACKEND_BIND_HOST``. Nothing here rewrites a value: an empty setting takes the default,
and a bind-all value in the dialed setting is left as written, so the egress guard refuses it and
``startup_validation.py`` fails the start naming the variable (a silent substitution would turn a
misconfigured multi-host fleet into a wrong-host success).
"""

import ipaddress
from typing import Annotated

from pydantic import BeforeValidator

#: The single-host default for both the dialed and the listen host.
DEFAULT_BACKEND_HOST = "127.0.0.1"


def host_or_default(host: str) -> str:
    """*host* unchanged, or the default when it is empty or blank (an unset setting)."""
    return host if str(host).strip() else DEFAULT_BACKEND_HOST


def is_unspecified_host(host: str) -> bool:
    """True for ``0.0.0.0`` and ``::`` (bind-all sentinels, never dialable)."""
    try:
        return ipaddress.ip_address(str(host).strip().strip("[]")).is_unspecified
    except ValueError:
        return False  # a DNS name, or empty (the default applies)


#: A host field whose empty value means the default (the type the SSOT host fields use).
HostOrDefault = Annotated[str, BeforeValidator(host_or_default)]
