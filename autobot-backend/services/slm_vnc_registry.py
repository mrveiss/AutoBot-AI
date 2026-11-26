# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The desktop VM, read from the SLM's registered VNC endpoints (#22145, owner 2026-11-24).

The desktop VM is a fleet node that runs VNC. Its address, ports and its OWN password come from the
SLM registry (``GET /api/vnc/endpoints`` and the node's VNC credential); nothing is guessed here. The
password travels over the existing authenticated SLM path (``connect`` mints a one-time token,
``exchange-token`` redeems it) and is never cached or stored. ``None`` from
:func:`desktop_vnc_endpoint` means "no VNC desktop node is registered"; the caller then falls back to
the main machine and says so in the log. A registry that cannot be reached raises: that is an
outage, not an empty fleet.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from autobot_shared import node_proxy
from autobot_shared.egress_allowlist import invalidate_internal_origin_cache, register_internal_origin_provider
from autobot_shared.env_utils import env_int
from autobot_shared.http_egress_guard import assert_egress_policy
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import TTL_1_MINUTE
from autobot_shared.store_authority import system_of_record

logger = get_logger(__name__)

ENDPOINTS_PATH = "/api/vnc/endpoints"
NODE_CREDENTIALS_PATH = "/api/nodes/{node_id}/vnc-credentials"
CONNECT_PATH = "/api/vnc/credentials/{credential_id}/connect"
EXCHANGE_PATH = "/api/vnc/exchange-token"
DESKTOP_VNC_TYPE = "desktop"
VNC_ROLE = "vnc"
NODES_PATH = "/api/nodes"
_NODES_PER_PAGE = 100
_MAX_NODE_PAGES = 50

#: Seconds the resolved endpoint is reused. The password is never cached.
REGISTRY_TTL_SECONDS = env_int("AUTOBOT_VNC_REGISTRY_TTL_SECONDS", TTL_1_MINUTE)


class SlmRegistryUnavailable(Exception):
    """The SLM registry could not be read (the request failed)."""


class SlmLinkNotInitialised(SlmRegistryUnavailable):
    """No SLM control link exists in this process. Decided explicitly: with no SLM there is no registered
    desktop node, so the desktop VM is absent (not an outage, and not an empty fleet to fall back from)."""


@dataclass(frozen=True)
class DesktopVmEndpoint:
    node_id: str
    credential_id: str
    host: str
    web_port: int  # websockify / noVNC
    rfb_port: int | None  # raw VNC, when the credential records it


_cache: tuple[float, DesktopVmEndpoint | None] | None = None
# The node last chosen is kept while it stays eligible, so a viewer and its controls agree. It lives in
# Redis (system_of_record("vnc_desktop_pin")) so every uvicorn worker keeps the SAME node; this process
# copy is only the fallback while Redis is unreachable.
_pinned_node_id: str | None = None
PIN_REDIS_KEY = "autobot:vnc:desktop_pin"
SYSTEM_OF_RECORD = system_of_record("vnc_desktop_pin")
_ORIGIN_SCHEMES = ("http", "https", "ws", "wss")
INTERNAL_KEY_HEADER = "X-Internal-API-Key"
_cache_lock = asyncio.Lock()  # one in-flight registry read; concurrent callers share its result


async def _pin_client():
    from autobot_shared.redis_client import get_redis_client

    return await get_redis_client(async_client=True, database="main")


async def _load_pin() -> str | None:
    """The pinned node id shared by every worker; this process's copy when Redis cannot answer."""
    try:
        raw = await (await _pin_client()).get(PIN_REDIS_KEY)
    except Exception as exc:  # Redis down must not take the desktop down: fall back to the local pin
        logger.warning("VNC desktop pin unreadable in Redis (%s); using this worker's copy", type(exc).__name__)
        return _pinned_node_id
    return (raw.decode("utf-8") if isinstance(raw, bytes) else raw) or None


async def _store_pin(node_id: str | None) -> None:
    global _pinned_node_id
    _pinned_node_id = node_id
    try:
        client = await _pin_client()
        await (client.set(PIN_REDIS_KEY, node_id) if node_id else client.delete(PIN_REDIS_KEY))
    except Exception as exc:
        logger.warning("VNC desktop pin not stored in Redis (%s)", type(exc).__name__)


def reset_cache() -> None:
    global _cache, _pinned_node_id
    _cache = None
    _pinned_node_id = None
    invalidate_internal_origin_cache()


def _registry_headers() -> dict[str, str]:
    """The machine caller's credential: the SLM's registry routes accept the internal service key, which
    the general service JWT (no admin claim) must never be widened to replace."""
    key = node_proxy.internal_api_key()
    return {INTERNAL_KEY_HEADER: key} if key else {}


def _desktop_origins() -> list[str]:
    """Origins of the registered desktop node's noVNC/websockify port: what the proxy and probes call.

    Reads the resolved endpoint only (never fetches): the fetch itself passes the egress check, so a fetch
    from here would wait on its own lock.
    """
    if _cache is None or time.monotonic() - _cache[0] >= REGISTRY_TTL_SECONDS or _cache[1] is None:
        return []
    host = _cache[1].host
    host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return [f"{scheme}://{host}:{_cache[1].web_port}" for scheme in _ORIGIN_SCHEMES]


async def _registered_desktop_origins() -> list[str]:
    return _desktop_origins()


register_internal_origin_provider(_registered_desktop_origins)


async def _request(method: str, path: str, params: dict | None = None) -> dict:
    from services.slm_client import get_slm_client

    client = get_slm_client()
    if client is None:
        raise SlmLinkNotInitialised("SLM control link is not initialised")
    session = await client._get_session()
    url = client._rest_url(path)
    await assert_egress_policy(url)
    try:
        async with session.request(
            method, url, params=params, headers=_registry_headers(), allow_redirects=False
        ) as response:
            response.raise_for_status()
            return await response.json()
    except Exception as exc:  # aiohttp raises several types; all mean "registry unreadable"
        raise SlmRegistryUnavailable(f"SLM registry request failed: {type(exc).__name__}") from exc


def _pick_desktop(endpoints: list[dict], vnc_node_ids: frozenset[str], pinned: str | None = None) -> dict | None:
    """The first live desktop endpoint on a node that CURRENTLY has the `vnc` role, in a stable
    (hostname, node_id) order. A credential left on a node without the role is stale and never used."""
    # The registry lists only active credentials (`include_inactive` defaults to false), so no re-check here.
    live = [e for e in endpoints if e.get("vnc_type") == DESKTOP_VNC_TYPE]
    usable = [e for e in live if e.get("node_id") in vnc_node_ids]
    if len(usable) < len(live):
        stale = sorted(str(e.get("node_id")) for e in live if e.get("node_id") not in vnc_node_ids)
        logger.warning("Ignoring VNC desktop endpoint(s) on node(s) without the '%s' role: %s", VNC_ROLE, stale)
    if not usable:
        return None
    kept = [e for e in usable if e.get("node_id") == pinned]  # a second registration never moves the desktop
    picked = (kept or sorted(usable, key=lambda e: (str(e.get("hostname", "")), str(e.get("node_id", "")))))[0]
    if len(usable) > 1:
        logger.warning("%d VNC desktop nodes are registered; using node %s", len(usable), picked.get("node_id"))
    return picked


async def _vnc_role_node_ids() -> frozenset[str]:
    """Ids of the nodes whose assigned roles include `vnc`, read from the SLM registry (paged)."""
    ids: set[str] = set()
    collected = 0
    for page in range(1, _MAX_NODE_PAGES + 1):
        body = await _request("GET", NODES_PATH, params={"page": str(page), "per_page": str(_NODES_PER_PAGE)})
        batch = [n for n in body.get("nodes") or [] if isinstance(n, dict)]
        ids.update(n["node_id"] for n in batch if VNC_ROLE in (n.get("roles") or []) and n.get("node_id"))
        collected += len(batch)
        total = body.get("total")
        if not batch or not isinstance(total, int) or collected >= total:
            break
    return frozenset(ids)


async def _rfb_port(node_id: str, credential_id: str) -> int | None:
    body = await _request("GET", NODE_CREDENTIALS_PATH.format(node_id=node_id))
    for cred in body.get("credentials", []):
        if cred.get("credential_id") == credential_id:
            return cred.get("vnc_port")
    return None


async def _fetch_endpoint() -> DesktopVmEndpoint | None:
    body = await _request("GET", ENDPOINTS_PATH)
    picked = _pick_desktop(body.get("endpoints", []), await _vnc_role_node_ids(), await _load_pin())
    await _store_pin(picked["node_id"] if picked else None)
    if picked is None:
        return None
    return DesktopVmEndpoint(
        node_id=picked["node_id"],
        credential_id=picked["credential_id"],
        host=picked["ip_address"],
        web_port=int(picked["port"]),
        rfb_port=await _rfb_port(picked["node_id"], picked["credential_id"]),
    )


async def desktop_vnc_endpoint(*, force_refresh: bool = False) -> DesktopVmEndpoint | None:
    """The registered VNC desktop node, or None when the registry has none or there is no SLM link."""
    global _cache
    async with _cache_lock:
        if not force_refresh and _cache is not None and time.monotonic() - _cache[0] < REGISTRY_TTL_SECONDS:
            return _cache[1]
        try:
            endpoint = await _fetch_endpoint()
        except SlmLinkNotInitialised:
            logger.info("No SLM link: no VNC desktop node is registered")
            endpoint = None
        if endpoint is not None:
            logger.info("Desktop VM is registered node %s", endpoint.node_id)
        _cache = (time.monotonic(), endpoint)  # stamped after the fetch, so the TTL counts from the answer
        invalidate_internal_origin_cache()  # the egress policy must see the endpoint just resolved
        return endpoint


async def desktop_vnc_password(endpoint: DesktopVmEndpoint) -> bytes | None:
    """The node's own VNC password via connect then exchange-token; None when the SLM holds none."""
    info = await _request("POST", CONNECT_PATH.format(credential_id=endpoint.credential_id))
    token = info.get("connection_token")
    if not token:
        return None
    body = await _request("POST", EXCHANGE_PATH, params={"token": token})
    password = body.get("password") if isinstance(body, dict) else None
    return str(password).encode("utf-8") if password else None
