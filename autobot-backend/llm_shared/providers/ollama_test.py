# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for MCP tool wiring in OllamaProvider.
GH#7911
"""

from __future__ import annotations

from unittest.mock import MagicMock

from llm_shared.models import LLMRequest, LLMSettings, ToolCall, ToolDefinition
from llm_shared.providers.ollama import OllamaProvider, _model_supports_tools

_TOOL = ToolDefinition(
    name="get_weather",
    description="Get the current weather",
    input_schema={"type": "object", "properties": {"location": {"type": "string"}}},
)


def _make_provider() -> OllamaProvider:
    settings = LLMSettings()
    streaming_manager = MagicMock()
    streaming_manager.should_use_streaming.return_value = False
    return OllamaProvider(settings=settings, streaming_manager=streaming_manager)


def _make_request(model: str = "llama3.1", tools=None, tool_choice=None, structured_output=False) -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": "What is the weather in Paris?"}],
        model_name=model,
        tools=tools,
        tool_choice=tool_choice,
        structured_output=structured_output,
    )


# ---------------------------------------------------------------------------
# Capability guard
# ---------------------------------------------------------------------------


class TestModelSupportsTools:
    def test_capable_models_detected(self):
        assert _model_supports_tools("llama3.1:8b") is True
        assert _model_supports_tools("llama3.2:latest") is True
        assert _model_supports_tools("mistral-nemo") is True
        assert _model_supports_tools("qwen2.5:7b") is True

    def test_incapable_models_rejected(self):
        assert _model_supports_tools("llama2") is False
        assert _model_supports_tools("codellama") is False
        assert _model_supports_tools("phi3") is False

    def test_case_insensitive(self):
        assert _model_supports_tools("LLAMA3.1") is True
        assert _model_supports_tools("Mistral-Large") is True


# ---------------------------------------------------------------------------
# build_request_data — tool injection
# ---------------------------------------------------------------------------


class TestBuildRequestDataTools:
    def test_tools_injected_for_capable_model(self):
        provider = _make_provider()
        req = _make_request(model="llama3.1:8b", tools=[_TOOL])
        data = provider.build_request_data(req, "llama3.1:8b", use_streaming=False)

        assert "tools" in data
        assert len(data["tools"]) == 1
        fn = data["tools"][0]
        assert fn["type"] == "function"
        assert fn["function"]["name"] == "get_weather"
        assert fn["function"]["description"] == "Get the current weather"
        assert "location" in fn["function"]["parameters"]["properties"]

    def test_tools_not_injected_for_incapable_model(self):
        provider = _make_provider()
        req = _make_request(model="llama2", tools=[_TOOL])
        data = provider.build_request_data(req, "llama2", use_streaming=False)

        assert "tools" not in data

    def test_tools_not_injected_when_no_tools_in_request(self):
        provider = _make_provider()
        req = _make_request(model="llama3.1:8b", tools=None)
        data = provider.build_request_data(req, "llama3.1:8b", use_streaming=False)

        assert "tools" not in data

    def test_tool_choice_forwarded_for_capable_model(self):
        provider = _make_provider()
        req = _make_request(model="llama3.1:8b", tools=[_TOOL], tool_choice="auto")
        data = provider.build_request_data(req, "llama3.1:8b", use_streaming=False)

        assert data.get("tool_choice") == "auto"

    def test_tool_choice_not_forwarded_for_incapable_model(self):
        provider = _make_provider()
        req = _make_request(model="llama2", tools=[_TOOL], tool_choice="auto")
        data = provider.build_request_data(req, "llama2", use_streaming=False)

        assert "tool_choice" not in data

    def test_format_json_suppressed_when_tools_present(self):
        provider = _make_provider()
        req = _make_request(model="llama3.1:8b", tools=[_TOOL], structured_output=True)
        data = provider.build_request_data(req, "llama3.1:8b", use_streaming=False)

        assert data["format"] == ""

    def test_format_json_set_when_structured_output_no_tools(self):
        provider = _make_provider()
        req = _make_request(model="llama3.1:8b", tools=None, structured_output=True)
        data = provider.build_request_data(req, "llama3.1:8b", use_streaming=False)

        assert data["format"] == "json"


# ---------------------------------------------------------------------------
# extract_tool_calls
# ---------------------------------------------------------------------------


class TestExtractToolCalls:
    def test_tool_calls_extracted(self):
        provider = _make_provider()
        response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_01",
                        "function": {"name": "get_weather", "arguments": {"location": "Paris"}},
                    }
                ],
            }
        }
        calls = provider.extract_tool_calls(response)

        assert len(calls) == 1
        tc = calls[0]
        assert isinstance(tc, ToolCall)
        assert tc.id == "call_01"
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "Paris"}

    def test_no_tool_calls_returns_empty(self):
        provider = _make_provider()
        response = {"message": {"role": "assistant", "content": "It's sunny."}}
        calls = provider.extract_tool_calls(response)

        assert calls == []

    def test_missing_message_returns_empty(self):
        provider = _make_provider()
        response = {"response": "some text"}
        calls = provider.extract_tool_calls(response)

        assert calls == []

    def test_multiple_tool_calls(self):
        provider = _make_provider()
        response = {
            "message": {
                "tool_calls": [
                    {"id": "c1", "function": {"name": "tool_a", "arguments": {"x": 1}}},
                    {"id": "c2", "function": {"name": "tool_b", "arguments": {"y": 2}}},
                ]
            }
        }
        calls = provider.extract_tool_calls(response)

        assert len(calls) == 2
        assert calls[0].name == "tool_a"
        assert calls[1].name == "tool_b"

    def test_missing_id_gets_uuid_fallback(self):
        provider = _make_provider()
        response = {
            "message": {
                "tool_calls": [
                    {"function": {"name": "tool_a", "arguments": {}}},
                ]
            }
        }
        calls = provider.extract_tool_calls(response)

        assert len(calls) == 1
        assert calls[0].id != ""
        assert len(calls[0].id) == 36  # uuid4 format


# ---------------------------------------------------------------------------
# build_response — tool_calls field
# ---------------------------------------------------------------------------


class TestBuildResponseToolCalls:
    def test_tool_calls_populated_in_response(self):
        provider = _make_provider()
        tc = ToolCall(id="c1", name="get_weather", arguments={"location": "Paris"})
        llm_resp = provider.build_response(
            content="",
            response={"model": "llama3.1"},
            model="llama3.1",
            processing_time=0.1,
            request_id="req-1",
            tool_calls=[tc],
        )

        assert llm_resp.tool_calls is not None
        assert len(llm_resp.tool_calls) == 1
        assert llm_resp.tool_calls[0].name == "get_weather"

    def test_no_tool_calls_when_omitted(self):
        provider = _make_provider()
        llm_resp = provider.build_response(
            content="Sunny!",
            response={"model": "llama3.1"},
            model="llama3.1",
            processing_time=0.1,
            request_id="req-2",
        )

        assert llm_resp.tool_calls is None


# ---------------------------------------------------------------------------
# _prepare_chat_request — streaming override and format gate
# ---------------------------------------------------------------------------


class TestPrepareCharRequestToolAwareness:
    def test_streaming_forced_off_for_capable_model_with_tools(self):
        """StreamingManager always returns True; must be overridden when tools active."""
        provider = _make_provider()
        provider.streaming_manager.should_use_streaming.return_value = True
        provider.ollama_host = "http://localhost:11434"

        req = _make_request(model="llama3.1:8b", tools=[_TOOL])
        _, _, _, use_streaming, data, _ = provider._prepare_chat_request(req)

        assert use_streaming is False
        assert data["stream"] is False

    def test_streaming_preserved_for_incapable_model(self):
        """Non-capable model with tools: streaming unchanged, tools not injected."""
        provider = _make_provider()
        provider.streaming_manager.should_use_streaming.return_value = True
        provider.ollama_host = "http://localhost:11434"

        req = _make_request(model="llama2", tools=[_TOOL])
        _, _, _, use_streaming, data, _ = provider._prepare_chat_request(req)

        assert use_streaming is True
        assert "tools" not in data

    def test_format_json_preserved_for_incapable_model_with_structured_output(self):
        """Incapable model with structured_output=True, tools=[...]: format=json must survive."""
        provider = _make_provider()
        provider.streaming_manager.should_use_streaming.return_value = False
        provider.ollama_host = "http://localhost:11434"

        req = _make_request(model="llama2", tools=[_TOOL], structured_output=True)
        _, _, _, _, data, _ = provider._prepare_chat_request(req)

        assert data["format"] == "json"
        assert "tools" not in data
