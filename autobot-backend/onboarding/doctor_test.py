# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for onboarding doctor / recommender logic (Issue #5061).
Tests mock psutil and aiohttp so no real hardware or network is required.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Minimal stubs so the module can be imported without psutil installed
# ---------------------------------------------------------------------------

if "psutil" not in sys.modules:
    psutil_stub = types.ModuleType("psutil")

    _vmem = MagicMock()
    _vmem.total = 8 * 1024**3  # 8 GiB
    _vmem.available = 4 * 1024**3

    _disk = MagicMock()
    _disk.total = 100 * 1024**3  # 100 GiB
    _disk.free = 50 * 1024**3

    psutil_stub.virtual_memory = MagicMock(return_value=_vmem)
    psutil_stub.disk_usage = MagicMock(return_value=_disk)
    psutil_stub.cpu_count = MagicMock(return_value=4)
    sys.modules["psutil"] = psutil_stub


from onboarding.doctor import (
    TIER_BALANCED,
    TIER_FAST,
    TIER_POWERFUL,
    _hardware_scan,
    _recommend_tier,
)


class TestRecommendTier:
    def test_powerful_tier_with_high_ram(self):
        tier = _recommend_tier(ram_gb=32.0, cpu_cores=16)
        assert tier == TIER_POWERFUL

    def test_balanced_tier_with_moderate_ram(self):
        tier = _recommend_tier(ram_gb=12.0, cpu_cores=8)
        assert tier == TIER_BALANCED

    def test_fast_tier_with_low_ram(self):
        tier = _recommend_tier(ram_gb=4.0, cpu_cores=2)
        assert tier == TIER_FAST

    def test_boundary_balanced_exact(self):
        # 8 GiB is the lower bound for balanced
        tier = _recommend_tier(ram_gb=8.0, cpu_cores=4)
        assert tier in (TIER_BALANCED, TIER_POWERFUL)

    def test_returns_string(self):
        tier = _recommend_tier(ram_gb=16.0, cpu_cores=8)
        assert isinstance(tier, str)


class TestHardwareScan:
    def test_returns_required_keys(self):
        result = _hardware_scan()
        for key in ("ram_gb", "ram_available_gb", "disk_total_gb", "disk_free_gb", "cpu_cores"):
            assert key in result, f"Missing key '{key}' in hardware scan"

    def test_ram_gb_positive(self):
        result = _hardware_scan()
        assert result["ram_gb"] > 0

    def test_cpu_cores_positive(self):
        result = _hardware_scan()
        assert result["cpu_cores"] > 0
