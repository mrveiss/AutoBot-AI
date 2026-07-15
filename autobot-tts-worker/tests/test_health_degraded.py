# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for TTS worker /health degraded-engine reporting (issue #11718).

These tests exercise the degraded-state helper copied from tts-worker.py.j2
in isolation, without loading torch or pocket_tts. The template is not
directly importable, so the helper is re-implemented here to match its
signature exactly — changes to the template must be reflected here.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Inline the helper under test (mirrors tts-worker.py.j2 exactly)
# ---------------------------------------------------------------------------

_GATED_MODEL_PREFIXES = (
    "meta-llama/",
    "mistralai/",
    "liquid-ai/",
    "stabilityai/",
)


def _is_gated_model(model_id: str) -> bool:
    return any(model_id.startswith(prefix) for prefix in _GATED_MODEL_PREFIXES)


class _WorkerState:
    """Stand-in for the module-level globals in tts-worker.py.j2."""

    def __init__(
        self,
        tts_model_id: str,
        hf_auth_ok: bool = True,
        hf_auth_error: Optional[str] = None,
        voice_cloning_loaded: bool = True,
    ):
        self.tts_model_id = tts_model_id
        self.hf_auth_ok = hf_auth_ok
        self.hf_auth_error = hf_auth_error
        self.voice_cloning_loaded = voice_cloning_loaded


def _compute_degraded_state(state: _WorkerState) -> tuple[bool, Optional[str]]:
    """Mirrors _compute_degraded_state() in tts-worker.py.j2."""
    if not state.hf_auth_ok:
        return True, f"HuggingFace authentication failed: {state.hf_auth_error}"
    if _is_gated_model(state.tts_model_id) and not state.voice_cloning_loaded:
        return True, (
            f"Configured model '{state.tts_model_id}' requires gated voice-cloning "
            "weights, but the worker fell back to the public model."
        )
    return False, None


# ---------------------------------------------------------------------------
# Tests: healthy, non-degraded states
# ---------------------------------------------------------------------------


class TestNotDegraded:
    def test_public_model_hf_ok_not_degraded(self):
        state = _WorkerState(tts_model_id="facebook/mms-tts-eng", hf_auth_ok=True)
        degraded, reason = _compute_degraded_state(state)
        assert degraded is False
        assert reason is None

    def test_gated_model_voice_cloning_loaded_not_degraded(self):
        state = _WorkerState(
            tts_model_id="liquid-ai/kani-tts-2",
            hf_auth_ok=True,
            voice_cloning_loaded=True,
        )
        degraded, reason = _compute_degraded_state(state)
        assert degraded is False
        assert reason is None


# ---------------------------------------------------------------------------
# Tests: HF auth failure -> degraded
# ---------------------------------------------------------------------------


class TestDegradedOnAuthFailure:
    def test_auth_failed_is_degraded(self):
        state = _WorkerState(
            tts_model_id="liquid-ai/kani-tts-2",
            hf_auth_ok=False,
            hf_auth_error="Invalid user token",
        )
        degraded, reason = _compute_degraded_state(state)
        assert degraded is True
        assert "Invalid user token" in reason

    def test_auth_failed_reason_mentions_hf(self):
        state = _WorkerState(tts_model_id="mistralai/Mistral-7B-v0.1", hf_auth_ok=False, hf_auth_error="401")
        _, reason = _compute_degraded_state(state)
        assert "HuggingFace authentication failed" in reason


# ---------------------------------------------------------------------------
# Tests: gated model fell back to public weights -> degraded
# ---------------------------------------------------------------------------


class TestDegradedOnVoiceCloningFallback:
    def test_gated_model_fallback_is_degraded(self):
        state = _WorkerState(
            tts_model_id="liquid-ai/kani-tts-2",
            hf_auth_ok=True,
            voice_cloning_loaded=False,
        )
        degraded, reason = _compute_degraded_state(state)
        assert degraded is True
        assert "liquid-ai/kani-tts-2" in reason
        assert "fell back" in reason

    def test_public_model_fallback_not_degraded(self):
        # has_voice_cloning False on a public (non-gated) model is not a
        # degraded state — gating never applied in the first place.
        state = _WorkerState(
            tts_model_id="facebook/mms-tts-eng",
            hf_auth_ok=True,
            voice_cloning_loaded=False,
        )
        degraded, reason = _compute_degraded_state(state)
        assert degraded is False
        assert reason is None


# ---------------------------------------------------------------------------
# Tests: auth failure takes precedence over voice-cloning check
# ---------------------------------------------------------------------------


class TestAuthFailurePrecedence:
    def test_auth_failure_reason_wins_over_fallback_reason(self):
        state = _WorkerState(
            tts_model_id="liquid-ai/kani-tts-2",
            hf_auth_ok=False,
            hf_auth_error="401 Unauthorized",
            voice_cloning_loaded=False,
        )
        degraded, reason = _compute_degraded_state(state)
        assert degraded is True
        assert "HuggingFace authentication failed" in reason
