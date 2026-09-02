# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one direct-uvicorn-vs-nginx decision for every SLM URL (#13584, #14039).

``SLM_URL`` may point at uvicorn directly (Docker Compose, ``:8000``) or at the
nginx reverse proxy that fronts it. nginx serves the SLM under a ``/slm``
prefix; uvicorn has no ``/slm`` route at all. So the same logical endpoint is
``/api/health`` on one deployment and ``/slm/api/health`` on the other, and a
call site that hardcodes either form 404s on the other.

``services/slm_client.py`` got this right for the WebSocket path first and then
for its own six REST call sites (#13584). Every other caller kept hardcoding
``/api`` (#14039) — seven sites across five files — because the decision lived
as a private function inside a module they cannot import: ``dag_executor`` and
``redis_service_manager`` hold bare URL strings, and ``scripts/`` runs outside
the backend's ``sys.path`` entirely.

This module is that decision, extracted, with nothing but ``urllib`` behind it
so any of them can import it. ``services/slm_client.py`` re-exports both names,
so ``from services.slm_client import rest_url`` keeps working for callers
already inside the backend — one implementation, two import paths, never two
copies.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Hosts that mean "the SLM is on this box"; see :func:`is_direct_uvicorn_url`.
_LOOPBACK_HOSTS: frozenset = frozenset({"127.0.0.1", "localhost", "::1", "ip6-localhost"})

#: Ports nginx serves on. Anything else on plain HTTP is uvicorn itself.
_NGINX_HTTP_PORTS: frozenset = frozenset({80, 443})


def is_direct_uvicorn_url(url: str) -> bool:
    """Return True when *url* points straight at uvicorn (no nginx in between).

    nginx always serves on HTTPS (443) or standard HTTP (80). Any plain-HTTP
    URL with a non-standard port (e.g. ``:8000``), or a loopback host off those
    ports, reaches uvicorn directly — so neither the WebSocket route nor a REST
    path may carry the ``/slm`` prefix.

    Two regressions are pinned into the ordering below and must stay that way:

    * #10459 — ``AUTOBOT_SLM_HOST=autobot-slm`` (a Docker DNS name, not a
      loopback address) on ``:8000`` was read as "behind nginx", so
      ``/slm/api/ws/events`` went to uvicorn, which has no such route: starlette
      closed before accept and uvicorn turned that into HTTP 403.
    * #12781 — the nginx PORT check must come FIRST, before the loopback
      branch. On a co-located install nginx terminates TLS on ``127.0.0.1:443``;
      treating loopback as "direct uvicorn" chose the un-prefixed path, nginx
      routed it to the *user* backend, and every reconnect got 403.

    Args:
        url: The SLM base URL (e.g. ``http://autobot-slm:8000``).

    Returns:
        True for direct uvicorn (no prefix); False for nginx (``/slm`` prefix).
        Malformed input degrades to False — the nginx path — rather than raising
        into a reconnect loop.
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        scheme = parsed.scheme.lower()
        port = parsed.port  # None means the scheme's default (80 http / 443 https)

        # #12781: an nginx port wins over any host heuristic, loopback included.
        if port in _NGINX_HTTP_PORTS or (port is None and scheme in ("http", "https")):
            return False

        # Loopback on a non-nginx port means direct uvicorn.
        if host in _LOOPBACK_HOSTS:
            return True

        # #10459: plain HTTP on a non-standard port — the Docker Compose case.
        if scheme == "http" and port is not None and port not in _NGINX_HTTP_PORTS:
            return True

        return False
    except Exception:
        return False


def rest_url(slm_url: str, path: str) -> str:
    """Join *slm_url* and *path*, adding the ``/slm`` prefix when nginx fronts it.

    The counterpart of ``SLMClient._rest_url`` for the call sites that hold a
    bare URL string rather than a client instance (#14039).

    Args:
        slm_url: The SLM base URL, with or without a trailing slash.
        path: The API path as uvicorn serves it, e.g. ``/api/health``. A leading
            slash is added when missing so a caller cannot glue two segments
            together by accident.

    Returns:
        The full URL — ``{slm_url}/api/...`` direct, ``{slm_url}/slm/api/...``
        behind nginx.
    """
    base = slm_url.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    prefix = "" if is_direct_uvicorn_url(base) else "/slm"
    return f"{base}{prefix}{path}"
