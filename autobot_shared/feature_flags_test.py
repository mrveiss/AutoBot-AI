#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit Tests for Feature Flag Utilities
======================================

Tests env-var reading, defaults, decorator behaviour, and feature listing.

Issue: #3017 — No feature flag system for optional subsystems
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_feature_config(**overrides):
    """Return a new FeatureConfig instance with isolated env."""
    from autobot_shared.ssot_config import FeatureConfig

    with patch.dict(os.environ, overrides, clear=True):
        return FeatureConfig(_env_file=None)


# ---------------------------------------------------------------------------
# FeatureConfig subsystem defaults
# ---------------------------------------------------------------------------


class TestFeatureConfigSubsystemDefaults:
    """All subsystem flags default to True when no env var is set."""

    def test_npu_enabled_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.npu_enabled is True

    def test_voice_enabled_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.voice_enabled is True

    def test_browser_enabled_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.browser_enabled is True

    def test_computer_vision_enabled_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.computer_vision_enabled is True

    def test_training_enabled_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.training_enabled is True

    def test_osint_enabled_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.osint_enabled is True


# ---------------------------------------------------------------------------
# FeatureConfig env-var overrides
# ---------------------------------------------------------------------------


class TestFeatureConfigEnvVarOverrides:
    """Subsystem flags can be toggled via AUTOBOT_FEATURE_* env vars."""

    def test_npu_disabled_via_env(self) -> None:
        cfg = _fresh_feature_config(AUTOBOT_FEATURE_NPU="false")
        assert cfg.npu_enabled is False

    def test_voice_disabled_via_env(self) -> None:
        cfg = _fresh_feature_config(AUTOBOT_FEATURE_VOICE="false")
        assert cfg.voice_enabled is False

    def test_browser_disabled_via_env(self) -> None:
        cfg = _fresh_feature_config(AUTOBOT_FEATURE_BROWSER="false")
        assert cfg.browser_enabled is False

    def test_computer_vision_disabled_via_env(self) -> None:
        cfg = _fresh_feature_config(AUTOBOT_FEATURE_COMPUTER_VISION="false")
        assert cfg.computer_vision_enabled is False

    def test_training_disabled_via_env(self) -> None:
        cfg = _fresh_feature_config(AUTOBOT_FEATURE_TRAINING="false")
        assert cfg.training_enabled is False

    def test_osint_disabled_via_env(self) -> None:
        cfg = _fresh_feature_config(AUTOBOT_FEATURE_OSINT="false")
        assert cfg.osint_enabled is False

    def test_explicit_true_still_enabled(self) -> None:
        cfg = _fresh_feature_config(AUTOBOT_FEATURE_NPU="true")
        assert cfg.npu_enabled is True


# ---------------------------------------------------------------------------
# is_feature_enabled
# ---------------------------------------------------------------------------


class TestIsFeatureEnabled:
    """is_feature_enabled reads live FeatureConfig through get_config()."""

    def _mock_feature_cfg(self, **kwargs):
        """Patch get_config().feature with controlled attribute values."""
        from unittest.mock import MagicMock

        feature_cfg = MagicMock()
        # Default all flags to True, then apply overrides.
        defaults = {
            "npu_enabled": True,
            "voice_enabled": True,
            "browser_enabled": True,
            "computer_vision_enabled": True,
            "training_enabled": True,
            "osint_enabled": True,
        }
        defaults.update(kwargs)
        for attr, val in defaults.items():
            setattr(feature_cfg, attr, val)

        mock_cfg = MagicMock()
        mock_cfg.feature = feature_cfg
        return mock_cfg

    def test_returns_true_when_flag_enabled(self) -> None:
        from autobot_shared.feature_flags import is_feature_enabled

        with patch("autobot_shared.feature_flags._get_feature_config") as mock_get:
            mock_get.return_value = self._mock_feature_cfg().feature
            assert is_feature_enabled("npu") is True

    def test_returns_false_when_flag_disabled(self) -> None:
        from autobot_shared.feature_flags import is_feature_enabled

        with patch("autobot_shared.feature_flags._get_feature_config") as mock_get:
            mock_get.return_value = self._mock_feature_cfg(npu_enabled=False).feature
            assert is_feature_enabled("npu") is False

    def test_raises_for_unknown_flag(self) -> None:
        from autobot_shared.feature_flags import is_feature_enabled

        with pytest.raises(ValueError, match="Unknown feature flag 'nonexistent'"):
            is_feature_enabled("nonexistent")

    def test_all_known_flags_accepted(self) -> None:
        from autobot_shared.feature_flags import _SUBSYSTEM_FLAG_MAP, is_feature_enabled

        with patch("autobot_shared.feature_flags._get_feature_config") as mock_get:
            mock_get.return_value = self._mock_feature_cfg().feature
            for name in _SUBSYSTEM_FLAG_MAP:
                # Should not raise
                result = is_feature_enabled(name)
                assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# get_enabled_features
# ---------------------------------------------------------------------------


