# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``POST /api/wake_word/check`` tested through the route itself (#16247).

``services/wake_word_detection_test.py::TestMatchTextHasNoSideEffects`` proves
that ``match_text`` is side-effect free, but it calls ``match_text`` directly.
If the route were pointed back at the stateful ``check_text_for_wake_word``,
those tests would still pass. These tests go through the route instead, and
check two things:

- the shared detector's cooldown and stats are untouched after ``/check``;
- the response discloses only the verdict and the confidence, per the owner
  ruling on #16247.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.wake_word import router
from services.wake_word_service import get_wake_word_detector, reset_wake_word_detector

_MATCHING = "hey autobot"  # one of WakeWordConfig's default wake words


@pytest.fixture
def detector():
    """A fresh process-wide detector, the one the route uses, reset again afterwards."""
    reset_wake_word_detector()
    yield get_wake_word_detector()
    reset_wake_word_detector()


def _check(text: str):
    app = FastAPI()
    app.include_router(router, prefix="/api/wake_word")
    return TestClient(app).post("/api/wake_word/check", json={"text": text})


def _state(detector) -> tuple:
    """Everything a /check call must not change."""
    return dict(vars(detector.stats)), detector._cooldown_end_time


def test_check_discloses_only_the_verdict_and_the_confidence(detector):
    response = _check(_MATCHING)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"detected", "confidence"}, f"/check disclosed more than the ruling allows: {sorted(body)}"
    assert body["detected"] is True


def test_a_non_matching_check_has_the_same_shape(detector):
    body = _check("good morning").json()
    assert set(body) == {"detected", "confidence"}
    assert body["detected"] is False


def test_check_leaves_the_shared_detector_untouched(detector):
    before = _state(detector)
    first = _check(_MATCHING).json()
    second = _check(_MATCHING).json()
    assert _state(detector) == before, "POST /check changed the shared detector's stats or cooldown"
    # No cooldown was started, so the second call still detects.
    assert first["detected"] is True and second["detected"] is True


def test_the_stateful_path_does_change_it(detector):
    """The contrast case: the comparison above can fail.

    If the route called ``check_text_for_wake_word`` instead of ``match_text``,
    the state snapshot would differ, as it does here.
    """
    before = _state(detector)
    assert detector.check_text_for_wake_word(_MATCHING) is not None
    assert _state(detector) != before
