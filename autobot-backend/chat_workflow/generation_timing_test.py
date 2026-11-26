# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The final chunk's timings are logged per iteration, in seconds (#22254)."""

import logging

import pytest

from autobot_shared import verifier_deadline
from chat_workflow.generation_timing import generation_timing, log_generation_timing


@pytest.fixture(autouse=True)
def _fresh_rates():
    verifier_deadline.clear_generation_rates()
    yield
    verifier_deadline.clear_generation_rates()


FINAL = {
    "done": True,
    "total_duration": 240_000_000_000,
    "load_duration": 30_000_000_000,
    "prompt_eval_count": 900,
    "prompt_eval_duration": 20_000_000_000,
    "eval_count": 400,
    "eval_duration": 190_000_000_000,
}


def test_durations_are_converted_to_seconds():
    t = generation_timing(FINAL)
    assert t["total_duration"] == 240.0 and t["load_duration"] == 30.0 and t["eval_count"] == 400.0


def test_a_chunk_without_timings_logs_nothing(caplog):
    with caplog.at_level(logging.INFO):
        log_generation_timing({"done": True}, "m")
        log_generation_timing({"response": "x", "done": False, "eval_count": 1}, "m")
    assert "[iteration_timing]" not in caplog.text


def test_the_final_chunk_is_logged_with_the_split(caplog):
    with caplog.at_level(logging.INFO):
        log_generation_timing(FINAL, "qwen")
    assert (
        "[iteration_timing]" in caplog.text
        and "load=30.0s" in caplog.text
        and "generation=400 tok/190.0s" in caplog.text
    )


def test_a_finished_generation_records_its_rate_for_the_verifier_deadline():
    log_generation_timing(FINAL, "m")  # 400 tokens in 190 s
    assert verifier_deadline.recent_tokens_per_second("m") == pytest.approx(400 / 190)
