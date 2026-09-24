# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the structured-output dialect builders (#17305).

``structured_output_wiring_test.py`` asserts what each provider puts on the
wire; this covers the builders themselves, including the inputs a provider
never sees because the caller got them wrong -- a schema with the flag off, a
non-dict schema, an empty one.
"""

from __future__ import annotations

from llm_shared.models import LLMRequest
from llm_shared.structured_output import (
    APPLIED_MODE_KEY,
    DEFAULT_SCHEMA_NAME,
    SCHEMA_NAME_KEY,
    StructuredOutputMode,
    anthropic_output_format,
    apply_anthropic_output_config,
    effective_mode,
    guided_json_schema,
    note_structured_output,
    openai_response_format,
    request_schema,
    response_format_for_mode,
)

_SCHEMA = {"type": "object", "properties": {"v": {"type": "string"}}, "additionalProperties": False}


def _request(*, structured_output: bool = True, schema=None, metadata=None) -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": "x"}],
        structured_output=structured_output,
        json_schema=schema,
        metadata=metadata or {},
    )


# ------------------------------------------------------------ schema reading


def test_request_schema_reads_a_dict_schema():
    assert request_schema(_request(schema=_SCHEMA)) == _SCHEMA


def test_request_schema_treats_empty_and_non_dict_as_absent():
    assert request_schema(_request(schema={})) is None
    assert request_schema(_request(schema="{}")) is None
    assert request_schema(_request()) is None


def test_request_schema_tolerates_an_object_without_the_field():
    class Older:
        structured_output = True

    assert request_schema(Older()) is None


# ---------------------------------------------------------- OpenAI dialect


def test_openai_json_object_without_a_schema():
    assert openai_response_format(_request()) == {"type": "json_object"}


def test_openai_json_schema_with_one():
    payload = openai_response_format(_request(schema=_SCHEMA))

    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["name"] == DEFAULT_SCHEMA_NAME
    assert payload["json_schema"]["schema"] == _SCHEMA


def test_openai_schema_name_can_be_overridden_by_the_caller():
    request = _request(schema=_SCHEMA, metadata={SCHEMA_NAME_KEY: "verifier_verdict"})

    assert openai_response_format(request)["json_schema"]["name"] == "verifier_verdict"


def test_openai_returns_nothing_when_the_flag_is_off():
    assert openai_response_format(_request(structured_output=False, schema=_SCHEMA)) is None


def test_clamp_downgrades_a_schema_for_a_json_object_provider():
    clamped = response_format_for_mode(_request(schema=_SCHEMA), StructuredOutputMode.JSON_OBJECT)

    assert clamped == {"type": "json_object"}


def test_clamp_keeps_a_schema_for_a_json_schema_provider():
    kept = response_format_for_mode(_request(schema=_SCHEMA), StructuredOutputMode.JSON_SCHEMA)

    assert kept["type"] == "json_schema"


# -------------------------------------------------------- Anthropic dialect


def test_anthropic_format_needs_a_schema():
    assert anthropic_output_format(_request()) is None
    assert anthropic_output_format(_request(schema=_SCHEMA)) == {"type": "json_schema", "schema": _SCHEMA}


def test_apply_anthropic_output_config_preserves_other_keys():
    kwargs = {"output_config": {"effort": "high"}}

    apply_anthropic_output_config(kwargs, _request(schema=_SCHEMA))

    assert kwargs["output_config"] == {"effort": "high", "format": {"type": "json_schema", "schema": _SCHEMA}}


def test_apply_anthropic_output_config_is_a_noop_without_a_schema():
    kwargs: dict = {}

    apply_anthropic_output_config(kwargs, _request())

    assert kwargs == {}


# ------------------------------------------------------------- guided json


def test_guided_json_is_the_bare_schema():
    assert guided_json_schema(_request(schema=_SCHEMA)) == _SCHEMA
    assert guided_json_schema(_request()) is None
    assert guided_json_schema(_request(structured_output=False, schema=_SCHEMA)) is None


# ----------------------------------------------------------- applied mode


def test_effective_mode_matrix():
    with_schema = _request(schema=_SCHEMA)
    without = _request()

    assert effective_mode(without, StructuredOutputMode.NONE) is StructuredOutputMode.NONE
    assert effective_mode(without, StructuredOutputMode.JSON_OBJECT) is StructuredOutputMode.JSON_OBJECT
    assert effective_mode(without, StructuredOutputMode.JSON_SCHEMA) is StructuredOutputMode.JSON_OBJECT
    assert effective_mode(with_schema, StructuredOutputMode.JSON_SCHEMA) is StructuredOutputMode.JSON_SCHEMA
    assert effective_mode(with_schema, StructuredOutputMode.JSON_OBJECT) is StructuredOutputMode.JSON_OBJECT


def test_effective_mode_is_none_when_the_native_mode_requires_a_schema():
    """Anthropic: no schema means nothing native was applied, not bare JSON."""
    mode = effective_mode(_request(), StructuredOutputMode.JSON_SCHEMA, requires_schema=True)

    assert mode is StructuredOutputMode.NONE


def test_a_request_that_asked_for_nothing_reports_nothing():
    request = _request(structured_output=False)

    note_structured_output(request, "openai", StructuredOutputMode.JSON_SCHEMA)

    assert APPLIED_MODE_KEY not in request.metadata
