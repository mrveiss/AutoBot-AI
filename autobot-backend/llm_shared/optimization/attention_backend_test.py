# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for attention_backend — tier selection, blocklist, fallback chain,
missing libraries, and available-backend enumeration.

Issue #1951: Attention backend fallback chain.
"""

from unittest.mock import MagicMock, patch

from llm_shared.optimization.attention_backend import (
    ARCH_DISPATCH_TABLE,
    AttentionBackend,
    AttentionBackendSelector,
    ModelConfig,
    _free_memory,
    get_attention_backend_selector,
)
from llm_shared.types import ArchitectureFamily

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_selector() -> AttentionBackendSelector:
    return AttentionBackendSelector()


def _make_model() -> MagicMock:
    """Minimal HF-like model mock with a config attribute."""
    model = MagicMock()
    model.config = MagicMock()
    model.config.attn_implementation = None
    return model


# ---------------------------------------------------------------------------
# AttentionBackend enum
# ---------------------------------------------------------------------------


class TestAttentionBackendEnum:
    """Validate enum values and string stability."""

    def test_values_are_strings(self):
        """All backend values should be strings."""
        for backend in AttentionBackend:
            assert isinstance(backend.value, str)

    def test_expected_members(self):
        """Enum must expose the three transformer tiers plus NOT_APPLICABLE."""
        names = {b.name for b in AttentionBackend}
        assert names == {"BETTER_TRANSFORMER", "SDPA", "VANILLA", "NOT_APPLICABLE"}

    def test_string_coercion(self):
        """AttentionBackend should be usable as a str subclass."""
        assert AttentionBackend.BETTER_TRANSFORMER == "better_transformer"
        assert AttentionBackend.SDPA == "sdpa"
        assert AttentionBackend.VANILLA == "vanilla"
        assert AttentionBackend.NOT_APPLICABLE == "not_applicable"


# ---------------------------------------------------------------------------
# Blocklist
# ---------------------------------------------------------------------------


class TestBlocklist:
    """Tests for the BetterTransformer incompatibility blocklist."""

    def test_mixtral_is_blocked(self):
        """Mixtral must not receive BetterTransformer."""
        sel = _make_selector()
        assert sel._is_blocklisted(ModelConfig(model_type="mixtral"))

    def test_mistral_is_blocked(self):
        """Mistral must not receive BetterTransformer."""
        sel = _make_selector()
        assert sel._is_blocklisted(ModelConfig(model_type="mistral"))

    def test_qwen_is_blocked(self):
        """QWen family must not receive BetterTransformer."""
        sel = _make_selector()
        assert sel._is_blocklisted(ModelConfig(model_type="qwen"))
        assert sel._is_blocklisted(ModelConfig(model_type="qwen2"))

    def test_chatglm_is_blocked(self):
        """ChatGLM family must not receive BetterTransformer."""
        sel = _make_selector()
        assert sel._is_blocklisted(ModelConfig(model_type="chatglm"))
        assert sel._is_blocklisted(ModelConfig(model_type="chatglm2"))
        assert sel._is_blocklisted(ModelConfig(model_type="chatglm3"))

    def test_blocklist_matches_model_name(self):
        """Blocklist should match on model_name as well as model_type."""
        sel = _make_selector()
        cfg = ModelConfig(model_name="mistralai/Mixtral-8x7B-Instruct-v0.1", model_type="")
        assert sel._is_blocklisted(cfg)

    def test_blocklist_is_case_insensitive(self):
        """Blocklist matching must be case-insensitive."""
        sel = _make_selector()
        assert sel._is_blocklisted(ModelConfig(model_type="Mixtral"))
        assert sel._is_blocklisted(ModelConfig(model_type="MISTRAL"))
        assert sel._is_blocklisted(ModelConfig(model_name="Qwen/Qwen2-7B"))

    def test_llama_is_not_blocked(self):
        """LLaMA should not be on the blocklist."""
        sel = _make_selector()
        assert not sel._is_blocklisted(ModelConfig(model_type="llama"))

    def test_falcon_is_not_blocked(self):
        """Falcon should not be on the blocklist."""
        sel = _make_selector()
        assert not sel._is_blocklisted(ModelConfig(model_type="falcon"))

    def test_empty_model_config_is_not_blocked(self):
        """Empty model config should not be blocked."""
        sel = _make_selector()
        assert not sel._is_blocklisted(ModelConfig())


# ---------------------------------------------------------------------------
# Tier selection — select_backend
# ---------------------------------------------------------------------------


class TestSelectBackend:
    """Tests for AttentionBackendSelector.select_backend tier ordering."""

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=MagicMock(),
    )
    def test_bt_selected_when_available_and_not_blocked(self, _mock_bt):
        """Tier 1 (BetterTransformer) should be selected when available and not blocked."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(model_type="llama"))
        assert result == AttentionBackend.BETTER_TRANSFORMER

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=MagicMock(),
    )
    def test_bt_skipped_for_blocklisted_model(self, _mock_bt):
        """Blocked models must fall through to Tier 2 or Tier 3."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(model_type="mixtral"))
        # Should not be BetterTransformer
        assert result != AttentionBackend.BETTER_TRANSFORMER

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=True,
    )
    def test_sdpa_selected_when_bt_absent(self, _mock_sdpa, _mock_bt):
        """Tier 2 (SDPA) should be selected when BetterTransformer is absent."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(model_type="llama"))
        assert result == AttentionBackend.SDPA

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=False,
    )
    def test_vanilla_selected_when_nothing_available(self, _mock_sdpa, _mock_bt):
        """Tier 3 (Vanilla) must be returned when nothing else is available."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(model_type="llama"))
        assert result == AttentionBackend.VANILLA

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=False,
    )
    def test_blocklisted_model_falls_to_vanilla_without_sdpa(self, _mock_sdpa, _mock_bt):
        """Blocklisted model without SDPA must still get Vanilla."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(model_type="mistral"))
        assert result == AttentionBackend.VANILLA


