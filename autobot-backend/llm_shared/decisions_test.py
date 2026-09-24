# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the typed-decision seam (#17308) and its refusal to guess.

The property under test everywhere here: an unreadable or out-of-contract
answer becomes a raised :class:`DecisionError`, never a value. Every site that
migrated onto this seam (``claim_verifier``, the autoresearch scorer, the
judges) decides its own fallback in the open, and it can only do that if the
seam never hands it a plausible-looking answer that came from a parse miss.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_shared.decisions import (
    BooleanQuestion,
    Calibration,
    ChoiceQuestion,
    DecisionBackend,
    DecisionError,
    LocalModelBackend,
    ScoreQuestion,
    decide,
    get_backend,
    register_backend,
    registered_backends,
)
from llm_shared.validated_llm import Completer, ValidatedLLMError

_CHOICE = ChoiceQuestion(id="agreement", prompt="Agree?", options=["agree", "contradict", "unrelated"])
_SCORE = ScoreQuestion(id="rating", prompt="Rate it.", minimum=0.0, maximum=10.0)
_BOOL = BooleanQuestion(id="safe", prompt="Is it safe?")


class _ScriptedBackend(DecisionBackend):
    """A backend that replays fixed raw replies, recording the prompts it saw."""

    name = "scripted"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[tuple[str, str]] = []

    def completer(self, schema: dict) -> Completer:
        self.schema = schema

        async def _complete(system_prompt: str, user_prompt: str) -> str:
            self.prompts.append((system_prompt, user_prompt))
            return self._replies.pop(0)

        return _complete


def _reply(**answers: object) -> str:
    """Build a well-formed seam reply for the given question ids."""
    return json.dumps({qid: value for qid, value in answers.items()})


# ------------------------------------------------------------------- answers


@pytest.mark.asyncio
async def test_choice_answer_is_typed_and_carries_a_probability():
    backend = _ScriptedBackend([_reply(agreement={"answer": "contradict", "probability": 0.82})])

    result = await decide("some state", [_CHOICE], backend=backend)

    assert result.value("agreement") == "contradict"
    assert result["agreement"].probability == pytest.approx(0.82)
    assert result.backend == "scripted"


@pytest.mark.asyncio
async def test_score_answer_comes_back_as_a_number():
    backend = _ScriptedBackend([_reply(rating={"answer": 7, "probability": 0.5})])

    result = await decide("state", [_SCORE], backend=backend)

    assert result.value("rating") == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_a_score_outside_its_range_never_reaches_the_caller():
    """The schema carries minimum/maximum, so out-of-range is a validation miss."""
    backend = _ScriptedBackend([_reply(rating={"answer": 42, "probability": 0.9})] * 2)

    with pytest.raises(DecisionError):
        await decide("state", [_SCORE], backend=backend, max_retries=2)


def test_coerce_clamps_a_direct_caller_into_range():
    """`coerce` is also reachable without `decide` -- it clamps rather than trusting."""
    answer = _SCORE.coerce({"answer": 99.0, "probability": 0.5})

    assert answer.value == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_boolean_answer_is_a_bool():
    backend = _ScriptedBackend([_reply(safe={"answer": False, "probability": 0.91})])

    result = await decide("state", [_BOOL], backend=backend)

    assert result.value("safe") is False
    assert result["safe"].probability == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_several_questions_share_one_round_trip():
    backend = _ScriptedBackend(
        [
            _reply(
                agreement={"answer": "agree", "probability": 0.7},
                rating={"answer": 8, "probability": 0.6},
                safe={"answer": True, "probability": 0.99},
            )
        ]
    )

    result = await decide("state", [_CHOICE, _SCORE, _BOOL], backend=backend)

    assert len(backend.prompts) == 1
    assert (result.value("agreement"), result.value("rating"), result.value("safe")) == ("agree", 8.0, True)


@pytest.mark.asyncio
async def test_the_state_and_every_question_reach_the_prompt():
    backend = _ScriptedBackend([_reply(agreement={"answer": "agree", "probability": 0.5})])

    await decide("THE-STATE", [_CHOICE], backend=backend)

    _system, user = backend.prompts[0]
    assert "THE-STATE" in user
    assert "agreement" in user
    assert "agree, contradict, unrelated" in user


# ---------------------------------------------------- refusing to guess


@pytest.mark.asyncio
async def test_an_unreadable_reply_raises_after_retrying():
    backend = _ScriptedBackend(["not json at all", "still not json", "nope"])

    with pytest.raises(DecisionError):
        await decide("state", [_CHOICE], backend=backend, max_retries=3)

    assert len(backend.prompts) == 3


