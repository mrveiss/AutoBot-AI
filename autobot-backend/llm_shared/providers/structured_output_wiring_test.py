# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
``structured_output`` reaches each provider's wire payload (#17305).

Before this, ``providers/ollama.py:113`` was the only site in the package that
read the flag; ``grep -rln "response_format\\|json_schema\\|json_object"``
over ``llm_shared/providers/`` returned nothing. These tests assert the flag
at the payload boundary per provider -- the shape ``ollama_test.py``'s
``test_format_json_set_when_structured_output_no_tools`` already used for the
one provider that worked -- so a provider that stops sending it fails here
rather than silently reverting to prompt-and-parse.

The assertions are on the payload builders, not on a live call: that is where
the regression was, and it is the only part reachable without a provider.
"""

from __future__ import annotations

import pytest

from llm_shared.models import LLMRequest
from llm_shared.providers.anthropic import AnthropicProvider
from llm_shared.providers.custom_openai import CustomOpenAIProvider
from llm_shared.providers.groq import GroqProvider
from llm_shared.providers.mistral import MistralProvider
from llm_shared.providers.nous_portal import NousPortalProvider
from llm_shared.providers.openai import OpenAIProvider
from llm_shared.providers.openrouter import OpenRouterProvider
from llm_shared.providers.vllm_base import VLLMBaseProvider
from llm_shared.structured_output import APPLIED_MODE_KEY, StructuredOutputMode

_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string"}},
    "required": ["verdict"],
    "additionalProperties": False,
}


def _request(*, structured_output: bool = True, schema: dict | None = None) -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": "classify this"}],
        model_name="test-model",
        structured_output=structured_output,
        json_schema=schema,
    )


# ---------------------------------------------------------------------------
# The OpenAI-compatible family -- one payload seam, five providers
# ---------------------------------------------------------------------------


class TestOpenAICompatibleFamily:
    def test_openai_sends_the_schema_it_was_given(self):
        params = OpenAIProvider(settings={"api_key": "k"})._build_params(_request(schema=_SCHEMA), "gpt-4o-mini")

        assert params["response_format"]["type"] == "json_schema"
        assert params["response_format"]["json_schema"]["schema"] == _SCHEMA

    def test_openai_marks_strict_only_for_a_closed_schema(self):
        open_schema = {"type": "object", "properties": {"v": {"type": "string"}}}
        provider = OpenAIProvider(settings={"api_key": "k"})

        closed = provider._build_params(_request(schema=_SCHEMA), "gpt-4o-mini")
        loose = provider._build_params(_request(schema=open_schema), "gpt-4o-mini")

        assert closed["response_format"]["json_schema"]["strict"] is True
        assert "strict" not in loose["response_format"]["json_schema"]

    def test_openai_falls_back_to_json_object_without_a_schema(self):
        params = OpenAIProvider(settings={"api_key": "k"})._build_params(_request(), "gpt-4o-mini")

        assert params["response_format"] == {"type": "json_object"}

    @pytest.mark.parametrize(
        "provider_cls",
        [GroqProvider, OpenRouterProvider, CustomOpenAIProvider, NousPortalProvider],
    )
    def test_json_object_family_never_sends_a_schema_it_cannot_enforce(self, provider_cls):
        """A declared json_object provider clamps: a schema is a 400 there."""
        provider = provider_cls(settings={"api_key": "k", "base_url": "http://host.invalid/v1"})

        params = provider._build_params(_request(schema=_SCHEMA), "test-model")

        assert params["response_format"] == {"type": "json_object"}

    def test_no_response_format_when_the_flag_is_off(self):
        params = OpenAIProvider(settings={"api_key": "k"})._build_params(
            _request(structured_output=False, schema=_SCHEMA), "gpt-4o-mini"
        )

        assert "response_format" not in params


# ---------------------------------------------------------------------------
# Mistral -- same dialect, its own builder
# ---------------------------------------------------------------------------


class TestMistral:
    def test_response_format_reaches_the_payload(self):
        provider = MistralProvider(settings={"api_key": "k"})

        params = provider._build_params(_request(), "mistral-small-latest", stream=False)

        assert params["response_format"] == {"type": "json_object"}

    def test_flag_off_sends_nothing(self):
        provider = MistralProvider(settings={"api_key": "k"})

        params = provider._build_params(_request(structured_output=False), "mistral-small-latest", stream=False)

        assert "response_format" not in params


# ---------------------------------------------------------------------------
# Anthropic -- output_config.format, and it must not clobber `effort`
# ---------------------------------------------------------------------------


class TestAnthropic:
    def test_schema_becomes_output_config_format(self):
        provider = AnthropicProvider(settings={"api_key": "k"})

        kwargs, _headers, _preserve = provider._build_request_kwargs("claude-sonnet-4-6", _request(schema=_SCHEMA))

        assert kwargs["output_config"]["format"] == {"type": "json_schema", "schema": _SCHEMA}

    def test_format_is_merged_beside_an_existing_effort_tier(self):
        """#15016 puts `effort` in output_config; #17305 must not overwrite it."""
        provider = AnthropicProvider(settings={"api_key": "k"})
        request = _request(schema=_SCHEMA)
        request.metadata["api_kwargs"] = {"output_config": {"effort": "high"}}

        kwargs, _headers, _preserve = provider._build_request_kwargs("claude-sonnet-4-6", request)

        assert kwargs["output_config"]["effort"] == "high"
        assert kwargs["output_config"]["format"]["type"] == "json_schema"

    def test_no_schema_sends_no_format(self):
        """The Messages API format has no schema-less variant to fall back to."""
        provider = AnthropicProvider(settings={"api_key": "k"})

        kwargs, _headers, _preserve = provider._build_request_kwargs("claude-sonnet-4-6", _request())

        assert "format" not in (kwargs.get("output_config") or {})

    def test_applied_mode_is_none_without_a_schema(self):
        provider = AnthropicProvider(settings={"api_key": "k"})

        assert provider.applied_structured_output_mode(_request()) is StructuredOutputMode.NONE
        assert provider.applied_structured_output_mode(_request(schema=_SCHEMA)) is StructuredOutputMode.JSON_SCHEMA


