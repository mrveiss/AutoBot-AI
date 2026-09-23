# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The one retry-and-validate loop for code-consumed LLM replies (#17307).

``structured_ops.extract()`` already had this loop -- parse, validate against a
schema, feed the error back into the next prompt, raise rather than swallow --
and #17307 found that its three production callers are all *extraction* sites.
Not one decision site used it: ``judges/__init__.py`` indexed required keys
straight out of a single-shot reply (`:242-244`), and a ``KeyError`` there
became an error judgment that ``workflow_automation/step_evaluator.py:208``
converted into **approval** of the step the judge was asked to gate.

So the loop moved here, behind a *completer* -- any coroutine that turns a
(system, user) prompt pair into raw text. That is what lets one loop serve the
sites that have different transports: ``llm_service`` for the judges, the
claim verifier and the autoresearch scorers, a direct local Ollama call for
``rlm/evaluator.py``, and whichever backend the typed-decision seam
(``llm_shared/decisions.py``) is configured with.

Two properties the call sites depend on:

- **A validated reply or an exception, never a default.** A site that wants to
  fail open decides that itself, in the open, knowing the validation failed --
  it is never handed a plausible-looking value that came from a parse miss.
- **The schema travels to the provider too.** ``llm_service_completer`` sends
  ``structured_output=True`` *and* ``json_schema=``, so #17305's native schema
  mode constrains the reply before this loop has to correct it. The retry is
  the backstop, not the mechanism.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Union

import pydantic

from autobot_shared.env_utils import env_int
from autobot_shared.ssot_constants import CategoryDefaults
from llm_shared.json_utils import extract_json_object
from llm_shared.types import LLMType

logger = logging.getLogger(__name__)

#: Maximum number of LLM call attempts before raising. Shared with
#: ``structured_ops`` -- one knob for one loop.
VALIDATED_MAX_RETRIES: int = env_int("AUTOBOT_EXTRACT_MAX_RETRIES", 3)

#: A coroutine that turns a (system_prompt, user_prompt) pair into raw text.
Completer = Callable[[str, str], Awaitable[str]]

#: Either a Pydantic model class or a JSON Schema dict.
Schema = Union[type[pydantic.BaseModel], dict]


class ValidatedLLMError(RuntimeError):
    """Raised after all attempts are exhausted without a schema-valid result.

    ``structured_ops.ExtractionError`` is this class under its original name
    (#11520), so the call sites that catch it keep working.
    """


def schema_as_dict(schema: Schema) -> dict:
    """Return *schema* as a JSON Schema dict, whichever form it arrived in."""
    if isinstance(schema, dict):
        return schema
    return schema.model_json_schema()


def schema_repr(schema: Schema) -> str:
    """Serialise *schema* for inclusion in a prompt."""
    return json.dumps(schema_as_dict(schema), ensure_ascii=False)


def validate_against(data: dict, schema: Schema) -> pydantic.BaseModel | dict:
    """Validate *data*, returning a model instance or the dict. Raises on failure."""
    if isinstance(schema, dict):
        import jsonschema

        jsonschema.Draft202012Validator(schema).validate(data)
        return data
    return schema.model_validate(data)


def retry_suffix(error_msg: str) -> str:
    """Return the correction appended to the user prompt after a bad reply."""
    return (
        f"\n\nYour previous response was invalid: {error_msg}\n"
        "Return ONLY a valid JSON object that conforms to the schema."
    )


def llm_service_completer(
    schema: Schema,
    *,
    llm_type: LLMType | str = LLMType.ANALYSIS,
    llm_service: Any = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Completer:
    """Return a :data:`Completer` backed by ``services.llm_service``.

    The schema is sent with the request, not only rendered into the prompt:
    ``structured_output=True`` plus ``json_schema=`` reaches the provider's
    native schema mode (#17305) on every provider that has one, so most
    replies are already well-formed by the time the loop sees them.

    *llm_service* lets a caller inject its own configured interface so
    per-agent SSOT provider/model routing is preserved; the shared singleton
    is resolved lazily otherwise.
    """
    schema_dict = schema_as_dict(schema)

    async def _complete(system_prompt: str, user_prompt: str) -> str:
        service = llm_service
        if service is None:
            from services.llm_service import get_llm_service

            service = get_llm_service()
        messages = []
        if system_prompt:
            messages.append({"role": CategoryDefaults.ROLE_SYSTEM, "content": system_prompt})
        messages.append({"role": CategoryDefaults.ROLE_USER, "content": user_prompt})
        kwargs: dict[str, Any] = {
            "llm_type": llm_type,
            "structured_output": True,
            "json_schema": schema_dict,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        # `messages=` by keyword, as ``structured_ops._call_llm`` always called
        # it -- the service's own tests assert on that kwarg.
        response = await service.chat(messages=messages, **kwargs)
        if getattr(response, "error", None):
            raise ValidatedLLMError(f"LLM call failed: {response.error}")
        return response.content or ""

    return _complete


async def complete_validated(
    system_prompt: str,
    user_prompt: str,
    schema: Schema,
    *,
    completer: Completer,
    max_retries: int = VALIDATED_MAX_RETRIES,
    label: str = "validated_llm",
) -> pydantic.BaseModel | dict:
    """Return a schema-valid reply, or raise :class:`ValidatedLLMError`.

    Each attempt rebuilds the user prompt from the original plus the previous
    attempt's validation error, so the model always sees both the task and
    what it got wrong. *label* names the call site in the logs -- "which
    decision retried" is the question these logs get asked.
    """
    base_user = user_prompt
    last_error = ""

    for attempt in range(1, max_retries + 1):
        prompt = base_user if attempt == 1 else base_user + retry_suffix(last_error)
        raw = await completer(system_prompt, prompt)

        try:
            data = extract_json_object(raw)
        except json.JSONDecodeError as exc:
            last_error = f"JSONDecodeError: {exc}"
            logger.warning("%s: JSON parse failed (attempt %d/%d): %s", label, attempt, max_retries, exc)
            if attempt >= max_retries:
                raise ValidatedLLMError(f"{label}: non-JSON output after {max_retries} attempts: {exc}") from exc
            continue

        try:
            return validate_against(data, schema)
        except Exception as exc:
            last_error = str(exc)
            logger.warning("%s: validation failed (attempt %d/%d): %s", label, attempt, max_retries, exc)
            if attempt >= max_retries:
                raise ValidatedLLMError(
                    f"{label}: schema validation failed after {max_retries} attempts: {exc}"
                ) from exc

    raise ValidatedLLMError(f"{label}: exhausted all attempts without result")  # pragma: no cover


__all__ = [
    "Completer",
    "Schema",
    "VALIDATED_MAX_RETRIES",
    "ValidatedLLMError",
    "complete_validated",
    "llm_service_completer",
    "retry_suffix",
    "schema_as_dict",
    "schema_repr",
    "validate_against",
]