@pytest.mark.asyncio
async def test_an_option_outside_the_enum_raises():
    backend = _ScriptedBackend([_reply(agreement={"answer": "maybe", "probability": 0.9})] * 3)

    with pytest.raises(DecisionError):
        await decide("state", [_CHOICE], backend=backend, max_retries=3)


@pytest.mark.asyncio
async def test_a_missing_question_raises():
    """A reply that answers only one of two questions is not a partial answer."""
    backend = _ScriptedBackend([_reply(agreement={"answer": "agree", "probability": 0.5})] * 3)

    with pytest.raises(DecisionError):
        await decide("state", [_CHOICE, _SCORE], backend=backend, max_retries=3)


@pytest.mark.asyncio
async def test_the_retry_carries_the_validation_error_back():
    backend = _ScriptedBackend(
        [
            "garbage",
            _reply(agreement={"answer": "agree", "probability": 0.5}),
        ]
    )

    result = await decide("state", [_CHOICE], backend=backend, max_retries=3)

    assert result.value("agreement") == "agree"
    assert "previous response was invalid" in backend.prompts[1][1]


@pytest.mark.asyncio
async def test_decide_error_is_a_validated_llm_error():
    """A site that already catches the validated-loop failure catches this too."""
    backend = _ScriptedBackend(["garbage"])

    with pytest.raises(ValidatedLLMError):
        await decide("state", [_CHOICE], backend=backend, max_retries=1)


@pytest.mark.asyncio
async def test_no_questions_is_an_error_not_an_empty_result():
    with pytest.raises(DecisionError):
        await decide("state", [])


@pytest.mark.asyncio
async def test_a_non_numeric_probability_never_reaches_the_caller():
    """The schema types `probability`, so "high" is a validation miss, not a 0.5."""
    backend = _ScriptedBackend([_reply(agreement={"answer": "agree", "probability": "high"})] * 2)

    with pytest.raises(DecisionError):
        await decide("state", [_CHOICE], backend=backend, max_retries=2)


def test_coerce_reports_an_unusable_probability_as_zero():
    """Direct `coerce` callers get 0.0 rather than an invented confidence."""
    answer = _CHOICE.coerce({"answer": "agree", "probability": None})

    assert answer.probability == 0.0
    assert answer.value == "agree"


# ----------------------------------------------------------- calibration


@pytest.mark.asyncio
async def test_probabilities_are_reported_as_self_reported():
    """#17308 AC: a calibration claim without our own measurement is not evidence."""
    backend = _ScriptedBackend([_reply(agreement={"answer": "agree", "probability": 0.9})])

    result = await decide("state", [_CHOICE], backend=backend)

    assert result["agreement"].calibration is Calibration.SELF_REPORTED


def test_the_local_backend_declares_self_reported_calibration():
    assert LocalModelBackend.calibration is Calibration.SELF_REPORTED


# --------------------------------------------------------------- backends


def test_the_local_model_path_is_the_default_backend():
    assert LocalModelBackend.name in registered_backends()
    assert isinstance(get_backend(LocalModelBackend.name), LocalModelBackend)


def test_an_unregistered_backend_name_raises():
    with pytest.raises(DecisionError):
        get_backend("some-hosted-vendor")


def test_a_registered_backend_is_selectable_but_not_default():
    class _Hosted(DecisionBackend):
        name = "hosted_example"

        def completer(self, schema: dict) -> Completer:  # pragma: no cover - not called
            raise NotImplementedError

    register_backend(_Hosted())
    try:
        assert get_backend("hosted_example").name == "hosted_example"
        # Registration alone must not displace the local default.
        assert isinstance(LocalModelBackend(), LocalModelBackend)
    finally:
        from llm_shared import decisions

        decisions._BACKENDS.pop("hosted_example", None)


@pytest.mark.asyncio
async def test_the_local_backend_sends_the_schema_to_the_provider():
    """#17305's native schema mode is what keeps the retry rare."""
    service = MagicMock()
    service.chat = AsyncMock(
        return_value=MagicMock(content=_reply(safe={"answer": True, "probability": 0.5}), error=None)
    )

    result = await decide("state", [_BOOL], backend=LocalModelBackend(llm_service=service))

    _args, kwargs = service.chat.call_args
    assert kwargs["structured_output"] is True
    assert kwargs["json_schema"]["properties"]["safe"]["properties"]["answer"]["type"] == "boolean"
    assert kwargs["temperature"] == 0.0
    assert result.value("safe") is True


@pytest.mark.asyncio
async def test_a_provider_error_becomes_a_decision_error():
    service = MagicMock()
    service.chat = AsyncMock(return_value=MagicMock(content="", error="provider unavailable"))

    with pytest.raises(ValidatedLLMError):
        await decide("state", [_BOOL], backend=LocalModelBackend(llm_service=service))
