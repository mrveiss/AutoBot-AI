# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the pure capability -> tier-set mapping (#15495 AC6).

No GPU, small VRAM, large VRAM, and missing/unknown fields -- the four
scenarios the acceptance criteria name explicitly.
"""

from autobot_shared.ssot_config import (
    CLASSIFICATION_MODEL,
    INSTRUCTION_MODEL,
    LIGHT_PROCESSING_MODEL,
    QUALITY_MODEL,
    ROUTING_MODEL,
    SYSTEM_MODEL,
)
from services.capability_tiers import CapabilityProfile, recommend_tier_set


def test_no_gpu_falls_back_to_ram():
    profile = CapabilityProfile(total_ram_mb=16000, total_vram_mb=None, gpu_present=False)

    tiers = recommend_tier_set(profile, max_loaded_models=5)

    # 16000 / 5 = 3200 MB per model: routing (1300), classification (1600) and
    # light (2200) fit; instruction (4400) does not.
    assert tiers == [ROUTING_MODEL, CLASSIFICATION_MODEL, LIGHT_PROCESSING_MODEL]


def test_small_vram_fits_nothing():
    profile = CapabilityProfile(total_ram_mb=8000, total_vram_mb=2048, gpu_present=True)

    tiers = recommend_tier_set(profile, max_loaded_models=5)

    # 2048 / 5 = 409.6 MB per model -- smaller than even the routing tier.
    assert tiers == []


def test_large_vram_fits_everything_but_the_top_tier():
    profile = CapabilityProfile(total_ram_mb=32000, total_vram_mb=24576, gpu_present=True)

    tiers = recommend_tier_set(profile, max_loaded_models=5)

    # 24576 / 5 = 4915.2 MB per model: everything up to system (4700) fits;
    # quality (6600) does not.
    assert tiers == [
        ROUTING_MODEL,
        CLASSIFICATION_MODEL,
        LIGHT_PROCESSING_MODEL,
        INSTRUCTION_MODEL,
        SYSTEM_MODEL,
    ]
    assert QUALITY_MODEL not in tiers


def test_gpu_present_but_vram_unmeasured_falls_back_to_ram():
    """An unmonitored GPU (#16280) reports present with no VRAM number -- RAM still answers."""
    profile = CapabilityProfile(total_ram_mb=6500, total_vram_mb=None, gpu_present=True)

    tiers = recommend_tier_set(profile, max_loaded_models=5)

    assert tiers == [ROUTING_MODEL]


def test_missing_fields_return_no_recommendation_rather_than_a_guess():
    profile = CapabilityProfile(total_ram_mb=None, total_vram_mb=None, gpu_present=None)

    assert recommend_tier_set(profile) == []


def test_zero_max_loaded_models_returns_no_recommendation():
    profile = CapabilityProfile(total_ram_mb=32000, total_vram_mb=None, gpu_present=False)

    assert recommend_tier_set(profile, max_loaded_models=0) == []


def test_tier_order_matches_the_sizing_table_smallest_to_largest():
    from services.capability_tiers import TIER_SIZES_MB

    sizes = list(TIER_SIZES_MB.values())
    assert sizes == sorted(sizes)