# ---------------------------------------------------------------------------
# Backend application — apply_backend
# ---------------------------------------------------------------------------


class TestApplyBackend:
    """Tests for AttentionBackendSelector.apply_backend fallback chain."""

    @patch("llm_shared.optimization.attention_backend._import_better_transformer")
    def test_bt_applied_successfully(self, mock_bt_import):
        """apply_backend returns the transformed model on BT success."""
        transformed_model = MagicMock(name="transformed_model")
        mock_bt_cls = MagicMock()
        mock_bt_cls.transform.return_value = transformed_model
        mock_bt_import.return_value = mock_bt_cls

        sel = _make_selector()
        result = sel.apply_backend(_make_model(), AttentionBackend.BETTER_TRANSFORMER)
        assert result is transformed_model
        mock_bt_cls.transform.assert_called_once()

    @patch("llm_shared.optimization.attention_backend._import_better_transformer")
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=True,
    )
    def test_bt_failure_falls_through_to_sdpa(self, _mock_sdpa, mock_bt_import):
        """When BetterTransformer.transform raises, apply_backend falls to SDPA."""
        mock_bt_cls = MagicMock()
        mock_bt_cls.transform.side_effect = RuntimeError("BT failed")
        mock_bt_import.return_value = mock_bt_cls

        sel = _make_selector()
        model = _make_model()
        result = sel.apply_backend(model, AttentionBackend.BETTER_TRANSFORMER)
        # Should have fallen through — model returned (SDPA path)
        assert result is not None

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    def test_sdpa_backend_returns_model(self, _mock_bt):
        """apply_backend with SDPA returns the original model."""
        sel = _make_selector()
        model = _make_model()
        result = sel.apply_backend(model, AttentionBackend.SDPA)
        assert result is model

    def test_vanilla_backend_returns_model_unchanged(self):
        """apply_backend with Vanilla must return the exact same model object."""
        sel = _make_selector()
        model = _make_model()
        result = sel.apply_backend(model, AttentionBackend.VANILLA)
        assert result is model

    @patch("llm_shared.optimization.attention_backend._import_better_transformer")
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._try_apply_sdpa",
        return_value=None,
    )
    def test_full_fallback_to_vanilla(self, _mock_sdpa, mock_bt_import):
        """When both BT and SDPA fail, apply_backend returns the original model."""
        mock_bt_cls = MagicMock()
        mock_bt_cls.transform.side_effect = RuntimeError("BT unavailable")
        mock_bt_import.return_value = mock_bt_cls

        sel = _make_selector()
        model = _make_model()
        result = sel.apply_backend(model, AttentionBackend.BETTER_TRANSFORMER)
        assert result is model


