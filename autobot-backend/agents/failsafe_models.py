# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The failsafe agent's stand-in model (#19733)."""

import os

from autobot_shared.agent_model_tiers import AGENT_TIERS, TIER_MODELS
from autobot_shared.ssot_config import AgentConfigurationError


def failsafe_secondary_model(primary: str) -> str:
    """The same model twice is no fallback: both tiers fail together, so that is refused.

    Defaults to the tier table rather than raising when unset, because a host updated before its
    environment is rendered again must not lose the failsafe over a missing fallback setting.
    """
    default = TIER_MODELS[AGENT_TIERS["llm_failsafe_secondary"]]
    secondary = os.environ.get("AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL") or default
    if secondary == primary:
        raise AgentConfigurationError(
            f"AUTOBOT_LLM_FAILSAFE_MODEL and AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL are both {primary}: "
            "the failsafe has nothing to fall back to. Set them to different models."
        )
    return secondary
