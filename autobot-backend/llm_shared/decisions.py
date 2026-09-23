# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
One typed-decision seam for code-consumed verdicts (#17308).

AutoBot makes a handful of small, frequent judgements whose answer is read by
*code*, not by a person: does this source agree with that claim, is this plan
better than that one, is this workflow step safe to run. Every site had its
own prompt, its own output format, its own parser and its own threshold, so
every site also had its own way of failing quietly.

``decide(state, questions)`` is the seam: a shared state, one or more typed
questions, and typed answers with a probability attached to each. The three
primitives cover every audited site --

- :class:`ChoiceQuestion` -- one option out of a fixed set (AGREE / CONTRADICT
  / UNRELATED, APPROVE / REJECT / CONDITIONAL / REVISE), probability per option.
- :class:`ScoreQuestion`  -- an ordered numeric level in a stated range
  (plan quality 0-1, a 0-10 rating), with the probability of the chosen level.
- :class:`BooleanQuestion` -- yes or no, with the probability of "yes".

Questions are answered against one shared state in a single round trip, and
the reply is validated against a generated JSON Schema through
``llm_shared.validated_llm`` -- so a malformed answer retries against the
schema and then *raises*. There is no code path here that turns an unreadable
reply into an answer, which is the defect #17307 recorded one layer up.

Backends
--------
``decide`` takes a backend, defaulting to :class:`LocalModelBackend`: the
local small-model path through ``services.llm_service`` with
``LLMType.CLASSIFICATION``, which AutoBot already routes to a local Ollama
model (``agents/gemma_classification_agent.py`` is the existing in-house
answer to this shape). No new outbound dependency is needed to use the seam,
and none is added by it. ``register_backend`` exists so a different backend
can be measured against the default with ``scripts/benchmark_decision_backends.py``
before anything changes.

**Probabilities are self-reported until measured.** Every answer carries
:class:`Calibration`, and the local backend reports ``SELF_REPORTED`` -- the
number is the model's stated confidence, not a calibrated frequency. Saying
otherwise would be a claim nobody here has measured; the benchmark script is
what would turn it into ``MEASURED``, per #17308's own acceptance criterion
that a calibration claim without our own measurement is not evidence.

Where this seam must NOT be used
--------------------------------
Audited in #17308 and recorded here so it is not re-proposed. These are
enforced by ``llm_shared/decisions_exclusions_test.py``, not just described:

- **Provider/tier routing** -- ``llm_shared/tiered_routing/complexity_router.py``
  and ``complexity_scorer.py`` already decide deterministically and locally,
  with no model call to displace.
- **Fast-path classifiers** -- ``intent_classifier.py``,
  ``workflow_classifier.py``, ``services/knowledge/intent_detector.py``,
  ``agent_tier_classifier.py`` are already sub-10ms and local.
- **Reranking** -- ``advanced_rag_optimizer.py`` uses a local cross-encoder,
  not an LLM.
- **Prompt-injection detection** -- ``security/prompt_injection_detector.py``
  is deterministic regex. A steerable model on that decision is the wrong
  direction.
- **The pre-action verifier gate** -- ``autobot_shared/pre_action_verifier_guard.py``
  is the best-fitting *shape* in the codebase and precisely where a cheaper,
  injection-steerable classifier must not go; it also deliberately picks a
  provider different from the actor to avoid shared-context steering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from autobot_shared.logging_manager import get_logger
from llm_shared.types import LLMType
from llm_shared.validated_llm import (
    Completer,
    ValidatedLLMError,
    complete_validated,
    llm_service_completer,
)

logger = get_logger(__name__)

#: Temperature for a decision call: the answer should not wander between runs.
DECISION_TEMPERATURE = 0.0


class Calibration(str, Enum):
    """Where an answer's probability came from."""

    #: The backend stated it. Usable for ordering, not as a frequency.
    SELF_REPORTED = "self_reported"
    #: Measured against a labelled sample by the benchmark harness.
    MEASURED = "measured"


class DecisionError(ValidatedLLMError):
    """Raised when a decision could not be obtained as a valid typed answer.

    A subclass of ``ValidatedLLMError`` so a call site that already catches
    the validated-loop failure catches this too.
    """


@dataclass(frozen=True)
class ChoiceQuestion:
    """Pick exactly one of *options*."""

    id: str
    prompt: str
    options: Sequence[str]

    def schema_fragment(self) -> dict:
        """Return this question's slice of the reply schema."""
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "enum": list(self.options)},
                "probability": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["answer", "probability"],
            "additionalProperties": False,
        }

    def describe(self) -> str:
        """Return the line that puts this question to the backend."""
        return f"- {self.id}: {self.prompt} Answer with exactly one of: {', '.join(self.options)}."

    def coerce(self, raw: Mapping[str, Any]) -> "DecisionAnswer":
        """Turn a validated reply fragment into an answer."""
        answer = str(raw["answer"])
        if answer not in self.options:  # pragma: no cover - schema enforces it
            raise DecisionError(f"{self.id}: {answer!r} is not one of {list(self.options)}")
        return DecisionAnswer(
            question_id=self.id,
            value=answer,
            probability=_unit(raw.get("probability")),
            reasoning=str(raw.get("reasoning") or ""),
        )


