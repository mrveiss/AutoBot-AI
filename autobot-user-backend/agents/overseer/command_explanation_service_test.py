# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for CommandExplanationService (#690)."""

import json
from unittest.mock import AsyncMock

import pytest
from agents.overseer.command_explanation_service import (
    CommandExplanationService,
    get_command_explanation_service,
)
from agents.overseer.types import (
    CommandBreakdownPart,
    CommandExplanation,
    OutputExplanation,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear class-level caches between tests."""
    CommandExplanationService._command_cache.clear()
    CommandExplanationService._output_cache.clear()
    yield
    CommandExplanationService._command_cache.clear()
    CommandExplanationService._output_cache.clear()


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset singleton between tests."""
    import agents.overseer.command_explanation_service as mod

    mod._service_instance = None
    yield
    mod._service_instance = None


@pytest.fixture()
def service():
    """Create a fresh CommandExplanationService."""
    return CommandExplanationService()


class TestCacheKeys:
    """Tests for cache key generation."""

    def test_normalizes_whitespace(self, service):
        k1 = service._get_cache_key("ls  -la   /tmp")
        k2 = service._get_cache_key("ls -la /tmp")
        assert k1 == k2

    def test_different_commands_different_keys(self, service):
        k1 = service._get_cache_key("ls -la")
        k2 = service._get_cache_key("cat /etc/hosts")
        assert k1 != k2

    def test_output_cache_key_deterministic(self, service):
        k1 = service._get_output_cache_key("ls", "output")
        k2 = service._get_output_cache_key("ls", "output")
        assert k1 == k2

    def test_output_cache_key_truncates_long_output(self, service):
        long_output = "x" * 5000
        k1 = service._get_output_cache_key("ls", long_output)
        k2 = service._get_output_cache_key("ls", long_output[:2000])
        assert k1 == k2


class TestExplainCommand:
    """Tests for explain_command method."""

    @pytest.mark.asyncio
    async def test_returns_cached_result(self, service):
        cached = CommandExplanation(
            summary="cached",
            breakdown=[CommandBreakdownPart(part="ls", explanation="list")],
        )
        cache_key = service._get_cache_key("ls")
        CommandExplanationService._command_cache[cache_key] = cached

        result = await service.explain_command("ls")
        assert result.summary == "cached"

    @pytest.mark.asyncio
    async def test_calls_llm_on_miss(self, service):
        llm_response = json.dumps(
            {
                "summary": "Lists files",
                "breakdown": [{"part": "ls", "explanation": "list command"}],
                "security_notes": None,
            }
        )
        service._call_llm = AsyncMock(return_value=llm_response)

        result = await service.explain_command("ls")
        assert result.summary == "Lists files"
        assert len(result.breakdown) == 1
        service._call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_caches_llm_result(self, service):
        llm_response = json.dumps(
            {
                "summary": "Lists files",
                "breakdown": [{"part": "ls", "explanation": "list"}],
            }
        )
        service._call_llm = AsyncMock(return_value=llm_response)

        await service.explain_command("ls -la")
        cache_key = service._get_cache_key("ls -la")
        assert cache_key in CommandExplanationService._command_cache

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, service):
        service._call_llm = AsyncMock(side_effect=Exception("LLM down"))

        result = await service.explain_command("ls -la")
        assert "ls" in result.summary.lower() or "Executes" in result.summary
        assert len(result.breakdown) >= 1


