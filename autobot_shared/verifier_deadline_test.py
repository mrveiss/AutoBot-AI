# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The verifier's deadline follows the model's measured speed, within the configured bounds (#22254)."""

import pytest

from autobot_shared import verifier_deadline as vd
from autobot_shared.verifier_degradation import VerifierDegradation, failure_observation


@pytest.fixture(autouse=True)
def _fresh_rates():
    vd.clear_generation_rates()
    yield
    vd.clear_generation_rates()


def test_no_measured_rate_keeps_the_configured_deadline():
    assert vd.verifier_deadline_s("m", 512, 10.0, 600.0, explicit=False) == 10.0


def test_a_slow_model_gets_the_time_its_reply_needs_with_headroom():
    vd.note_generation_rate("m", 20.0)  # 512 tokens at 20 tok/s = 25.6 s; x2 headroom
    assert vd.verifier_deadline_s("m", 512, 10.0, 600.0, explicit=False) == pytest.approx(51.2)


def test_a_fast_model_never_drops_below_the_floor():
    vd.note_generation_rate("m", 5000.0)
    assert vd.verifier_deadline_s("m", 512, 10.0, 600.0, explicit=False) == 10.0


def test_the_ceiling_bounds_a_very_slow_model():
    vd.note_generation_rate("m", 2.1)  # the 2 tok/s local model of the report
    assert vd.verifier_deadline_s("m", 512, 10.0, 90.0, explicit=False) == 90.0


def test_an_explicit_env_value_wins_over_the_measured_rate(monkeypatch):
    vd.note_generation_rate("m", 2.1)
    monkeypatch.setenv("VERIFIER_TIMEOUT_S", "7")
    assert vd.verifier_deadline_s("m", 512, 7.0, 90.0) == 7.0


def test_a_stale_rate_is_not_used(monkeypatch):
    vd.note_generation_rate("m", 2.1)
    real = vd.time.monotonic()
    monkeypatch.setattr(vd.time, "monotonic", lambda: real + vd.RATE_MAX_AGE_S + 1)
    assert vd.verifier_deadline_s("m", 512, 10.0, 90.0, explicit=False) == 10.0


def test_a_different_verifier_model_never_borrows_the_chat_models_rate():
    vd.note_generation_rate("chat-model", 20.0)
    assert vd.verifier_deadline_s("other", 512, 10.0, 600.0, explicit=False) == 10.0  # its own rate, else the floor


def test_the_chat_models_rate_stands_in_only_when_the_verifier_reuses_the_chat_model(monkeypatch):
    from contextvars import ContextVar

    from autobot_shared import chat_model_context

    monkeypatch.setattr(chat_model_context, "_last_turn_model", ContextVar("t", default="chat-model"))
    vd.note_generation_rate("chat-model", 20.0)
    assert vd.verifier_deadline_s("chat-model:latest", 512, 10.0, 600.0, explicit=False, reuses_chat=True) == (
        pytest.approx(51.2)
    )
    assert vd.verifier_deadline_s("chat-model:latest", 512, 10.0, 600.0, explicit=False) == 10.0


def test_the_verifier_models_own_rate_wins_even_when_reusing_chat():
    vd.note_generation_rate("v", 40.0)
    vd.note_generation_rate("chat-model", 5.0)
    assert vd.recent_tokens_per_second("v", reuses_chat=True) == 40.0


def test_headroom_and_rate_age_are_registered_env_constants():
    from autobot_shared.env_registry import REGISTRY

    assert REGISTRY["AUTOBOT_VERIFIER_HEADROOM_FACTOR"].default == vd.HEADROOM_FACTOR == 2.0
    assert REGISTRY["AUTOBOT_VERIFIER_RATE_MAX_AGE_S"].default == vd.RATE_MAX_AGE_S == 900.0


def test_a_timeout_names_the_deadline_it_hit():
    observation = failure_observation(TimeoutError(), 51.2)
    assert observation.degradation is VerifierDegradation.TIMEOUT
    assert "51.2s" in observation.rationale


def test_the_default_ceiling_fits_a_two_token_per_second_model(monkeypatch):
    monkeypatch.delenv("AUTOBOT_VERIFIER_TIMEOUT_MAX_S", raising=False)
    vd.note_generation_rate("m", 2.0)  # 512 tokens at 2 tok/s = 256 s; x2 headroom = 512 s
    assert vd.verifier_deadline_s("m", 512, 10.0, explicit=False) == pytest.approx(512.0)


def test_the_ceiling_env_var_bounds_the_scaled_deadline(monkeypatch):
    monkeypatch.setenv("AUTOBOT_VERIFIER_TIMEOUT_MAX_S", "120")
    vd.note_generation_rate("m", 2.0)
    assert vd.verifier_deadline_s("m", 512, 10.0, explicit=False) == 120.0