@dataclass(frozen=True)
class ScoreQuestion:
    """Return an ordered numeric level between *minimum* and *maximum*."""

    id: str
    prompt: str
    minimum: float = 0.0
    maximum: float = 1.0

    def schema_fragment(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "number", "minimum": self.minimum, "maximum": self.maximum},
                "probability": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["answer", "probability"],
            "additionalProperties": False,
        }

    def describe(self) -> str:
        return f"- {self.id}: {self.prompt} Answer with a number between {self.minimum} and {self.maximum}."

    def coerce(self, raw: Mapping[str, Any]) -> "DecisionAnswer":
        value = float(raw["answer"])
        clamped = max(self.minimum, min(self.maximum, value))
        if clamped != value:
            logger.warning("decisions: %s clamped %s into [%s, %s]", self.id, value, self.minimum, self.maximum)
        return DecisionAnswer(
            question_id=self.id,
            value=clamped,
            probability=_unit(raw.get("probability")),
            reasoning=str(raw.get("reasoning") or ""),
        )


@dataclass(frozen=True)
class BooleanQuestion:
    """Answer yes or no; the probability is the probability of ``True``."""

    id: str
    prompt: str

    def schema_fragment(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "boolean"},
                "probability": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["answer", "probability"],
            "additionalProperties": False,
        }

    def describe(self) -> str:
        return f"- {self.id}: {self.prompt} Answer true or false."

    def coerce(self, raw: Mapping[str, Any]) -> "DecisionAnswer":
        return DecisionAnswer(
            question_id=self.id,
            value=bool(raw["answer"]),
            probability=_unit(raw.get("probability")),
            reasoning=str(raw.get("reasoning") or ""),
        )


#: Any of the three primitives.
Question = ChoiceQuestion | ScoreQuestion | BooleanQuestion


@dataclass(frozen=True)
class DecisionAnswer:
    """One typed answer and the probability the backend attached to it."""

    question_id: str
    value: str | float | bool
    probability: float
    reasoning: str = ""
    calibration: Calibration = Calibration.SELF_REPORTED

    def with_calibration(self, calibration: Calibration) -> "DecisionAnswer":
        """Return a copy carrying *calibration* -- used by the benchmark."""
        return DecisionAnswer(
            question_id=self.question_id,
            value=self.value,
            probability=self.probability,
            reasoning=self.reasoning,
            calibration=calibration,
        )


@dataclass(frozen=True)
class DecisionResult:
    """Every answer from one ``decide`` round trip, keyed by question id."""

    answers: dict[str, DecisionAnswer] = field(default_factory=dict)
    backend: str = ""

    def __getitem__(self, question_id: str) -> DecisionAnswer:
        return self.answers[question_id]

    def value(self, question_id: str) -> str | float | bool:
        """Return just the answer's value."""
        return self.answers[question_id].value


