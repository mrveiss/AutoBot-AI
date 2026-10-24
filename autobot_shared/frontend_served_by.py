# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which server answers on the frontend host decides the frontend's served URL (#19326).

``AUTOBOT_FRONTEND_PORT`` is the Vite dev server (``port.frontend``). The URL a user opens on a
nginx host is built from ``tls.frontend_tls_port`` (HTTPS) or ``port.frontend_http`` (HTTP), and
``AUTOBOT_FRONTEND_SERVED_BY`` says which family applies. Dependency-free so the SSOT, the env
registry and the guard share one definition. An unset or unknown value is never defaulted: a
default would pick a port the host may not listen on, and the URL feeds redirect validation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

VITE = "vite"
NGINX = "nginx"
SERVED_BY_VALUES = (VITE, NGINX)
SERVED_BY_ENV = "AUTOBOT_FRONTEND_SERVED_BY"


class FrontendServedByError(ValueError):
    """``AUTOBOT_FRONTEND_SERVED_BY`` is unset or not one of ``vite`` / ``nginx``."""


def parse_served_by(value: object) -> str:
    """``''`` for unset, the lower-cased value when valid, :class:`FrontendServedByError` otherwise."""
    text = "" if value is None else str(value).strip().lower()
    if text and text not in SERVED_BY_VALUES:
        raise FrontendServedByError(f"{SERVED_BY_ENV}={value!r} -- expected one of {', '.join(SERVED_BY_VALUES)}")
    return text


def frontend_url(config: Any) -> str:
    """The URL *config* (an ``AutoBotConfig``) serves the frontend at; unset or unknown raises, never guesses."""
    served_by = parse_served_by(config.frontend_served_by)
    if served_by == VITE:
        return f"http://{config.vm.frontend}:{config.port.frontend}"
    if served_by != NGINX:
        raise FrontendServedByError(f"{SERVED_BY_ENV} is unset -- set it to one of {', '.join(SERVED_BY_VALUES)}")
    if config.tls.frontend_tls_enabled:
        return f"https://{config.vm.frontend}:{config.tls.frontend_tls_port}"
    return f"http://{config.vm.frontend}:{config.port.frontend_http}"


def try_frontend_url(config: Any) -> str | None:
    """``config.frontend_url``, or ``None`` after a warning when the profile is unset or unknown.

    For callers where the frontend is one optional target among several (health probes, the egress
    allowlist): the frontend is left out -- never defaulted to a port -- and the rest still work.
    """
    try:
        return config.frontend_url
    except FrontendServedByError as exc:
        logger.warning("frontend URL unavailable, the frontend is left out: %s", exc)
        return None
