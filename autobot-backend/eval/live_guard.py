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

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List

from autobot_shared.env_registry import env
from autobot_shared.url_safety import LOOPBACK, PRIVATE, PUBLIC, url_locality_async  # noqa: F401  (re-exported)
from llm_shared.failover_policy import is_local_provider

_LOCAL_CLASSES = frozenset({LOOPBACK, PRIVATE})

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
    """``loopback`` / ``private`` / ``public`` for *url*, by the SSOT host classification (``url_safety``).

    Fail closed: a host that does not resolve, or resolves to any public address, is ``public``.
    """
    return await url_locality_async(url)


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
    """Primary-model keys of the ACTIVE manager's operator fallback chains with a hop to a non-local provider.

    A hop that names no provider inherits the request's own, so it is as local as the primary. The chain is
    named by its primary model key, never by an endpoint. The manager inspected is the one the chat route's
    failover consults (``get_fallback_chain_manager``), so a chain registered at runtime is seen too.
    """
    from llm_shared.fallback_chain import get_fallback_chain_manager

    found = []
    for chain in get_fallback_chain_manager().operator_chains():
        providers = chain.fallback_providers or []
        if any(p and not is_local_provider(p) for p in providers):
            found.append(chain.primary_model)
    return found


def assert_chains_local(allow_remote: bool = False) -> List[str]:
    """Refuse the run when an operator fallback chain could move a prompt to a hosted provider.

    Returns the chains that can (empty when none can), so an allowed remote run stamps that in its report.
    """
    remote = non_local_fallback_chains()
    if remote and not (allow_remote or remote_allowed()):
        raise RemoteProviderRefused(
            f"refusing a live eval: AUTOBOT_FALLBACK_CHAIN_* for {', '.join(remote)} can fail over to a "
            "non-local provider. Set AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER=true to run it anyway."
        )
    return remote
