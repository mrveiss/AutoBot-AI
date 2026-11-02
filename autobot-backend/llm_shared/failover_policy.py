# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How long a failed model is held out, who a failure may be charged to, and where a failover may not go (#19753).

Skip window -- a transient provider error only *skips* the model for
``AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS`` (``provider_degradation``), the one
existing env-backed window; this module adds nothing parallel to it.

Hold -- a plan/quota limit holds the model until it resets: the provider's own
reset when it stated one, else ``AUTOBOT_LLM_QUOTA_HOLD_DEFAULT_SECONDS``, never
longer than ``AUTOBOT_LLM_QUOTA_HOLD_MAX_SECONDS`` so a bogus reset cannot park a
model forever.

Who pays -- the degradation mark is shared by every user and worker, so only a cause that is
the *provider's* may set it (``marks_provider_wide``). A caller's own credential
(``may_fail_over``) or one local request that a local model could not serve is not.

Locality -- failover never carries a prompt from a local model to an external provider unless
the operator wrote that chain (``AUTOBOT_FALLBACK_CHAIN_*``). "Local" is by provider *type*
(``OptimizationRouter.LOCAL_PROVIDERS``), not by host: an Ollama pointed at a remote machine is
still "local" here. The in-code default chains are cloud-to-cloud (ending on a local model) and so
never authorise leaving the machine.
"""

from __future__ import annotations

import math
from typing import Optional

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

from .optimization.router import OptimizationRouter
from .provider_error_category import ProviderErrorCategory, ProviderFailure
from .run_credentials import get_llm_principal
from .types import ProviderType

logger = get_logger(__name__)

_QUOTA_HOLD_DEFAULT_SECONDS: int = env_int_clamped("AUTOBOT_LLM_QUOTA_HOLD_DEFAULT_SECONDS", 3600, 1, 604800)
_QUOTA_HOLD_MAX_SECONDS: int = env_int_clamped("AUTOBOT_LLM_QUOTA_HOLD_MAX_SECONDS", 86400, 1, 2592000)


def hold_seconds(failure: ProviderFailure) -> Optional[int]:
    """TTL for the degradation mark: ``None`` = the plain skip window, else the quota hold.

    The provider's stated reset is clamped *before* ``int()``: ``int(inf)`` raises and ``1e999``
    parses to ``inf``. A non-finite or non-positive value is no reset at all and takes the default.
    """
    if not failure.category.holds_until_reset:
        return None
    reset = failure.retry_after
    until_reset = reset if reset is not None and math.isfinite(reset) and reset > 0 else _QUOTA_HOLD_DEFAULT_SECONDS
    return max(1, int(min(until_reset, _QUOTA_HOLD_MAX_SECONDS)))


def caller_owns_credential() -> bool:
    """True when the current call runs for a signed-in user, so the credential used may be that user's own.

    Evidence: ``provider_oauth_credentials.resolve_signed_in_token`` resolves the requesting user's own
    token first, and the principal that selects it is set by the chat turn and by both compat routes
    (``llm_principal_scope_for``). With a principal in scope there is no way to tell, here, whether the
    shared API key or the user's token was used -- so a credential failure is treated as the caller's.
    """
    principal = get_llm_principal()
    return bool(principal and principal[0])


def may_fail_over(failure: ProviderFailure) -> bool:
    """False for an authentication failure on a credential that may be the caller's own: it surfaces as before."""
    if failure.category is ProviderErrorCategory.AUTHENTICATION and caller_owns_credential():
        logger.info("failover: authentication failure on a possibly caller-owned credential -- surfaced, no hop")
        return False
    return True


def marks_provider_wide(failure: ProviderFailure, provider: Optional[str]) -> bool:
    """True when *failure* may degrade the provider:model for every user and worker.

    Provider-wide causes: rate limit, billing, a network failure, and a timeout or 5xx from a *hosted*
    provider. Not provider-wide: a caller's credential (``may_fail_over``), and a 5xx or timeout from a
    *local* provider -- a local server answers 500 for one request it cannot serve (a prompt that does
    not fit, a model that fails to load for it) while still serving everyone else, and a slow generation
    times out the same way. A local server that is really down fails to connect, which is NETWORK.
    """
    category = failure.category
    if category is ProviderErrorCategory.AUTHENTICATION:
        return not caller_owns_credential()
    if category in (ProviderErrorCategory.PROVIDER_UNAVAILABLE, ProviderErrorCategory.TIMEOUT):
        return not is_local_provider(provider)
    return True


def is_local_provider(name: Optional[str]) -> bool:
    """True for a provider that keeps prompts on the operator's own hardware. Unknown names are not."""
    if not name:
        return False
    try:
        return ProviderType(name.lower()) in OptimizationRouter.LOCAL_PROVIDERS
    except ValueError:
        return False


def _is_known_external(name: Optional[str]) -> bool:
    """True only for a provider we can name and know to be hosted -- an unknown origin is not."""
    if not name:
        return False
    try:
        return ProviderType(name.lower()) not in OptimizationRouter.LOCAL_PROVIDERS
    except ValueError:
        return False


def locality_allows(from_provider: Optional[str], to_provider: Optional[str], *, operator_configured: bool) -> bool:
    """False when a hop could move a prompt from a local (or unknown) origin to an external destination.

    An origin counts as external only when it is a known hosted provider; an unknown or unresolved one
    is treated as local, so it cannot hop outward. A hop naming no provider is treated as *external*:
    the cloned request then carries no provider and the registry picks one by the configured order,
    which may be a hosted one. Both are allowed only on a chain the operator wrote.
    """
    if _is_known_external(from_provider) or is_local_provider(to_provider) or operator_configured:
        return True
    logger.warning(
        "failover: refusing %r -> %r -- local to external is allowed only on an operator-configured chain",
        from_provider,
        to_provider,
    )
    return False
