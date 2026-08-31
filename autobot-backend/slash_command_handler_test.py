# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit Tests for Slash Command Handler

Tests the /docs, /help, and /status commands.

Related Issue: #166 - Architecture Roadmap Phase 1 - Critical Fixes
"""

import pytest

from slash_command_handler import (
    CommandType,
    SlashCommandHandler,
    SlashCommandResult,
    get_slash_command_handler,
)


class TestSlashCommandDetection:
    """Test slash command detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SlashCommandHandler(docs_base_path="docs")

    def test_is_slash_command_valid(self):
        """Test detection of valid slash commands."""
        assert self.handler.is_slash_command("/docs") is True
        assert self.handler.is_slash_command("/help") is True
        assert self.handler.is_slash_command("/status") is True
        assert self.handler.is_slash_command("/docs api") is True
        assert self.handler.is_slash_command("/docs search term") is True

    def test_is_slash_command_invalid(self):
        """Test non-slash command messages."""
        assert self.handler.is_slash_command("hello") is False
        assert self.handler.is_slash_command("what is /docs") is False
        assert self.handler.is_slash_command("") is False
        assert self.handler.is_slash_command("   ") is False
        assert self.handler.is_slash_command(None) is False

    def test_is_slash_command_edge_cases(self):
        """Test edge cases in slash command detection."""
        # Valid with leading/trailing whitespace
        assert self.handler.is_slash_command("  /docs  ") is True
        # Not valid - space before slash
        assert self.handler.is_slash_command(" hello /docs") is False


class TestCommandParsing:
    """Test command parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SlashCommandHandler()

    def test_parse_docs_command(self):
        """Test parsing /docs command."""
        cmd_type, args = self.handler.parse_command("/docs")
        assert cmd_type == CommandType.DOCS
        assert args is None

        cmd_type, args = self.handler.parse_command("/docs api")
        assert cmd_type == CommandType.DOCS
        assert args == "api"

        cmd_type, args = self.handler.parse_command("/docs redis client")
        assert cmd_type == CommandType.DOCS
        assert args == "redis client"

    def test_parse_help_command(self):
        """Test parsing /help command."""
        cmd_type, args = self.handler.parse_command("/help")
        assert cmd_type == CommandType.HELP
        assert args is None

        cmd_type, args = self.handler.parse_command("/h")
        assert cmd_type == CommandType.HELP

    def test_parse_status_command(self):
        """Test parsing /status command."""
        cmd_type, args = self.handler.parse_command("/status")
        assert cmd_type == CommandType.STATUS

        cmd_type, args = self.handler.parse_command("/st")
        assert cmd_type == CommandType.STATUS

    def test_parse_unknown_command(self):
        """Test parsing unknown commands."""
        cmd_type, args = self.handler.parse_command("/unknown")
        assert cmd_type == CommandType.UNKNOWN

        cmd_type, args = self.handler.parse_command("/xyz")
        assert cmd_type == CommandType.UNKNOWN

    def test_parse_command_aliases(self):
        """Test command aliases work."""
        # /doc is alias for /docs
        cmd_type, _ = self.handler.parse_command("/doc")
        assert cmd_type == CommandType.DOCS

        # /documentation is alias for /docs
        cmd_type, _ = self.handler.parse_command("/documentation")
        assert cmd_type == CommandType.DOCS


class TestDocsCommand:
    """Test /docs command execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SlashCommandHandler(docs_base_path="docs")

    @pytest.mark.asyncio
    async def test_docs_list_categories(self):
        """Test /docs with no args lists categories."""
        result = await self.handler.execute("/docs")

        assert result.success is True
        assert result.command_type == CommandType.DOCS
        assert "Documentation" in result.content
        assert "api" in result.content.lower()
        assert "developer" in result.content.lower()

    @pytest.mark.asyncio
    async def test_docs_category_api(self):
        """Test /docs api lists API docs."""
        result = await self.handler.execute("/docs api")

        assert result.success is True
        assert result.command_type == CommandType.DOCS
        # Should mention the category
        assert "api" in result.content.lower()

    @pytest.mark.asyncio
    async def test_docs_search(self):
        """Test /docs search functionality."""
        result = await self.handler.execute("/docs redis")

        assert result.success is True
        assert result.command_type == CommandType.DOCS
        # Should search for redis-related docs

    @pytest.mark.asyncio
    async def test_docs_not_found(self):
        """Test /docs with non-existent search term."""
        result = await self.handler.execute("/docs xyznonexistent123")

        assert result.success is True  # Command worked, just no results
        assert "No documentation found" in result.content


