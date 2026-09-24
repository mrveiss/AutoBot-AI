# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Provider-native structured-output payloads (#17305).

``LLMRequest.structured_output`` reached exactly one provider before this:
``providers/ollama.py`` turned it into ``format: "json"`` and every hosted
provider dropped it silently. A caller that set the flag and then handed the
reply to a text parser -- the judges, the contradiction detector, the
extraction cognifiers -- believed it was asking for schema-constrained output
and was not. "Constrained" and "hoping" produced the same payload.

Each dialect's fragment is built here once, so a provider opts into native
structured output by calling the builder for the dialect it speaks instead of
hand-rolling a payload key:

- ``openai_response_format`` -- the OpenAI chat-completions ``response_format``
  (OpenAI, Groq, OpenRouter, CustomOpenAI, NousPortal, Mistral).
- ``anthropic_output_format`` -- the Messages API ``output_config["format"]``.
- ``guided_json_schema`` -- the raw schema, for engines that take one directly
  (vLLM guided decoding, Ollama's ``format``).

``StructuredOutputMode`` is the other half: a provider *declares* what it can
do, so a caller can tell a schema-constrained reply from a best-effort one
rather than inferring it from silence (#17305 AC4). ``note_structured_output``
records that declaration on the request and warns when the flag cannot be
honoured -- ``MEASUREMENT_DISCIPLINE.md``: *asked for and dropped* must not
read the same as *asked for and applied*.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Dict

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from llm_shared.models import LLMRequest

logger = get_logger(__name__)

#: ``json_schema.name`` sent when the caller supplies no name of its own.
#: The OpenAI dialect requires the field; the value is opaque to the API.
DEFAULT_SCHEMA_NAME = "autobot_structured_output"

#: Request metadata key carrying an explicit schema name.
SCHEMA_NAME_KEY = "json_schema_name"

#: Request metadata key this module writes with the mode that was applied.
APPLIED_MODE_KEY = "structured_output_mode_applied"


class StructuredOutputMode(str, Enum):
    """What a provider can do with ``LLMRequest.structured_output``."""

    #: No native mode -- the flag cannot be honoured, only prompted for.
    NONE = "none"
    #: Free-form JSON mode: valid JSON guaranteed, shape is not.
    JSON_OBJECT = "json_object"
    #: Schema-constrained: a supplied JSON Schema is enforced by the provider.
    JSON_SCHEMA = "json_schema"


def request_schema(request: "LLMRequest") -> Dict[str, Any] | None:
    """Return the JSON Schema carried by *request*, or None.

    Read through ``getattr`` so a caller holding an older ``LLMRequest``
    (or a test double standing in for one) is a missing schema rather than
    an ``AttributeError``.
    """
    schema = getattr(request, "json_schema", None)
    return schema if isinstance(schema, dict) and schema else None


def _schema_name(request: "LLMRequest") -> str:
    """Return the caller's schema name, else :data:`DEFAULT_SCHEMA_NAME`."""
    metadata = getattr(request, "metadata", None) or {}
    name = metadata.get(SCHEMA_NAME_KEY)
    return str(name) if name else DEFAULT_SCHEMA_NAME


def openai_response_format(request: "LLMRequest") -> Dict[str, Any] | None:
    """Return the ``response_format`` value for the OpenAI dialect, or None.

    A schema-carrying request gets ``json_schema`` mode; a bare
    ``structured_output=True`` gets ``json_object``, which is the most the
    dialect can promise without a schema. ``strict`` is set only when the
    schema itself declares ``additionalProperties: false`` -- strict mode
    rejects a schema that does not, so asserting it on every schema would
    turn a working prompt-and-parse call into a 400.
    """
    if not getattr(request, "structured_output", False):
        return None
    schema = request_schema(request)
    if schema is None:
        return {"type": "json_object"}
    json_schema: Dict[str, Any] = {"name": _schema_name(request), "schema": schema}
    if schema.get("additionalProperties") is False:
        json_schema["strict"] = True
    return {"type": "json_schema", "json_schema": json_schema}


def response_format_for_mode(
    request: "LLMRequest",
    declared: StructuredOutputMode,
) -> Dict[str, Any] | None:
    """Return ``response_format`` clamped to what *declared* can keep, or None.

    Sending ``json_schema`` to an endpoint that implements only
    ``json_object`` is a 400, so a provider declaring the lower capability
    drops the schema deliberately; the applied mode recorded by
    :func:`note_structured_output` is what says the schema did not travel.
    """
    payload = openai_response_format(request)
    if payload is None:
        return None
    if declared is not StructuredOutputMode.JSON_SCHEMA:
        return {"type": "json_object"}
    return payload


def anthropic_output_format(request: "LLMRequest") -> Dict[str, Any] | None:
    """Return the Anthropic ``output_config["format"]`` value, or None.

    The Messages API expresses structured output as
    ``output_config={"format": {"type": "json_schema", "schema": {...}}}``;
    there is no bare-JSON variant, so ``structured_output=True`` with no
    schema has nothing native to map onto and returns None. The caller logs
    that through :func:`note_structured_output` rather than dropping it.
    """
    if not getattr(request, "structured_output", False):
        return None
    schema = request_schema(request)
    if schema is None:
        return None
    return {"type": "json_schema", "schema": schema}


def apply_anthropic_output_config(kwargs: Dict[str, Any], request: "LLMRequest") -> None:
    """Merge the structured-output format into ``kwargs["output_config"]``, in place.

    Merged, never assigned: ``_apply_thinking_budget`` (#15016) may already
    have put an ``effort`` tier in ``output_config`` for a model that requires
    adaptive thinking, and overwriting the dict would silently undo that
    mapping. A no-op when the request asks for nothing native.
    """
    output_format = anthropic_output_format(request)
    if output_format is None:
        return
    output_config = dict(kwargs.get("output_config") or {})
    output_config["format"] = output_format
    kwargs["output_config"] = output_config


def guided_json_schema(request: "LLMRequest") -> Dict[str, Any] | None:
    """Return the schema for engines that accept one directly, or None.

    vLLM's guided decoding and Ollama's ``format`` both take the schema
    itself rather than a wrapper object.
    """
    if not getattr(request, "structured_output", False):
        return None
    return request_schema(request)


def effective_mode(
    request: "LLMRequest",
    declared: StructuredOutputMode,
    *,
    requires_schema: bool = False,
) -> StructuredOutputMode:
    """Return the mode a *declared*-capability provider actually applies.

    A schema-capable provider still only delivers ``json_object`` when the
    request carries no schema. Where the native mode *requires* one --
    Anthropic's ``output_config.format`` has no schema-less variant --
    *requires_schema* makes that ``NONE`` instead, because reporting
    ``json_object`` would claim a constraint the payload does not carry.
    """
    if not getattr(request, "structured_output", False):
        return StructuredOutputMode.NONE
    if request_schema(request) is not None:
        return declared
    if requires_schema:
        return StructuredOutputMode.NONE
    if declared is StructuredOutputMode.JSON_SCHEMA:
        return StructuredOutputMode.JSON_OBJECT
    return declared


def note_structured_output(request: "LLMRequest", provider_name: str, applied: StructuredOutputMode) -> None:
    """Record on *request* which structured-output mode was applied, and warn.

    ``metadata[APPLIED_MODE_KEY]`` is the capability flag a caller reads to
    tell a constrained reply from a best-effort one. A request that asked for
    structured output and got ``NONE`` is logged at WARNING: that is the case
    #17305 was filed for, and it must be visible without reading the payload.
    """
    if not getattr(request, "structured_output", False):
        return
    metadata = getattr(request, "metadata", None)
    if isinstance(metadata, dict):
        metadata[APPLIED_MODE_KEY] = applied.value
    if applied is StructuredOutputMode.NONE:
        logger.warning(
            "structured_output=True is not honoured natively by provider=%s (#17305) "
            "-- the reply is prompt-and-parse, not schema-constrained",
            provider_name,
        )
    else:
        logger.debug(
            "structured_output=True mapped to %s on provider=%s",
            applied.value,
            provider_name,
        )


__all__ = [
    "APPLIED_MODE_KEY",
    "DEFAULT_SCHEMA_NAME",
    "SCHEMA_NAME_KEY",
    "StructuredOutputMode",
    "anthropic_output_format",
    "apply_anthropic_output_config",
    "effective_mode",
    "guided_json_schema",
    "note_structured_output",
    "openai_response_format",
    "request_schema",
    "response_format_for_mode",
]