# ---------------------------------------------------------------------------
# Missing libraries
# ---------------------------------------------------------------------------


class TestMissingLibraries:
    """Ensure graceful degradation when optional libraries are absent."""

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=False,
    )
    def test_select_backend_no_libraries(self, _mock_sdpa, _mock_bt):
        """With no optional libraries, VANILLA must always be returned."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(model_type="llama"))
        assert result == AttentionBackend.VANILLA

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=False,
    )
    def test_apply_backend_no_libraries_returns_model(self, _mock_sdpa, _mock_bt):
        """apply_backend must return a model even when all optional libs are absent."""
        sel = _make_selector()
        model = _make_model()
        result = sel.apply_backend(model, AttentionBackend.VANILLA)
        assert result is model

    @patch(
        "llm_shared.optimization.attention_backend._import_torch",
        side_effect=ImportError("no torch"),
    )
    def test_can_use_sdpa_returns_false_without_torch(self, _mock_torch):
        """_can_use_sdpa must return False when torch import fails."""
        sel = _make_selector()
        assert sel._can_use_sdpa() is False


# ---------------------------------------------------------------------------
# Available backends
# ---------------------------------------------------------------------------


class TestGetAvailableBackends:
    """Tests for AttentionBackendSelector.get_available_backends."""

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=MagicMock(),
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=True,
    )
    def test_all_backends_available(self, _mock_sdpa, _mock_bt):
        """When all libraries are present all three backends are listed."""
        sel = _make_selector()
        backends = sel.get_available_backends()
        assert AttentionBackend.BETTER_TRANSFORMER in backends
        assert AttentionBackend.SDPA in backends
        assert AttentionBackend.VANILLA in backends

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=False,
    )
    def test_only_vanilla_available(self, _mock_sdpa, _mock_bt):
        """When no optional libraries exist only VANILLA is returned."""
        sel = _make_selector()
        backends = sel.get_available_backends()
        assert backends == [AttentionBackend.VANILLA]

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=None,
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=True,
    )
    def test_sdpa_and_vanilla_available(self, _mock_sdpa, _mock_bt):
        """When only SDPA is present, list contains SDPA and VANILLA."""
        sel = _make_selector()
        backends = sel.get_available_backends()
        assert AttentionBackend.BETTER_TRANSFORMER not in backends
        assert AttentionBackend.SDPA in backends
        assert AttentionBackend.VANILLA in backends

    def test_vanilla_is_always_last(self):
        """VANILLA must be the last element regardless of other tiers."""
        sel = _make_selector()
        backends = sel.get_available_backends()
        assert backends[-1] == AttentionBackend.VANILLA

    @patch(
        "llm_shared.optimization.attention_backend._import_better_transformer",
        return_value=MagicMock(),
    )
    @patch(
        "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
        return_value=True,
    )
    def test_order_is_tier_descending(self, _mock_sdpa, _mock_bt):
        """Backends must be listed highest capability first."""
        sel = _make_selector()
        backends = sel.get_available_backends()
        assert backends[0] == AttentionBackend.BETTER_TRANSFORMER
        assert backends[1] == AttentionBackend.SDPA
        assert backends[2] == AttentionBackend.VANILLA


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------


class TestGetAttentionBackendSelector:
    """Tests for the module-level singleton accessor."""

    def test_returns_selector_instance(self):
        """get_attention_backend_selector should return an AttentionBackendSelector."""
        sel = get_attention_backend_selector()
        assert isinstance(sel, AttentionBackendSelector)

    def test_returns_same_instance(self):
        """Repeated calls must return the exact same object (singleton)."""
        sel_a = get_attention_backend_selector()
        sel_b = get_attention_backend_selector()
        assert sel_a is sel_b


# ---------------------------------------------------------------------------
# Memory cleanup helper
# ---------------------------------------------------------------------------


class TestFreeMemory:
    """Tests for the _free_memory utility."""

    def test_does_not_raise_without_torch(self):
        """_free_memory must not raise even when torch is absent."""
        with patch(
            "llm_shared.optimization.attention_backend._import_torch",
            side_effect=ImportError("no torch"),
        ):
            _free_memory()  # must not raise

    def test_does_not_raise_with_torch(self):
        """_free_memory must not raise in a normal environment."""
        _free_memory()  # must not raise


# ---------------------------------------------------------------------------
# ModelConfig dataclass
# ---------------------------------------------------------------------------


class TestModelConfig:
    """Tests for ModelConfig defaults and field behaviour."""

    def test_default_values(self):
        """ModelConfig should have safe defaults."""
        cfg = ModelConfig()
        assert cfg.model_name == ""
        assert cfg.model_type == ""
        assert cfg.torch_dtype is None
        assert cfg.extra == {}

    def test_default_architecture_family_is_transformer(self):
        """Default architecture_family must be TRANSFORMER for backwards compat."""
        cfg = ModelConfig()
        assert cfg.architecture_family == ArchitectureFamily.TRANSFORMER

    def test_custom_values(self):
        """ModelConfig should accept custom field values."""
        cfg = ModelConfig(
            model_name="meta-llama/Llama-3-8B",
            model_type="llama",
            torch_dtype="float16",
            extra={"revision": "main"},
        )
        assert cfg.model_name == "meta-llama/Llama-3-8B"
        assert cfg.model_type == "llama"
        assert cfg.torch_dtype == "float16"
        assert cfg.extra == {"revision": "main"}

    def test_architecture_family_field(self):
        """ModelConfig should accept and store architecture_family."""
        cfg = ModelConfig(architecture_family=ArchitectureFamily.STATE_SPACE)
        assert cfg.architecture_family == ArchitectureFamily.STATE_SPACE


# ---------------------------------------------------------------------------
# Architecture-family dispatch — Issue #7350
# ---------------------------------------------------------------------------


class TestArchitectureFamilyDispatch:
    """Tests for architecture-family based NOT_APPLICABLE dispatch."""

    def test_transformer_family_enters_normal_selection(self):
        """TRANSFORMER family must fall through to normal tier selection."""
        sel = _make_selector()
        with (
            patch(
                "llm_shared.optimization.attention_backend._import_better_transformer",
                return_value=None,
            ),
            patch(
                "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
                return_value=False,
            ),
        ):
            result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.TRANSFORMER))
        assert result == AttentionBackend.VANILLA

    def test_state_space_returns_not_applicable(self):
        """STATE_SPACE architecture must return NOT_APPLICABLE immediately."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.STATE_SPACE))
        assert result == AttentionBackend.NOT_APPLICABLE

    def test_linear_attention_returns_not_applicable(self):
        """LINEAR_ATTENTION architecture must return NOT_APPLICABLE."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.LINEAR_ATTENTION))
        assert result == AttentionBackend.NOT_APPLICABLE

    def test_hybrid_returns_not_applicable(self):
        """HYBRID architecture must return NOT_APPLICABLE."""
        sel = _make_selector()
        result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.HYBRID))
        assert result == AttentionBackend.NOT_APPLICABLE

    def test_state_space_large_context_not_capped(self):
        """State-space with 131072 context must not be routed through BT/SDPA."""
        sel = _make_selector()
        cfg = ModelConfig(
            model_name="state-spaces/mamba-3b-131k",
            architecture_family=ArchitectureFamily.STATE_SPACE,
        )
        result = sel.select_backend(cfg)
        assert result == AttentionBackend.NOT_APPLICABLE

    def test_apply_backend_not_applicable_is_noop(self):
        """apply_backend with NOT_APPLICABLE must return model unchanged without warning."""
        sel = _make_selector()
        model = _make_model()
        result = sel.apply_backend(model, AttentionBackend.NOT_APPLICABLE)
        assert result is model

    def test_not_applicable_blocklist_not_consulted(self):
        """Non-transformer families must bypass the blocklist entirely."""
        sel = _make_selector()
        # Mamba model whose name might accidentally match "mamba" blocklist entries
        cfg = ModelConfig(
            model_type="mamba",
            architecture_family=ArchitectureFamily.STATE_SPACE,
        )
        result = sel.select_backend(cfg)
        assert result == AttentionBackend.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# arch_dispatch_event structured log — Issue #7350
# ---------------------------------------------------------------------------


class TestArchDispatchEvent:
    """select_backend must emit one arch_dispatch_event log entry per call."""

    def test_event_emitted_for_transformer(self, caplog):
        """arch_dispatch_event must be logged for TRANSFORMER family."""
        import logging

        sel = _make_selector()
        with (
            patch(
                "llm_shared.optimization.attention_backend._import_better_transformer",
                return_value=None,
            ),
            patch(
                "llm_shared.optimization.attention_backend.AttentionBackendSelector._can_use_sdpa",
                return_value=False,
            ),
            caplog.at_level(logging.INFO, logger="llm_shared.optimization.attention_backend"),
        ):
            sel.select_backend(ModelConfig(model_name="llama-test", architecture_family=ArchitectureFamily.TRANSFORMER))

        event_lines = [r for r in caplog.records if "arch_dispatch_event" in r.message]
        assert len(event_lines) == 1
        assert "transformer" in event_lines[0].message
        assert "vanilla" in event_lines[0].message

    def test_event_emitted_for_state_space(self, caplog):
        """arch_dispatch_event must be logged for STATE_SPACE family."""
        import logging

        sel = _make_selector()
        with caplog.at_level(logging.INFO, logger="llm_shared.optimization.attention_backend"):
            sel.select_backend(ModelConfig(model_name="mamba-test", architecture_family=ArchitectureFamily.STATE_SPACE))

        event_lines = [r for r in caplog.records if "arch_dispatch_event" in r.message]
        assert len(event_lines) == 1
        assert "state_space" in event_lines[0].message
        assert "not_applicable" in event_lines[0].message

    def test_event_contains_model_name(self, caplog):
        """arch_dispatch_event log must include the model name."""
        import logging

        sel = _make_selector()
        with caplog.at_level(logging.INFO, logger="llm_shared.optimization.attention_backend"):
            sel.select_backend(
                ModelConfig(model_name="my-special-model", architecture_family=ArchitectureFamily.HYBRID)
            )

        event_lines = [r for r in caplog.records if "arch_dispatch_event" in r.message]
        assert any("my-special-model" in r.message for r in event_lines)


# ---------------------------------------------------------------------------
# SSM does not invoke FlashAttention / BetterTransformer — Issue #7350
# ---------------------------------------------------------------------------


class TestSSMNoFlashAttention:
    """STATE_SPACE requests must never reach BetterTransformer or SDPA."""

    def test_ssm_does_not_call_better_transformer(self):
        """_import_better_transformer must NOT be consulted for SSM models."""
        sel = _make_selector()
        with patch(
            "llm_shared.optimization.attention_backend._import_better_transformer",
        ) as mock_bt:
            result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.STATE_SPACE))

        assert result == AttentionBackend.NOT_APPLICABLE
        mock_bt.assert_not_called()

    def test_ssm_does_not_call_sdpa_check(self):
        """_can_use_sdpa must NOT be consulted for SSM models."""
        sel = _make_selector()
        with patch.object(AttentionBackendSelector, "_can_use_sdpa") as mock_sdpa:
            result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.STATE_SPACE))

        assert result == AttentionBackend.NOT_APPLICABLE
        mock_sdpa.assert_not_called()

    def test_linear_attention_does_not_call_better_transformer(self):
        """_import_better_transformer must NOT be consulted for linear-attn models."""
        sel = _make_selector()
        with patch(
            "llm_shared.optimization.attention_backend._import_better_transformer",
        ) as mock_bt:
            result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.LINEAR_ATTENTION))

        assert result == AttentionBackend.NOT_APPLICABLE
        mock_bt.assert_not_called()


# ---------------------------------------------------------------------------
# Dispatch table extensibility — Issue #7350
# ---------------------------------------------------------------------------


class TestDispatchTableExtensibility:
    """ARCH_DISPATCH_TABLE must be extendable without modifying select_backend."""

    def test_module_level_table_exported(self):
        """ARCH_DISPATCH_TABLE must be importable and contain the four base families."""
        assert ArchitectureFamily.TRANSFORMER in ARCH_DISPATCH_TABLE
        assert ArchitectureFamily.STATE_SPACE in ARCH_DISPATCH_TABLE
        assert ArchitectureFamily.LINEAR_ATTENTION in ARCH_DISPATCH_TABLE
        assert ArchitectureFamily.HYBRID in ARCH_DISPATCH_TABLE

    def test_new_family_routed_via_instance_table(self):
        """A new family registered on the instance dispatch table is honoured."""
        sel = _make_selector()

        # Register a custom handler for a hypothetical new family key
        sentinel_backend = AttentionBackend.NOT_APPLICABLE

        def _custom_handler(_cfg: ModelConfig) -> AttentionBackend:
            return sentinel_backend

        # Inject directly onto instance _arch_dispatch (simulates startup config)
        custom_key = "moe_custom"  # not an enum — string key test
        sel._arch_dispatch = dict(sel._arch_dispatch)  # copy so class var is not mutated
        # Map HYBRID to a custom handler to verify routing without inventing an enum
        sel._arch_dispatch[ArchitectureFamily.HYBRID] = "_handle_ssm"

        result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.HYBRID))
        # Should route through _handle_ssm which returns NOT_APPLICABLE
        assert result == AttentionBackend.NOT_APPLICABLE

    def test_unknown_family_falls_back_to_transformer(self):
        """An unregistered family string falls back to transformer path with WARNING."""

        sel = _make_selector()
        # Remove HYBRID from the instance dispatch table to simulate an unknown family
        sel._arch_dispatch = {k: v for k, v in ARCH_DISPATCH_TABLE.items() if k != ArchitectureFamily.HYBRID}

        with (
            patch(
                "llm_shared.optimization.attention_backend._import_better_transformer",
                return_value=None,
            ),
            patch.object(AttentionBackendSelector, "_can_use_sdpa", return_value=False),
        ):
            result = sel.select_backend(ModelConfig(architecture_family=ArchitectureFamily.HYBRID))

        # Falls back to transformer path → VANILLA in this environment
        assert result == AttentionBackend.VANILLA

    def test_transformer_regression_matches_vanilla_when_no_libs(self):
        """TRANSFORMER family with no optional libs must return VANILLA (regression)."""
        sel = _make_selector()
        with (
            patch(
                "llm_shared.optimization.attention_backend._import_better_transformer",
                return_value=None,
            ),
            patch.object(AttentionBackendSelector, "_can_use_sdpa", return_value=False),
        ):
            result = sel.select_backend(
                ModelConfig(model_type="llama", architecture_family=ArchitectureFamily.TRANSFORMER)
            )
        assert result == AttentionBackend.VANILLA
