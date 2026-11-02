# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The failsafe agent's stand-in model (#19733)."""

import os

from autobot_shared.agent_model_tiers import AGENT_TIERS, TIER_MODELS
from autobot_shared.ssot_config import AgentConfigurationError


def failsafe_answer(response) -> str:
    """The text of a response. ``llm.chat`` reports failure in ``error``, it doesn't raise."""
    if response.error:
        raise RuntimeError(response.error)
    return response.content


def failsafe_primary_model() -> str:
    """The first model to try. Unset, it comes from the tier table: the failsafe is what runs when
    configuration has gone wrong, so a missing setting mustn't stop it starting."""
    explicit = (os.environ.get("AUTOBOT_LLM_FAILSAFE_MODEL") or "").strip()
    return explicit or TIER_MODELS[AGENT_TIERS["llm_failsafe"]]


def failsafe_secondary_model(primary: str) -> str:
    """The stand-in model. The same model twice is no fallback: both tiers fail together.

    Unset, it comes from the tier table, so a host whose environment isn't rendered yet keeps its
    failsafe, and a host whose primary is set to that same model gets the other tier's. Only two
    settings naming one model are refused.
    """
    explicit = (os.environ.get("AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL") or "").strip()
    if explicit and explicit == primary:
        raise AgentConfigurationError(
            f"AUTOBOT_LLM_FAILSAFE_MODEL and AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL are both {primary}: "
            "the failsafe has nothing to fall back to. Set them to different models."
        )
    if explicit:
        return explicit
    default = TIER_MODELS[AGENT_TIERS["llm_failsafe_secondary"]]
    return default if default != primary else TIER_MODELS[AGENT_TIERS["llm_failsafe"]]