class TestGetEnabledFeatures:
    """get_enabled_features returns a sorted list of enabled subsystem names."""

    def test_all_enabled_returns_all_names(self) -> None:
        from unittest.mock import MagicMock

        from autobot_shared.feature_flags import (
            _SUBSYSTEM_FLAG_MAP,
            get_enabled_features,
        )

        feature_cfg = MagicMock()
        for attr in _SUBSYSTEM_FLAG_MAP.values():
            setattr(feature_cfg, attr, True)

        with patch("autobot_shared.feature_flags._get_feature_config", return_value=feature_cfg):
            result = get_enabled_features()

        assert result == sorted(_SUBSYSTEM_FLAG_MAP.keys())

    def test_none_enabled_returns_empty_list(self) -> None:
        from unittest.mock import MagicMock

        from autobot_shared.feature_flags import (
            _SUBSYSTEM_FLAG_MAP,
            get_enabled_features,
        )

        feature_cfg = MagicMock()
        for attr in _SUBSYSTEM_FLAG_MAP.values():
            setattr(feature_cfg, attr, False)

        with patch("autobot_shared.feature_flags._get_feature_config", return_value=feature_cfg):
            result = get_enabled_features()

        assert result == []

    def test_partial_enabled_returns_subset(self) -> None:
        from unittest.mock import MagicMock

        from autobot_shared.feature_flags import (
            _SUBSYSTEM_FLAG_MAP,
            get_enabled_features,
        )

        feature_cfg = MagicMock()
        for attr in _SUBSYSTEM_FLAG_MAP.values():
            setattr(feature_cfg, attr, False)
        # Enable just npu and voice
        feature_cfg.npu_enabled = True
        feature_cfg.voice_enabled = True

        with patch("autobot_shared.feature_flags._get_feature_config", return_value=feature_cfg):
            result = get_enabled_features()

        assert result == sorted(["npu", "voice"])

    def test_result_is_sorted(self) -> None:
        from unittest.mock import MagicMock

        from autobot_shared.feature_flags import (
            _SUBSYSTEM_FLAG_MAP,
            get_enabled_features,
        )

        feature_cfg = MagicMock()
        for attr in _SUBSYSTEM_FLAG_MAP.values():
            setattr(feature_cfg, attr, True)

        with patch("autobot_shared.feature_flags._get_feature_config", return_value=feature_cfg):
            result = get_enabled_features()

        assert result == sorted(result)


# ---------------------------------------------------------------------------
# require_feature decorator
# ---------------------------------------------------------------------------


class TestRequireFeatureDecorator:
    """require_feature raises FeatureDisabledError when subsystem is off."""

    def test_decorated_function_runs_when_enabled(self):
        from autobot_shared.feature_flags import require_feature

        @require_feature("npu")
        def _do_npu():
            return "npu_result"

        with patch("autobot_shared.feature_flags.is_feature_enabled", return_value=True):
            assert _do_npu() == "npu_result"

    def test_raises_feature_disabled_error_when_off(self):
        from autobot_shared.feature_flags import FeatureDisabledError, require_feature

        @require_feature("npu")
        def _do_npu():
            return "npu_result"

        with patch("autobot_shared.feature_flags.is_feature_enabled", return_value=False):
            with pytest.raises(FeatureDisabledError) as exc_info:
                _do_npu()

        assert exc_info.value.feature_name == "npu"
        assert "npu" in str(exc_info.value).lower()

    def test_error_message_includes_env_var_hint(self) -> None:
        from autobot_shared.feature_flags import FeatureDisabledError, require_feature

        @require_feature("voice")
        def _speak() -> None:
            pass

        with patch("autobot_shared.feature_flags.is_feature_enabled", return_value=False):
            with pytest.raises(FeatureDisabledError) as exc_info:
                _speak()

        assert "AUTOBOT_FEATURE_VOICE" in str(exc_info.value)

    def test_raises_value_error_for_unknown_flag_at_decoration_time(self) -> None:
        from autobot_shared.feature_flags import require_feature

        with pytest.raises(ValueError, match="Unknown feature flag 'bad_flag'"):

            @require_feature("bad_flag")
            def _noop() -> None:
                pass

    def test_preserves_function_name_and_docstring(self) -> None:
        from autobot_shared.feature_flags import require_feature

        @require_feature("osint")
        def run_osint_sweep() -> None:
            """Perform an OSINT sweep."""

        assert run_osint_sweep.__name__ == "run_osint_sweep"
        assert run_osint_sweep.__doc__ == "Perform an OSINT sweep."

    def test_passes_args_and_kwargs_through(self):
        from autobot_shared.feature_flags import require_feature

        @require_feature("training")
        def train_model(model_id: str, epochs: int = 5) -> dict:
            return {"model": model_id, "epochs": epochs}

        with patch("autobot_shared.feature_flags.is_feature_enabled", return_value=True):
            result = train_model("gpt2", epochs=10)

        assert result == {"model": "gpt2", "epochs": 10}

    def test_feature_disabled_error_is_runtime_error(self) -> None:
        from autobot_shared.feature_flags import FeatureDisabledError

        err = FeatureDisabledError("browser")
        assert isinstance(err, RuntimeError)
        assert err.feature_name == "browser"


# ---------------------------------------------------------------------------
# FeatureConfig plan short-name fields — issue #3009
# ---------------------------------------------------------------------------


class TestFeatureConfigPlanFields:
    """Verify the short-name subsystem fields added in issue #3009."""

    def test_default_flags_exist(self) -> None:
        cfg = _fresh_feature_config()
        assert hasattr(cfg, "npu")
        assert hasattr(cfg, "voice")
        assert hasattr(cfg, "browser_automation")
        assert hasattr(cfg, "computer_vision")
        assert hasattr(cfg, "training")
        assert hasattr(cfg, "graph_rag")
        assert hasattr(cfg, "mcp")

    def test_heavy_features_off_by_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.computer_vision is False
        assert cfg.training is False

    def test_standard_features_on_by_default(self) -> None:
        cfg = _fresh_feature_config()
        assert cfg.npu is True
        assert cfg.voice is True
        assert cfg.browser_automation is True
        assert cfg.graph_rag is True
        assert cfg.mcp is True
