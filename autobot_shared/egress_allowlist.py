# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The internal-origin allowlist behind ``EGRESS_POLICY`` (#17576, AC4).

Rule 8 wants every outbound request guarded; AutoBot's own service-to-service
traffic must still reach hosts that are loopback on a single-host deployment,
which :mod:`autobot_shared.url_safety` hard-blocks in both modes. The policy is
therefore "internal origins bypass the check, everything else must be public",
and this module is the one place that says what *internal* means.

**Exact origin match, never a bare host.** An origin is ``scheme://host:port``
with the port always explicit. A known-internal host on another port is a
different service, possibly a different trust domain, so it is NOT internal.

**One normaliser** (:func:`normalize_origin`) is used both to build the set and
to match against it, so the two sides cannot disagree about case, default ports
or IPv6 brackets.

**Only for server-chosen URLs.** ``EGRESS_POLICY`` (which consults this set) is for URLs the server
picked itself -- from the SSOT or operator configuration. A URL a user, an LLM or a document supplied
must use ``guard_egress=False`` (public-only, no internal trust): trusting an internal origin there
would let the requester aim the server at its own services.

**Config LLM base URLs are not trusted as internal.** The OpenAI and Anthropic base URLs (and any other
operator-set LLM gateway URL) stay on the public-only check; a private gateway needs an owner policy decision.

**Residual, stated rather than discovered (#18199).** Matching compares origin *strings* and does not
resolve DNS. A DNS-named config host is trusted wherever the name resolves at request time.

**Strict URLs only.** The bypass is granted only to a URL whose raw ``scheme://host[:port]`` prefix
equals the parsed origin textually, with no userinfo, backslash, whitespace, control or
percent-encoded character in the authority (:func:`strict_origin`). ``urlparse`` and the HTTP clients
(urllib3, yarl, httpx) disagree about a backslash before an `@` in the authority; anything
not strictly shaped is not internal and falls through to the public-only check.

Static origins come from the SSOT (:data:`autobot_shared.ssot_config.config`).
Dynamic origins (e.g. SLM-managed nodes) arrive through providers registered
with :func:`register_internal_origin_provider`; their result is cached for
``EGRESS_INTERNAL_ORIGINS_TTL_S`` and a failing provider never breaks the
static set.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from typing import Awaitable, Callable, Iterable, Optional
from urllib.parse import urlparse

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Seconds a provider-derived origin set is reused before providers run again.
EGRESS_INTERNAL_ORIGINS_TTL_S: int = env_int("AUTOBOT_EGRESS_INTERNAL_ORIGINS_TTL_S", 60)

#: Seconds one provider may take before it is abandoned for this refresh (static origins still apply).
EGRESS_PROVIDER_TIMEOUT_S: int = env_int("AUTOBOT_EGRESS_PROVIDER_TIMEOUT_S", 5)

_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}

OriginProvider = Callable[[], Awaitable[Iterable[str]]]

_providers: list[OriginProvider] = []
_cache: tuple[float, frozenset[str]] | None = None


def normalize_origin(url: object) -> Optional[str]:
    """``scheme://host:port`` for *url*, or ``None`` when it has no usable origin.

    Scheme and host are lowercased, IPv6 hosts are bracketed, and the port is
    explicit (defaulted by scheme). Path, query and userinfo are ignored. A
    scheme-less string, an unparsable one, or a scheme with neither an explicit
    port nor a known default yields ``None``.
    """
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url.strip())
        scheme, host, port = parsed.scheme.lower(), parsed.hostname, parsed.port
    except ValueError:
        return None
    port = port or _DEFAULT_PORTS.get(scheme)
    if not scheme or not host or not parsed.netloc or port is None:
        return None
    return f"{scheme}://{f'[{host}]' if ':' in host else host}:{port}"


_ALWAYS_REFUSED_HOSTS = frozenset(ipaddress.ip_address(h) for h in ("169.254.169.254", "fd00:ec2::254"))


