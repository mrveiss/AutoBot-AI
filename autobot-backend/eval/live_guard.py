# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The local-only guard of the live eval (#20843).

A live run sends the golden prompts to a model. Unless the operator says otherwise, that model must be a local
provider on a loopback or private origin; anything else is refused before the first prompt leaves, and the
report stamps ``local_only`` and an endpoint *class* (never a host) so a remote run cannot pass for a local one.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List
from urllib.parse import urlparse

from autobot_shared.egress_allowlist import is_internal_origin
from autobot_shared.env_registry import env
from llm_shared.failover_policy import is_local_provider

LOOPBACK, PRIVATE, PUBLIC = "loopback", "private", "public"
_LOCAL_CLASSES = frozenset({LOOPBACK, PRIVATE})
_LOOPBACK_NAMES = frozenset({"localhost"})
#: RFC 1918, link-local and IPv6 unique-local ranges. Not ``ipaddress``'s ``is_private``, which also accepts the
#: documentation and other reserved ranges that no deployment's own network uses.
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fc00::/7")
)

#: ``model -> endpoint URL`` as the chat route will actually resolve it.
EndpointResolver = Callable[[str], Awaitable[str]]


class RemoteProviderRefused(RuntimeError):
    """The live run would send prompts somewhere that is not local-only, and the operator did not allow it."""


@dataclass(frozen=True)
class Locality:
    """Where one model's prompts go, as a class and never as a host string."""

    model: str
    provider: str
    endpoint_class: str
    local_only: bool


async def endpoint_class(url: str) -> str:
    """``loopback`` / ``private`` / ``public`` for *url*; a name that is not a known internal origin is public."""
    host = (urlparse(url).hostname or "").strip("[]").lower()
    if host in _LOOPBACK_NAMES:
        return LOOPBACK
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return PRIVATE if await is_internal_origin(url) else PUBLIC
    if address.is_loopback:
        return LOOPBACK
    return PRIVATE if any(address in net for net in _PRIVATE_NETWORKS) else PUBLIC


async def classify_locality(model: str, provider: str, resolve_endpoint: EndpointResolver) -> Locality:
    """The locality of one model: local provider AND a loopback/private endpoint."""
    klass = await endpoint_class(await resolve_endpoint(model))
    return Locality(model, provider, klass, is_local_provider(provider) and klass in _LOCAL_CLASSES)


def remote_allowed() -> bool:
    """True when the operator set ``AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER``."""
    return bool(env("AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER"))


async def assert_local_only(
    models: List[str], provider: str, resolve_endpoint: EndpointResolver, allow_remote: bool = False
) -> Dict[str, Locality]:
    """Resolve every model's locality; refuse the run unless all are local or remote was explicitly allowed.

    Raises ``RemoteProviderRefused`` naming the model and the endpoint class, never the host.
    """
    found = {m: await classify_locality(m, provider, resolve_endpoint) for m in models}
    remote = [loc for loc in found.values() if not loc.local_only]
    if remote and not (allow_remote or remote_allowed()):
        detail = ", ".join(f"{loc.model} ({loc.provider}, {loc.endpoint_class})" for loc in remote)
        raise RemoteProviderRefused(
            f"refusing a live eval against a non-local provider/endpoint: {detail}. "
            "Set AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER=true to run it anyway; the report will say local_only=false."
        )
    return found


def non_local_fallback_chains() -> List[str]:
    """Env names of operator fallback chains (``AUTOBOT_FALLBACK_CHAIN_*``) with a hop to a non-local provider.

    A hop that names no provider inherits the request's own, so it is as local as the primary. The chain is
    named by its primary model key, never by an endpoint.
    """
    from llm_shared.fallback_chain import FallbackChainManager

    found = []
    for chain in FallbackChainManager().operator_chains():
        providers = chain.fallback_providers or []
        if any(p and not is_local_provider(p) for p in providers):
            found.append(chain.primary_model)
    return found


def assert_chains_local(allow_remote: bool = False) -> None:
    """Refuse the run when an operator fallback chain could move a prompt to a hosted provider."""
    remote = non_local_fallback_chains()
    if remote and not (allow_remote or remote_allowed()):
        raise RemoteProviderRefused(
            f"refusing a live eval: AUTOBOT_FALLBACK_CHAIN_* for {', '.join(remote)} can fail over to a "
            "non-local provider. Set AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER=true to run it anyway."
        )