def _unit(value: Any) -> float:
    """Clamp *value* into [0, 1]; an unusable probability is 0.0, never a guess."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _reply_schema(questions: Sequence[Question]) -> dict:
    """Return the JSON Schema the whole reply must satisfy."""
    return {
        "type": "object",
        "properties": {q.id: q.schema_fragment() for q in questions},
        "required": [q.id for q in questions],
        "additionalProperties": False,
    }


_SYSTEM_PROMPT = (
    "You answer typed questions about a given state. "
    "Return ONLY a JSON object whose keys are the question ids. "
    "Each value is an object with `answer`, `probability` (0.0-1.0, your confidence "
    "in that answer) and a one-sentence `reasoning`. "
    "Do not add keys, prose or markdown fences."
)


def _user_prompt(state: str, questions: Sequence[Question]) -> str:
    """Return the state-plus-questions request body."""
    lines = "\n".join(q.describe() for q in questions)
    return f"## State\n{state}\n\n## Questions\n{lines}"


class DecisionBackend:
    """A transport that answers a state-plus-questions request."""

    name = "base"
    calibration = Calibration.SELF_REPORTED

    def completer(self, schema: dict) -> Completer:  # pragma: no cover - interface
        """Return the :data:`Completer` that carries one decision round trip."""
        raise NotImplementedError


class LocalModelBackend(DecisionBackend):
    """The default: the local small-model path through ``services.llm_service``.

    ``LLMType.CLASSIFICATION`` is what AutoBot already routes to a local
    model, so the seam costs no egress and needs no vendor. A caller can
    inject its own configured service (per-agent SSOT routing) or a different
    ``llm_type``.
    """

    name = "local_model"

    def __init__(self, llm_service: Any = None, llm_type: LLMType | str = LLMType.CLASSIFICATION) -> None:
        self._llm_service = llm_service
        self._llm_type = llm_type

    def completer(self, schema: dict) -> Completer:
        return llm_service_completer(
            schema,
            llm_type=self._llm_type,
            llm_service=self._llm_service,
            temperature=DECISION_TEMPERATURE,
        )


_BACKENDS: dict[str, DecisionBackend] = {}


def register_backend(backend: DecisionBackend) -> None:
    """Register *backend* under its ``name`` so a caller can select it.

    Registration does not make a backend the default -- #17308 requires a
    benchmark against a labelled sample before that, and a hosted backend also
    has to answer for egress guarding, redaction and key handling, none of
    which the local path needs.
    """
    _BACKENDS[backend.name] = backend
    logger.info("decisions: registered backend %s", backend.name)


def get_backend(name: str) -> DecisionBackend:
    """Return the registered backend called *name*."""
    if name == LocalModelBackend.name and name not in _BACKENDS:
        return LocalModelBackend()
    if name not in _BACKENDS:
        raise DecisionError(f"no decision backend registered as {name!r}")
    return _BACKENDS[name]


def registered_backends() -> list[str]:
    """Return the names of every registered backend, local path included."""
    return sorted({LocalModelBackend.name, *_BACKENDS})


async def decide(
    state: str,
    questions: Sequence[Question],
    *,
    backend: DecisionBackend | None = None,
    max_retries: int | None = None,
    label: str = "decisions.decide",
) -> DecisionResult:
    """Answer *questions* against *state*, typed, with probabilities.

    Raises :class:`DecisionError` when no schema-valid answer arrives within
    the retry budget. That is deliberate: a caller that wants to fail open
    decides so itself, having been told the decision failed -- the seam never
    manufactures an answer, because a manufactured answer is indistinguishable
    from a real one at the call site.
    """
    if not questions:
        raise DecisionError("decide() needs at least one question")
    active = backend or LocalModelBackend()
    schema = _reply_schema(questions)
    kwargs: dict[str, Any] = {"completer": active.completer(schema), "label": label}
    if max_retries is not None:
        kwargs["max_retries"] = max_retries

    try:
        payload = await complete_validated(_SYSTEM_PROMPT, _user_prompt(state, questions), schema, **kwargs)
    except ValidatedLLMError as exc:
        # Re-raised as DecisionError so a caller can catch decisions
        # specifically, while `except ValidatedLLMError` still catches it too.
        raise DecisionError(str(exc)) from exc
    data = payload if isinstance(payload, dict) else payload.model_dump()

    answers: dict[str, DecisionAnswer] = {}
    for question in questions:
        answer = question.coerce(data[question.id])
        answers[question.id] = answer.with_calibration(active.calibration)
    return DecisionResult(answers=answers, backend=active.name)


__all__ = [
    "BooleanQuestion",
    "Calibration",
    "ChoiceQuestion",
    "DECISION_TEMPERATURE",
    "DecisionAnswer",
    "DecisionBackend",
    "DecisionError",
    "DecisionResult",
    "LocalModelBackend",
    "Question",
    "ScoreQuestion",
    "decide",
    "get_backend",
    "register_backend",
    "registered_backends",
]
