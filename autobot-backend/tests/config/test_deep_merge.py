# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for deep_merge depth-limit guard in config/loader.py (#3931)."""

import pytest

from config.loader import deep_merge


class TestDeepMergeDepthLimit:
    """Verify deep_merge raises ValueError when nesting exceeds max_depth."""

    def test_flat_merge_succeeds(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge_within_limit_succeeds(self):
        base = {"level1": {"level2": {"level3": {"value": "base"}}}}
        override = {"level1": {"level2": {"level3": {"value": "override"}}}}
        result = deep_merge(base, override)
        assert result["level1"]["level2"]["level3"]["value"] == "override"

    def test_override_takes_precedence_over_base(self):
        base = {"key": "base_value", "shared": {"x": 1, "y": 2}}
        override = {"key": "override_value", "shared": {"y": 99}}
        result = deep_merge(base, override)
        assert result["key"] == "override_value"
        assert result["shared"]["x"] == 1
        assert result["shared"]["y"] == 99

    def test_non_dict_override_replaces_dict_in_base(self):
        base = {"key": {"nested": "value"}}
        override = {"key": "flat_value"}
        result = deep_merge(base, override)
        assert result["key"] == "flat_value"

    def test_depth_exceeded_raises_value_error(self):
        """A payload exceeding max_depth must raise ValueError — DoS guard (#3931)."""

        def make_nested(depth: int) -> dict:
            result: dict = {"leaf": True}
            for _ in range(depth):
                result = {"child": result}
            return result

        bomb = make_nested(12)
        with pytest.raises(ValueError, match="nesting depth exceeds maximum"):
            deep_merge({}, bomb, max_depth=10)

    def test_custom_max_depth_respected(self):
        """Callers can tighten the depth limit."""

        def make_nested(depth: int) -> dict:
            result: dict = {"leaf": True}
            for _ in range(depth):
                result = {"child": result}
            return result

        # Exactly at limit succeeds
        deep_merge({}, make_nested(3), max_depth=3)

        # One level over raises
        with pytest.raises(ValueError):
            deep_merge({}, make_nested(4), max_depth=3)

    def test_base_keys_not_in_override_are_preserved(self):
        base = {"a": 1, "b": {"x": 10, "y": 20}}
        override = {"b": {"x": 99}}
        result = deep_merge(base, override)
        assert result["a"] == 1
        assert result["b"]["x"] == 99
        assert result["b"]["y"] == 20

    def test_empty_override_returns_base_copy(self):
        base = {"a": 1, "b": {"c": 2}}
        result = deep_merge(base, {})
        assert result == base
        assert result is not base

    def test_empty_base_returns_override_copy(self):
        override = {"a": 1, "b": {"c": 2}}
        result = deep_merge({}, override)
        assert result == override
