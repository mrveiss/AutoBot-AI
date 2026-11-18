# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider preference order as configuration, not statement order (#15500).

``_populate_default_providers`` built the fallback chain by appending each
provider as its registration block ran, so the order was a property of where a
block sat in the file: Ollama was appended first and was therefore always
primary.  An operator who had configured and paid for a cloud provider still
got the local model for every request, and reached their own provider only
once Ollama had failed.

The order is now data.  ``AUTOBOT_LLM_PROVIDER_ORDER`` is a comma-separated
list of provider names in which ``*`` stands for "then every other registered
provider, in the order they registered":

    ollama,*            the default -- today's behaviour, local first
    anthropic,openai,*  those two first, everything else behind them
    anthropic           exhaustive: only anthropic is in the chain

The ``*`` is what lets an exhaustive list mean something.  Without it the list
*is* the whole chain, which is how a provider is held out of the generation
path rather than merely demoted.  With it, a provider the list never names
still sits in the chain at the ``*`` position, so adding a provider cannot
silently drop it.

#15494's three modes are values of this one setting rather than a second
mechanism beside it:

    full_local      ollama,*      Ollama first whatever keys are present
    full_provider   <provider>    the chosen provider only; Ollama absent
    (unset)         ollama,*      the same chain as full_local

Registration stays gated on credentials and this module registers nothing --
it orders what registration produced.  A name in the order that matched no
registered provider is logged, never raised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from autobot_shared.env_utils import env_str
from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import LLMProvider

logger = get_logger(__name__)

#: Stands for "every other registered provider, in registration order".
REST = "*"

#: Read through :func:`configured_order`; registered in ``env_registry_ai``.
ORDER_ENV_VAR = "AUTOBOT_LLM_PROVIDER_ORDER"

#: Local-first -- the order the registry produced before #15500.  Kept as the
#: default so an operator who configures nothing sees no change in behaviour.
DEFAULT_ORDER = "ollama,*"


@dataclass(frozen=True)
class OrderedChain:
    """A fallback chain, plus what the order decided to leave out of it."""

    #: Provider names to try, in order, when no provider was requested.
    chain: tuple[str, ...]

    #: Registered, but an exhaustive order left it out of the chain.  Still in
    #: the registry, so an explicit per-request or per-conversation choice
    #: reaches it; it is out of the *fallback* path only.
    excluded: tuple[str, ...]

    #: Named in the order, but no provider registered under that name -- its
    #: credentials are absent, or the name is a typo.  ``LLMProvider`` is now
    #: the set of registrable names (#17504), so ``apply_configured_order``
    #: splits this list: a name in ``LLMProvider`` is "absent credentials", one
    #: outside it is "unrecognised" (or a user-chosen custom instance name).
    unmatched: tuple[str, ...]


def parse_order(raw: str) -> tuple[str, ...]:
    """Split a configured order into lowercase tokens, dropping blanks."""
    return tuple(token.strip().lower() for token in raw.split(",") if token.strip())


def configured_order() -> tuple[str, ...]:
    """The order from the environment, read at call time rather than import.

    ``env_str`` already substitutes the default for an unset or blank value,
    but a value like ``","`` is neither -- it parses to no tokens at all, and
    an empty order would mean an empty chain and no provider reachable by
    fallback.  That is a configuration mistake, not a request for silence.
    """
    raw = env_str(ORDER_ENV_VAR, DEFAULT_ORDER)
    tokens = parse_order(raw)
    if tokens:
        return tokens
    logger.warning(
        "%s=%r names no provider; falling back to %r",
        ORDER_ENV_VAR,
        raw,
        DEFAULT_ORDER,
    )
    return parse_order(DEFAULT_ORDER)


def order_providers(registered: Iterable[str], order: Sequence[str]) -> OrderedChain:
    """Arrange the *registered* provider names according to *order*."""
    present = tuple(dict.fromkeys(name.lower() for name in registered))
    named = {token for token in order if token != REST}
    unnamed = [name for name in present if name not in named]

    chain: list[str] = []
    for token in order:
        for name in unnamed if token == REST else [token]:
            if name in present and name not in chain:
                chain.append(name)

    return OrderedChain(
        chain=tuple(chain),
        excluded=tuple(name for name in present if name not in chain),
        unmatched=tuple(dict.fromkeys(t for t in order if t != REST and t not in present)),
    )


def provider_is_permitted(name: str, order: Sequence[str] | None = None) -> bool:
    """False when an exhaustive configured order holds *name* out of the chain.

    A cross-provider model fallback hop is part of the generation path, so a
    provider kept out of the chain must not be reachable through one either --
    otherwise the order shuts the front door and a model hop lets the provider
    back in (#15500, and #15494's ``full_provider`` requirement that Ollama be
    absent rather than merely last).
    """
    tokens = configured_order() if order is None else order
    return REST in tokens or name.lower() in tokens


def _log_unmatched(unmatched: Sequence[str]) -> None:
    """Log names the order holds that no provider registered, split by cause (#17504)."""
    known = {member.value for member in LLMProvider}
    absent = [name for name in unmatched if name in known]
    unrecognised = [name for name in unmatched if name not in known]
    if absent:
        logger.info(
            "%s names %s, which matched no registered provider — absent credentials",
            ORDER_ENV_VAR,
            ", ".join(absent),
        )
    if unrecognised:
        logger.info(
            "%s names %s, which is not a known provider name (or a custom instance name)",
            ORDER_ENV_VAR,
            ", ".join(unrecognised),
        )


def apply_configured_order(registered: Sequence[str]) -> list[str]:
    """Order *registered* by configuration and log what the order decided."""
    order = configured_order()
    result = order_providers(registered, order)

    _log_unmatched(result.unmatched)
    if result.excluded:
        logger.info(
            "%s=%r is exhaustive, so %s stay out of the fallback chain; they "
            "remain registered and reachable by explicit request",
            ORDER_ENV_VAR,
            ",".join(order),
            ", ".join(result.excluded),
        )
    logger.info(
        "Provider registry initialised with %d providers: %s",
        len(result.chain),
        list(result.chain),
    )
    return list(result.chain)


__all__ = [
    "DEFAULT_ORDER",
    "ORDER_ENV_VAR",
    "REST",
    "OrderedChain",
    "apply_configured_order",
    "configured_order",
    "order_providers",
    "parse_order",
    "provider_is_permitted",
]
