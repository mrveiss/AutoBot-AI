# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How long a failed model is held out, and where a failover may not go (#19753).

Skip window -- a transient provider error only *skips* the model for
``AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS`` (``provider_degradation``), the one
existing env-backed window; this module adds nothing parallel to it.

Hold -- a plan/quota limit holds the model until it resets: the provider's own
reset when it stated one, else ``AUTOBOT_LLM_QUOTA_HOLD_DEFAULT_SECONDS``, never
longer than ``AUTOBOT_LLM_QUOTA_HOLD_MAX_SECONDS`` so a bogus reset cannot park a
model forever.

Locality -- failover never carries a prompt from a local model to an external
provider unless the operator wrote that chain (``AUTOBOT_FALLBACK_CHAIN_*``).
The in-code default chains are cloud-to-cloud (ending on a local model) and so
never authorise leaving the machine.
"""

from __future__ import annotations

from typing import Optional

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

from .optimization.router import OptimizationRouter
from .provider_error_category import ProviderFailure
from .types import ProviderType

logger = get_logger(__name__)

_QUOTA_HOLD_DEFAULT_SECONDS: int = env_int_clamped("AUTOBOT_LLM_QUOTA_HOLD_DEFAULT_SECONDS", 3600, 1, 604800)
_QUOTA_HOLD_MAX_SECONDS: int = env_int_clamped("AUTOBOT_LLM_QUOTA_HOLD_MAX_SECONDS", 86400, 1, 2592000)


def hold_seconds(failure: ProviderFailure) -> Optional[int]:
    """TTL for the degradation mark: ``None`` = the plain skip window, else the quota hold."""
    if not failure.category.holds_until_reset:
        return None
    until_reset = failure.retry_after if failure.retry_after else _QUOTA_HOLD_DEFAULT_SECONDS
    return max(1, min(int(until_reset), _QUOTA_HOLD_MAX_SECONDS))


def is_local_provider(name: Optional[str]) -> bool:
    """True for a provider that keeps prompts on the operator's own hardware. Unknown names are external."""
    if not name:
        return False
    try:
        return ProviderType(name.lower()) in OptimizationRouter.LOCAL_PROVIDERS
    except ValueError:
        return False


def locality_allows(from_provider: Optional[str], to_provider: Optional[str], *, operator_configured: bool) -> bool:
    """False when a hop would move a prompt from a local provider to an external one on a default chain.

    A hop naming no provider inherits the failed one's, so it cannot cross.
    """
    if not to_provider or not is_local_provider(from_provider):
        return True
    if is_local_provider(to_provider) or operator_configured:
        return True
    logger.warning(
        "failover: refusing %r -> %r -- local to external is allowed only on an operator-configured chain",
        from_provider,
        to_provider,
    )
    return False
