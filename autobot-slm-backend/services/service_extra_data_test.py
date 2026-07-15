# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for services.service_extra_data.engine_degraded_fields (#11718).

Pure-function, dependency-free module — no DB, no network, no stubbing.
"""

from services.service_extra_data import engine_degraded_fields


class TestEngineDegradedFields:
    def test_absent_key_returns_empty_dict(self):
        assert engine_degraded_fields({"name": "redis"}) == {}

    def test_present_true_with_reason(self):
        result = engine_degraded_fields(
            {"name": "tts-worker", "engine_degraded": True, "degraded_reason": "HF auth failed"}
        )
        assert result == {"engine_degraded": True, "degraded_reason": "HF auth failed"}

    def test_present_false_still_included(self):
        # Explicit False must still be carried through (not treated as absent).
        result = engine_degraded_fields({"engine_degraded": False, "degraded_reason": None})
        assert result == {"engine_degraded": False, "degraded_reason": None}

    def test_coerces_truthy_value_to_bool(self):
        result = engine_degraded_fields({"engine_degraded": 1, "degraded_reason": "x"})
        assert result["engine_degraded"] is True