# ---------------------------------------------------------------------------
# vLLM -- guided decoding takes the schema itself
# ---------------------------------------------------------------------------


class TestVLLM:
    def test_schema_threads_into_the_inference_kwargs(self):
        kwargs = VLLMBaseProvider._inference_kwargs(_request(schema=_SCHEMA))

        assert kwargs["guided_json"] == _SCHEMA

    def test_no_guided_json_without_a_schema(self):
        assert "guided_json" not in VLLMBaseProvider._inference_kwargs(_request())

    def test_guided_decoding_kwargs_degrade_loudly_without_vllm(self, caplog):
        """An engine without GuidedDecodingParams must warn, not silently drop."""
        from llm_shared.providers.vllm import guided_decoding_kwargs

        with caplog.at_level("WARNING"):
            result = guided_decoding_kwargs(_SCHEMA)

        # vllm is absent in CI, so this asserts the degraded path; where vllm
        # IS installed the kwargs carry guided_decoding instead.
        if result == {}:
            assert any("guided decoding unavailable" in r.message for r in caplog.records)
        else:
            assert "guided_decoding" in result

    def test_no_schema_is_not_a_degradation(self, caplog):
        from llm_shared.providers.vllm import guided_decoding_kwargs

        with caplog.at_level("WARNING"):
            assert guided_decoding_kwargs(None) == {}

        assert not caplog.records


# ---------------------------------------------------------------------------
# The capability flag itself (#17305 AC4)
# ---------------------------------------------------------------------------


class TestCapabilityDeclaration:
    def test_every_named_provider_declares_a_native_mode(self):
        declared = {
            OpenAIProvider: StructuredOutputMode.JSON_SCHEMA,
            GroqProvider: StructuredOutputMode.JSON_OBJECT,
            OpenRouterProvider: StructuredOutputMode.JSON_OBJECT,
            CustomOpenAIProvider: StructuredOutputMode.JSON_OBJECT,
            NousPortalProvider: StructuredOutputMode.JSON_OBJECT,
            MistralProvider: StructuredOutputMode.JSON_OBJECT,
            AnthropicProvider: StructuredOutputMode.JSON_SCHEMA,
            VLLMBaseProvider: StructuredOutputMode.JSON_SCHEMA,
        }
        for provider_cls, mode in declared.items():
            assert provider_cls.structured_output_mode is mode, provider_cls.__name__

    def test_a_provider_without_a_native_mode_declares_none(self):
        """bedrock/vertexai/huggingface inherit NONE -- declared, not dropped."""
        from llm_shared.providers.huggingface import HuggingFaceProvider

        assert HuggingFaceProvider.structured_output_mode is StructuredOutputMode.NONE

    def test_applied_mode_is_recorded_on_the_request(self):
        provider = OpenAIProvider(settings={"api_key": "k"})
        request = _request(schema=_SCHEMA)

        from llm_shared.structured_output import note_structured_output

        note_structured_output(request, provider.provider_name, provider.applied_structured_output_mode(request))

        assert request.metadata[APPLIED_MODE_KEY] == StructuredOutputMode.JSON_SCHEMA.value

    def test_unhonoured_flag_is_recorded_and_warned(self, caplog):
        from llm_shared.structured_output import effective_mode, note_structured_output

        request = _request()
        applied = effective_mode(request, StructuredOutputMode.NONE)

        with caplog.at_level("WARNING"):
            note_structured_output(request, "huggingface", applied)

        assert request.metadata[APPLIED_MODE_KEY] == StructuredOutputMode.NONE.value
        assert any("not honoured natively" in r.message for r in caplog.records)