class TestHelpCommand:
    """Test /help command execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SlashCommandHandler()

    @pytest.mark.asyncio
    async def test_help_shows_commands(self):
        """Test /help shows available commands."""
        result = await self.handler.execute("/help")

        assert result.success is True
        assert result.command_type == CommandType.HELP
        assert "/docs" in result.content
        assert "/help" in result.content
        assert "/status" in result.content
        assert "Commands" in result.content


class TestStatusCommand:
    """/status must never assert health it has not measured (#14851).

    The command imported ``services.consolidated_health_service``, which has
    never existed in this repo. The import is function-local, so it raised
    ModuleNotFoundError on every call, and the surrounding ``except Exception``
    answered "Status: ✅ Running / The chat system is operational" — with no
    check behind it. The real branch was unreachable, so a user asking /status
    during an outage was told everything was fine.
    """

    # Words that assert a working system. None may appear in an answer that
    # measured nothing.
    _HEALTH_CLAIMS = ("operational", "running", "healthy")

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SlashCommandHandler()

    @pytest.mark.asyncio
    async def test_an_unreachable_health_source_is_reported_as_unknown(self, monkeypatch):
        """The reproduction, with the failure the original code actually hit."""
        import slash_command_handler as module

        async def unreachable():
            raise ModuleNotFoundError("No module named 'services.consolidated_health_service'")

        monkeypatch.setattr(module.StatusCommand, "_measure_health", staticmethod(unreachable))

        result = await self.handler.execute("/status")

        assert result.command_type == CommandType.STATUS
        assert result.success is False, "a status that could not be determined must not report success"
        assert "UNKNOWN" in result.content
        assert "could not be determined" in result.content
        assert "ModuleNotFoundError" in result.content, "the reason must reach the user, not only the log"

        lowered = result.content.lower()
        for claim in self._HEALTH_CLAIMS:
            assert claim not in lowered, f"/status claimed {claim!r} having measured nothing"

    @pytest.mark.asyncio
    async def test_an_empty_probe_registry_is_not_reported_as_healthy(self, monkeypatch):
        """The aggregator answers "ok" with no probes registered — nothing was checked.

        That answer is right for its own contract and wrong as a health report,
        so /status clamps it. Without this the fix would reproduce the original
        bug through a different route.
        """
        health_module = pytest.importorskip("api.system_health")
        monkeypatch.setattr(health_module, "_PROBES", {})

        result = await self.handler.execute("/status")

        assert result.success is False
        assert "no health probes are registered" in result.content
        lowered = result.content.lower()
        for claim in self._HEALTH_CLAIMS:
            assert claim not in lowered

    @pytest.mark.asyncio
    async def test_a_measured_failure_is_reported_as_a_failure(self, monkeypatch):
        """A down component must reach the user, and the answer must say it measured."""
        health_module = pytest.importorskip("api.system_health")

        async def redis_probe(request=None):
            return health_module.ComponentHealth(name="redis", status="down", detail="connection refused")

        async def kb_probe(request=None):
            return health_module.ComponentHealth(name="knowledge", status="ok")

        monkeypatch.setattr(health_module, "_PROBES", {"redis": redis_probe, "knowledge": kb_probe})

        result = await self.handler.execute("/status")

        # success=True here is the *measurement* succeeding — the content is what
        # carries the verdict. Asserting both pins which branch ran.
        assert result.success is True
        assert "DOWN" in result.content, "the overall verdict does not reflect the down component"
        assert "redis" in result.content and "knowledge" in result.content
        assert "Components checked:** 2" in result.content
        assert "UNKNOWN" not in result.content

    @pytest.mark.asyncio
    async def test_a_healthy_measurement_is_reported_as_healthy(self, monkeypatch):
        """Negative control: the fix must not make a working system read as broken."""
        health_module = pytest.importorskip("api.system_health")

        async def kb_probe(request=None):
            return health_module.ComponentHealth(name="knowledge", status="ok")

        monkeypatch.setattr(health_module, "_PROBES", {"knowledge": kb_probe})

        result = await self.handler.execute("/status")

        assert result.success is True
        assert "OK" in result.content
        assert "DOWN" not in result.content and "UNKNOWN" not in result.content


class TestUnknownCommand:
    """Test unknown command handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SlashCommandHandler()

    @pytest.mark.asyncio
    async def test_unknown_command_helpful_error(self):
        """Test unknown commands give helpful error."""
        result = await self.handler.execute("/foobar")

        assert result.success is False
        assert result.command_type == CommandType.UNKNOWN
        assert "/help" in result.content


class TestSingletonHandler:
    """Test the singleton handler pattern."""

    def test_get_slash_command_handler(self):
        """Test singleton returns same instance."""
        handler1 = get_slash_command_handler()
        handler2 = get_slash_command_handler()

        assert handler1 is handler2


class TestSlashCommandResult:
    """Test SlashCommandResult dataclass."""

    def test_result_defaults(self):
        """Test default values in result."""
        result = SlashCommandResult(
            success=True,
            command_type=CommandType.DOCS,
            content="Test content",
        )

        assert result.file_paths == []

    def test_result_with_file_paths(self):
        """Test result with file paths."""
        result = SlashCommandResult(
            success=True,
            command_type=CommandType.DOCS,
            content="Test",
            file_paths=["docs/api/README.md", "docs/developer/setup.md"],
        )

        assert len(result.file_paths) == 2
        assert "docs/api/README.md" in result.file_paths
