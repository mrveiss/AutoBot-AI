# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for HuggingFace token handling in the TTS worker (issue #3078).

These tests exercise the helper functions copied from tts-worker.py.j2 in
isolation, without loading torch or pocket_tts. The template is not directly
importable, so the helpers are re-implemented here to match their signatures
exactly — changes to the template must be reflected here.
"""

import logging
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Inline the helpers under test (mirrors tts-worker.py.j2 exactly)
# ---------------------------------------------------------------------------

_GATED_MODEL_PREFIXES = (
    "meta-llama/",
    "mistralai/",
    "liquid-ai/",
    "stabilityai/",
)

logger = logging.getLogger("tts-worker")


def _is_gated_model(model_id: str) -> bool:
    """Return True when model_id belongs to a known gated-model namespace."""
    return any(model_id.startswith(prefix) for prefix in _GATED_MODEL_PREFIXES)


def _warn_missing_token(model_id: str) -> None:
    """Log a warning when HF_TOKEN is absent for a potentially gated model."""
    if _is_gated_model(model_id):
        logger.warning(
            "HF_TOKEN is not set and model '%s' may be gated. "
            "Set the HF_TOKEN environment variable (via vault_hf_token in Ansible) "
            "to authenticate with HuggingFace Hub. "
            "Model download will fail with a 401/403 error if access is restricted.",
            model_id,
        )
    else:
        logger.info(
            "HF_TOKEN is not set. Model '%s' will be downloaded without authentication. "
            "This is fine for public models.",
            model_id,
        )


def _configure_hf_token(hf_token: str | None, model_id: str) -> None:
    """Authenticate with HuggingFace Hub using hf_token when present."""
    if hf_token:
        import huggingface_hub

        huggingface_hub.login(token=hf_token, add_to_git_credential=False)
        logger.info("HuggingFace Hub authenticated via HF_TOKEN.")
    else:
        _warn_missing_token(model_id)


# ---------------------------------------------------------------------------
# Tests: _is_gated_model
# ---------------------------------------------------------------------------


class TestIsGatedModel:
    def test_liquid_ai_is_gated(self):
        assert _is_gated_model("liquid-ai/kani-tts-2") is True

    def test_meta_llama_is_gated(self):
        assert _is_gated_model("meta-llama/Llama-3-8B") is True

    def test_mistralai_is_gated(self):
        assert _is_gated_model("mistralai/Mistral-7B-v0.1") is True

    def test_stabilityai_is_gated(self):
        assert _is_gated_model("stabilityai/stable-diffusion-xl-base-1.0") is True

    def test_public_model_not_gated(self):
        assert _is_gated_model("facebook/mms-tts-eng") is False

    def test_empty_string_not_gated(self):
        assert _is_gated_model("") is False

    def test_partial_prefix_not_gated(self):
        # "liquid-ai" without trailing slash should not match
        assert _is_gated_model("liquid-ai-clone/other-model") is False


# ---------------------------------------------------------------------------
# Tests: _configure_hf_token — token present
# ---------------------------------------------------------------------------


class TestConfigureHfTokenPresent:
    def test_calls_hub_login_with_token(self):
        mock_hub = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            _configure_hf_token("hf_testtoken123", "liquid-ai/kani-tts-2")
        mock_hub.login.assert_called_once_with(token="hf_testtoken123", add_to_git_credential=False)

    def test_logs_authenticated_message(self, caplog):
        mock_hub = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            with caplog.at_level(logging.INFO, logger="tts-worker"):
                _configure_hf_token("hf_testtoken123", "liquid-ai/kani-tts-2")
        assert "HuggingFace Hub authenticated" in caplog.text

    def test_does_not_warn_when_token_set(self, caplog):
        mock_hub = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            with caplog.at_level(logging.WARNING, logger="tts-worker"):
                _configure_hf_token("hf_testtoken123", "liquid-ai/kani-tts-2")
        assert "HF_TOKEN is not set" not in caplog.text


# ---------------------------------------------------------------------------
# Tests: _configure_hf_token — token absent, gated model
# ---------------------------------------------------------------------------


class TestConfigureHfTokenAbsentGated:
    def test_logs_warning_for_gated_model(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tts-worker"):
            _configure_hf_token(None, "liquid-ai/kani-tts-2")
        assert "HF_TOKEN is not set" in caplog.text
        assert "gated" in caplog.text
        assert "liquid-ai/kani-tts-2" in caplog.text

    def test_warning_mentions_vault_hf_token(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tts-worker"):
            _configure_hf_token(None, "meta-llama/Llama-3-8B")
        assert "vault_hf_token" in caplog.text

    def test_warning_mentions_401_403(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tts-worker"):
            _configure_hf_token(None, "mistralai/Mistral-7B-v0.1")
        assert "401/403" in caplog.text

    def test_does_not_call_hub_login_when_no_token(self):
        mock_hub = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            _configure_hf_token(None, "liquid-ai/kani-tts-2")
        mock_hub.login.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _configure_hf_token — token absent, public model
# ---------------------------------------------------------------------------


class TestConfigureHfTokenAbsentPublic:
    def test_logs_info_not_warning_for_public_model(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="tts-worker"):
            _configure_hf_token(None, "facebook/mms-tts-eng")
        # Should log at INFO, not WARNING
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not warning_records

    def test_info_message_says_fine_for_public(self, caplog):
        with caplog.at_level(logging.INFO, logger="tts-worker"):
            _configure_hf_token(None, "facebook/mms-tts-eng")
        assert "fine for public models" in caplog.text


# ---------------------------------------------------------------------------
# Tests: empty string token treated as absent
# ---------------------------------------------------------------------------


class TestEmptyTokenTreatedAsAbsent:
    def test_empty_string_triggers_warning_for_gated_model(self, caplog):
        # os.getenv returns '' when var is set but empty; falsy check must catch it
        with caplog.at_level(logging.WARNING, logger="tts-worker"):
            _configure_hf_token("", "liquid-ai/kani-tts-2")
        assert "HF_TOKEN is not set" in caplog.text

    def test_empty_string_does_not_call_login(self):
        mock_hub = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            _configure_hf_token("", "liquid-ai/kani-tts-2")
        mock_hub.login.assert_not_called()
