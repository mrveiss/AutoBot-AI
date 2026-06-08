# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for onboarding preset loader (Issue #5061).
"""

from onboarding.presets import get_all_presets, get_preset

REQUIRED_FIELDS = {"name", "title", "description", "agents", "skills", "connectors", "system_prompt", "llm_tier"}
VALID_TIERS = {"fast", "balanced", "powerful"}


class TestGetAllPresets:
    def test_returns_at_least_five_presets(self):
        presets = get_all_presets()
        assert len(presets) >= 5

    def test_all_presets_have_required_fields(self):
        for preset in get_all_presets():
            missing = REQUIRED_FIELDS - set(preset.keys())
            assert not missing, f"Preset '{preset.get('name')}' missing fields: {missing}"

    def test_all_names_are_unique(self):
        names = [p["name"] for p in get_all_presets()]
        assert len(names) == len(set(names)), "Duplicate preset names found"

    def test_all_llm_tiers_are_valid(self):
        for preset in get_all_presets():
            assert (
                preset["llm_tier"] in VALID_TIERS
            ), f"Preset '{preset['name']}' has invalid llm_tier '{preset['llm_tier']}'"

    def test_returns_copies_not_references(self):
        presets = get_all_presets()
        presets[0]["name"] = "mutated"
        # Second call should be unaffected
        assert get_all_presets()[0]["name"] != "mutated"


class TestGetPreset:
    def test_returns_known_preset(self):
        preset = get_preset("chat-simple")
        assert preset is not None
        assert preset["name"] == "chat-simple"

    def test_returns_none_for_unknown_name(self):
        assert get_preset("nonexistent-preset") is None

    def test_returns_copy_not_reference(self):
        preset = get_preset("chat-simple")
        assert preset is not None
        preset["title"] = "mutated"
        # Subsequent call should return original title
        assert get_preset("chat-simple")["title"] != "mutated"

    def test_all_catalogue_presets_are_findable(self):
        all_presets = get_all_presets()
        for p in all_presets:
            found = get_preset(p["name"])
            assert found is not None, f"get_preset('{p['name']}') returned None"
            assert found["name"] == p["name"]