class TestExplainOutput:
    """Tests for explain_output method."""

    @pytest.mark.asyncio
    async def test_returns_cached_result(self, service):
        cached = OutputExplanation(summary="cached", key_findings=["cached finding"])
        cache_key = service._get_output_cache_key("ls", "output")
        CommandExplanationService._output_cache[cache_key] = cached

        result = await service.explain_output("ls", "output")
        assert result.summary == "cached"

    @pytest.mark.asyncio
    async def test_calls_llm_on_miss(self, service):
        llm_response = json.dumps(
            {
                "summary": "Shows files",
                "key_findings": ["Found 5 files"],
                "details": None,
                "next_steps": None,
            }
        )
        service._call_llm = AsyncMock(return_value=llm_response)

        result = await service.explain_output("ls", "file1\nfile2\n", 0)
        assert result.summary == "Shows files"
        service._call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_error_success(self, service):
        service._call_llm = AsyncMock(side_effect=Exception("LLM down"))

        result = await service.explain_output("ls", "output", return_code=0)
        assert "completed" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_fallback_on_error_failure(self, service):
        service._call_llm = AsyncMock(side_effect=Exception("LLM down"))

        result = await service.explain_output("bad_cmd", "error", return_code=1)
        assert "1" in result.summary


class TestPromptBuilding:
    """Tests for prompt building methods."""

    def test_command_prompt_contains_command(self, service):
        prompt = service._build_command_explanation_prompt("nmap -sn 10.0.0.0/24")
        assert "nmap -sn 10.0.0.0/24" in prompt
        assert "JSON" in prompt

    def test_output_prompt_truncates_long_output(self, service):
        long_output = "x" * 5000
        prompt = service._build_output_explanation_prompt("ls", long_output, 0)
        assert "truncated" in prompt.lower()
        assert "4000" in prompt

    def test_output_prompt_no_truncation_short(self, service):
        prompt = service._build_output_explanation_prompt("ls", "short output", 0)
        assert "truncated" not in prompt.lower()


class TestParsing:
    """Tests for response parsing methods."""

    def test_parse_command_explanation_valid(self, service):
        response = json.dumps(
            {
                "summary": "Scans network",
                "breakdown": [
                    {"part": "nmap", "explanation": "network mapper"},
                    {"part": "-sn", "explanation": "ping scan"},
                ],
                "security_notes": "Active scanning",
            }
        )
        result = service._parse_command_explanation(response, "nmap -sn 10.0.0.0/24")
        assert result.summary == "Scans network"
        assert len(result.breakdown) == 2
        assert result.security_notes == "Active scanning"

    def test_parse_command_explanation_fallback(self, service):
        result = service._parse_command_explanation("not json", "nmap -sn")
        assert "nmap" in result.summary.lower()
        assert len(result.breakdown) >= 1

    def test_parse_output_explanation_valid(self, service):
        response = json.dumps(
            {
                "summary": "Found hosts",
                "key_findings": ["3 hosts up", "1 host down"],
                "details": "Network scan complete",
                "next_steps": ["Run deeper scan"],
            }
        )
        result = service._parse_output_explanation(response)
        assert result.summary == "Found hosts"
        assert len(result.key_findings) == 2
        assert result.details == "Network scan complete"

    def test_parse_output_explanation_fallback(self, service):
        result = service._parse_output_explanation("garbage")
        assert result.summary is not None
        assert len(result.key_findings) >= 1


class TestExtractJson:
    """Tests for JSON extraction from LLM responses."""

    def test_direct_json(self, service):
        data = service._extract_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_embedded_json(self, service):
        text = 'Here is the result:\n{"summary": "test", "items": [1, 2]}\nDone.'
        data = service._extract_json(text)
        assert data["summary"] == "test"

    def test_invalid_raises(self, service):
        with pytest.raises(ValueError, match="Could not extract JSON"):
            service._extract_json("no json here at all")


class TestClearCache:
    """Tests for cache clearing."""

    def test_clears_both_caches(self, service):
        CommandExplanationService._command_cache["key1"] = "val1"
        CommandExplanationService._output_cache["key2"] = "val2"

        service.clear_cache()

        assert len(CommandExplanationService._command_cache) == 0
        assert len(CommandExplanationService._output_cache) == 0


class TestSingleton:
    """Tests for singleton factory."""

    def test_returns_same_instance(self):
        s1 = get_command_explanation_service()
        s2 = get_command_explanation_service()
        assert s1 is s2

    def test_creates_instance(self):
        instance = get_command_explanation_service()
        assert isinstance(instance, CommandExplanationService)
