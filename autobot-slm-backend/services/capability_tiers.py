# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure hardware-capability -> LLM tier-set mapping (#15495 AC5).

No DB, no I/O -- takes a profile, returns the tiers that fit. This feeds
#15494's Hybrid mode recommendation, which is not itself in scope here.

Model sizes are the part worth being honest about. Four of the six tiers were
measured directly on a dev host (#15495's own sizing reference). The other
two -- INSTRUCTION_MODEL and SYSTEM_MODEL -- were declared required but
absent from that host, so their sizes below are read from the Ollama
library's published default-quantization sizes instead of guessed: 4.4 GB
(Q4_K_M) for the instruction tier and 4.7 GB (Q4_0) for the system tier,
both read 2026-09-20.
"""

from __future__ import annotations

from dataclasses import dataclass

from autobot_shared.ssot_config import (
    CLASSIFICATION_MODEL,
    INSTRUCTION_MODEL,
    LIGHT_PROCESSING_MODEL,
    QUALITY_MODEL,
    ROUTING_MODEL,
    SYSTEM_MODEL,
)

# Smallest to largest -- "largest tier set that fits" is the longest PREFIX
# of this list whose per-model budget clears each tier in turn, not an
# independent per-tier decision: #2553's 6-tier mapping is additive, with the
# lighter tiers staying loaded alongside whatever heavier tier is serving.
TIER_SIZES_MB: dict[str, int] = {
    ROUTING_MODEL: 1300,  # llama3.2:1b -- #15495 dev-host measurement
    CLASSIFICATION_MODEL: 1600,  # gemma2:2b -- #15495 dev-host measurement
    LIGHT_PROCESSING_MODEL: 2200,  # phi3:mini -- #15495 dev-host measurement
    INSTRUCTION_MODEL: 4400,  # mistral:7b-instruct -- ollama.com library, Q4_K_M default
    SYSTEM_MODEL: 4700,  # dolphin-llama3:8b -- ollama.com library, Q4_0 default
    QUALITY_MODEL: 6600,  # qwen3.5:9b -- #15495 dev-host measurement
}

# dict preserves insertion order (smallest to largest) -- Python 3.7+ guarantee.
_TIER_ORDER = tuple(TIER_SIZES_MB)


@dataclass(frozen=True)
class CapabilityProfile:
    """The subset of a node's hardware profile the tier-fit function needs."""

    total_ram_mb: int | None
    total_vram_mb: int | None
    gpu_present: bool | None


def recommend_tier_set(profile: CapabilityProfile, max_loaded_models: int = 5) -> list[str]:
    """The largest prefix of the 6-tier list that fits *profile*, headroomed for concurrency.

    Prefers VRAM when a GPU is present and measured (Ollama offloads loaded
    layers there first); falls back to total RAM otherwise. An unknown budget
    (neither total is known) returns an empty list rather than guessing a fit
    -- #15495 AC7's "unknown, not a fabricated pass" applies here too.
    """
    if profile.gpu_present and profile.total_vram_mb:
        budget_mb = profile.total_vram_mb
    else:
        budget_mb = profile.total_ram_mb
    if not budget_mb or max_loaded_models <= 0:
        return []

    per_model_budget_mb = budget_mb / max_loaded_models
    fitted = []
    for tier in _TIER_ORDER:
        if TIER_SIZES_MB[tier] > per_model_budget_mb:
            break
        fitted.append(tier)
    return fitted