def _never_internal(origin: str) -> bool:
    """True for a literal link-local, cloud-metadata or unspecified host (loopback stays: single-host default)."""
    host = origin.split("://", 1)[1].rsplit(":", 1)[0].strip("[]")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a DNS name: not resolved here (#18199)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped  # ::ffff:169.254.169.254 is not is_link_local until unwrapped
    return ip.is_link_local or ip.is_unspecified or ip in _ALWAYS_REFUSED_HOSTS


def _normalized(urls: Iterable[object]) -> frozenset[str]:
    """Normalised origins of *urls*, minus any literal host that must never be trusted as internal."""
    kept = set()
    for origin in filter(None, (normalize_origin(u) for u in urls)):
        if _never_internal(origin):
            logger.warning("Dropping internal-origin %s: link-local / metadata / unspecified host", origin)
        else:
            kept.add(origin)
    return frozenset(kept)


def _ssot_service_urls() -> list[str]:
    """Node-to-node HTTP targets the SSOT declares (found by reading ``AutoBotConfig`` in ssot_config.py).

    ``backend_url``, ``ollama_url``, ``aistack_url``, ``npu_worker_url``, ``tts_worker_url``,
    ``browser_service_url`` and ``slm_url`` are URL properties; ChromaDB has none and is built from
    ``vm.chromadb`` + ``port.chromadb``. :func:`_server_called_urls` adds the targets server code calls
    that the SSOT declares differently.

    Deliberately absent: ``redis_url`` (``redis://``, never HTTP egress), ``chrome_cdp_url`` (Playwright
    ``connect_over_cdp`` only -- allowlisting it would expose CDP ``/json/*`` control), ``vnc_url`` (a link
    for a human) and ``websocket_url`` (handed to clients).
    """
    from autobot_shared.ssot_config import config

    names = (
        "backend_url",
        "ollama_url",
        "aistack_url",
        "npu_worker_url",
        "tts_worker_url",
        "browser_service_url",
        "slm_url",
    )
    urls = [getattr(config, name, "") for name in names]
    urls.append(f"http://{config.vm.chromadb}:{config.port.chromadb}")
    return urls + _server_called_urls()


def _ws_scheme(url: str) -> str:
    """*url* with ``http``/``https`` mapped to ``ws``/``wss`` (same host and port): the SLM event socket."""
    return re.sub(r"^http(s?)://", r"ws\1://", url, count=1, flags=re.IGNORECASE)


def _server_called_urls() -> list[str]:
    """Origins the server itself calls, each from its SSOT source (never a second literal list).

    The earlier exclusion of ``frontend_url`` and the VNC link was about callers that only hand a link
    to a human. These are here because server code requests them: ``api/analytics.py`` health check
    (frontend), ``api/vnc_proxy.py`` ``VNC_ENDPOINTS`` HTTP and websockify calls (``vm.main`` and
    ``vm.browser`` on ``port.vnc``; the websockify call is ``wss://``, so both schemes), and
    ``api/monitoring.py`` Alertmanager queries (``ServiceURLs.ALERTMANAGER_API``), the SLM event websocket
    (``config.slm_url`` with the scheme mapped http->ws, https->wss), and the local LLM servers the provider
    health probes call (``config.llm.lmstudio_host`` and ``config.vllm_host``, both full URLs).
    Prometheus is deliberately absent: its host is derived two ways (``vm.main`` vs ``REDIS_VM_IP``), pending #18326.
    """
    from autobot_shared.network_constants import ServiceURLs
    from autobot_shared.ssot_config import config

    return [
        config.frontend_url,
        *(
            f"{scheme}://{host}:{config.port.vnc}"
            for host in (config.vm.main, config.vm.browser)
            for scheme in ("http", "wss")
        ),
        ServiceURLs.ALERTMANAGER_API,
        _ws_scheme(config.slm_url),
        config.llm.lmstudio_host,
        config.vllm_host,
    ]


def static_internal_origins() -> frozenset[str]:
    """Origins derived from the SSOT, recomputed on every call (config may reload)."""
    return _normalized(_ssot_service_urls())


def register_internal_origin_provider(provider: OriginProvider) -> None:
    """Add an async callable yielding extra internal URLs/origins (e.g. SLM nodes).

    Registering invalidates the cache so the new provider is consulted at once.
    """
    global _cache
    if provider not in _providers:
        _providers.append(provider)
    _cache = None


async def _provider_origins() -> frozenset[str]:
    global _cache
    now = time.monotonic()
    if _cache is not None and now < _cache[0]:
        return _cache[1]
    found: set[str] = set()
    for provider in list(_providers):
        try:
            found |= _normalized(await asyncio.wait_for(provider(), EGRESS_PROVIDER_TIMEOUT_S))
        except Exception:
            logger.warning("Internal-origin provider %r failed; static origins only", provider, exc_info=True)
    result = frozenset(found)
    _cache = (now + EGRESS_INTERNAL_ORIGINS_TTL_S, result)
    return result


async def internal_origins() -> frozenset[str]:
    """Static SSOT origins plus the (TTL-cached) provider origins."""
    return static_internal_origins() | await _provider_origins()


_UNSAFE_AUTHORITY = re.compile(r"[\\@%\s\x00-\x1f\x7f]|[^\x00-\x7f]")


def strict_origin(url: object) -> Optional[str]:
    """:func:`normalize_origin` of *url*, but only when every HTTP parser would read it the same way.

    ``None`` for a URL with userinfo, a backslash, whitespace/control/non-ASCII or percent-encoded
    characters in the authority, or whose raw ``scheme://authority`` text differs from the parsed origin
    (e.g. a zero-padded port).
    """
    origin = normalize_origin(url)
    if origin is None or not isinstance(url, str):
        return None
    scheme, sep, rest = url.partition("://")
    authority = re.split(r"[/?#]", rest, maxsplit=1)[0]
    if not sep or _UNSAFE_AUTHORITY.search(authority) or _UNSAFE_AUTHORITY.search(scheme):
        return None
    raw = f"{scheme}://{authority}".lower()
    default_port = _DEFAULT_PORTS.get(scheme.lower())
    return origin if raw == origin or (default_port and raw + f":{default_port}" == origin) else None


def operator_origins(entries: Iterable[object]) -> frozenset[str]:
    """Strictly shaped origins of operator-listed URLs, minus literal link-local/metadata/unspecified hosts.

    For an operator-named allowlist of exact origins that is NOT the SSOT service set (e.g. LLM tracing
    destinations, #19933): the same strictness as :func:`is_internal_origin`, the same refused hosts as
    :func:`_normalized`, without trusting any SSOT service.
    """
    return frozenset(o for o in (strict_origin(e) for e in entries) if o and not _never_internal(o))


async def is_internal_origin(url: str) -> bool:
    """True when *url* is strictly shaped and its exact origin is in :func:`internal_origins`."""
    origin = strict_origin(url)
    return origin is not None and origin in await internal_origins()


def reset_internal_origin_state() -> None:
    """Drop providers and the cache (test isolation)."""
    global _cache
    _providers.clear()
    _cache = None
