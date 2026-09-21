# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for promoting heartbeat extra_data onto node_capability_profiles (#15495).

The SLM test suite stubs ``sqlalchemy`` globally (conftest.py, #13084), so a
``select``/``insert``/``update`` construct is itself a mock here and its
compiled SQL cannot be asserted on -- the same constraint
``services/node_gpu_test.py``'s ``_Db`` fake works under. What IS real and
worth asserting: ``_gpu_summary``'s pure aggregation, and
``apply_capability_profile``'s behavioral contract -- the no-op gate, and
exactly one existence check followed by exactly one write.
"""

import asyncio
from types import SimpleNamespace

from services.node_capability import _gpu_summary, apply_capability_profile

MEASURED = {
    "device_type": "nvidia-gpu",
    "index": 0,
    "name": "NVIDIA GeForce RTX 4070 Laptop GPU",
    "monitored": True,
    "utilization_percent": 12.0,
    "memory_used_mb": 2047.0,
    "memory_total_mb": 8188.0,
    "temperature_celsius": 51.0,
    "power_watts": None,
}
UNMONITORED = {"device_type": "amd-gpu", "monitored": False}

FULL_HEARTBEAT = {
    "total_ram_mb": 16000,
    "npu_present": False,
    "free_disk_model_dir_mb": 50000,
    "gpu": [MEASURED],
}


class _Db:
    """Records every ``execute()`` call; the first answers the existence check."""

    def __init__(self, existing: bool = False):
        self._existing = existing
        self.calls = []

    async def execute(self, statement):
        self.calls.append(statement)
        if len(self.calls) == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: ("node-1" if self._existing else None))
        return SimpleNamespace()


class TestGpuSummary:
    def test_not_reported_is_all_unknown(self):
        assert _gpu_summary(None) == (None, None, None)

    def test_empty_probe_is_a_real_zero(self):
        assert _gpu_summary([]) == (False, None, 0)

    def test_measured_device_reports_name_and_vram(self):
        assert _gpu_summary([MEASURED]) == (True, "NVIDIA GeForce RTX 4070 Laptop GPU", 8188)

    def test_unmonitored_device_is_present_with_unknown_vram(self):
        assert _gpu_summary([UNMONITORED]) == (True, None, None)

    def test_malformed_entries_are_skipped(self):
        assert _gpu_summary([{"device_type": "nvidia-gpu"}, MEASURED])[1] == "NVIDIA GeForce RTX 4070 Laptop GPU"


class TestApplyCapabilityProfile:
    def test_a_new_node_is_checked_then_inserted(self):
        db = _Db(existing=False)

        asyncio.run(apply_capability_profile(db, "node-1", FULL_HEARTBEAT))

        assert len(db.calls) == 2

    def test_a_known_node_is_checked_then_updated(self):
        db = _Db(existing=True)

        asyncio.run(apply_capability_profile(db, "node-1", FULL_HEARTBEAT))

        assert len(db.calls) == 2

    def test_a_pre_15495_heartbeat_is_a_no_op(self):
        """An agent that predates #15495 sends none of the three keys -- must never write."""
        db = _Db()

        asyncio.run(apply_capability_profile(db, "node-1", {"gpu": [MEASURED], "services": {}}))

        assert db.calls == []

    def test_partial_keys_are_a_no_op_not_a_partial_write(self):
        """Only two of three keys present must not blank the third with None."""
        db = _Db()

        asyncio.run(apply_capability_profile(db, "node-1", {"total_ram_mb": 16000, "npu_present": False}))

        assert db.calls == []
