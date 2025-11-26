# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Slash Command Handler - Chat Command Processing System

This module provides a slash command system for the chat interface,
allowing users to access documentation, help, and other features
directly through chat commands.

Supported Commands:
- /docs [topic] - List or search documentation
- /help - Show available commands
- /status - Show system status

Related Issue: #166 - Architecture Roadmap Phase 1 - Critical Fixes
Created: 2025-01-26
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Supported slash command types."""

    DOCS = "docs"
    HELP = "help"
    STATUS = "status"
    UNKNOWN = "unknown"


@dataclass
class SlashCommandResult:
    """Result of executing a slash command."""

    success: bool
    command_type: CommandType
    content: str
    file_paths: List[str] = None

    def __post_init__(self):
        if self.file_paths is None:
            self.file_paths = []


class SlashCommandHandler:
    """
    Handler for slash commands in the chat interface.

    Detects and processes commands starting with '/' character,
    providing quick access to documentation and system features.
    """

    def __init__(self, docs_base_path: str = "docs"):
        """
        Initialize the slash command handler.

        Args:
            docs_base_path: Base path to documentation directory
        """
        self.docs_base_path = Path(docs_base_path)
        self._command_pattern = re.compile(r"^/(\w+)(?:\s+(.*))?$", re.IGNORECASE)

        # Documentation category mappings
        self.doc_categories = {
            "api": "api/",
            "architecture": "architecture/",
            "developer": "developer/",
            "features": "features/",
            "security": "security/",
            "deployment": "deployment/",
            "agents": "agents/",
            "guides": "guides/",
            "workflow": "workflow/",
            "testing": "testing/",
        }

        logger.info(f"SlashCommandHandler initialized with docs path: {docs_base_path}")

    def is_slash_command(self, message: str) -> bool:
        """
        Check if a message is a slash command.

        Args:
            message: User message to check

        Returns:
            True if the message starts with '/' and matches command pattern
        """
        if not message or not message.strip():
            return False
        return bool(self._command_pattern.match(message.strip()))

    def parse_command(self, message: str) -> tuple:
        """
        Parse a slash command into command type and arguments.

        Args:
            message: Slash command message

        Returns:
            Tuple of (CommandType, argument_string or None)
        """
        match = self._command_pattern.match(message.strip())
        if not match:
            return CommandType.UNKNOWN, None

        cmd = match.group(1).lower()
        args = match.group(2).strip() if match.group(2) else None

        command_map = {
            "docs": CommandType.DOCS,
            "doc": CommandType.DOCS,
            "documentation": CommandType.DOCS,
            "help": CommandType.HELP,
            "h": CommandType.HELP,
            "status": CommandType.STATUS,
            "st": CommandType.STATUS,
        }

        return command_map.get(cmd, CommandType.UNKNOWN), args

    async def execute(self, message: str) -> SlashCommandResult:
        """
        Execute a slash command and return the result.

        Args:
            message: Slash command message

        Returns:
            SlashCommandResult with execution outcome
        """
        cmd_type, args = self.parse_command(message)

        handlers = {
            CommandType.DOCS: self._handle_docs,
            CommandType.HELP: self._handle_help,
            CommandType.STATUS: self._handle_status,
            CommandType.UNKNOWN: self._handle_unknown,
        }

        handler = handlers.get(cmd_type, self._handle_unknown)
        return await handler(args)

    async def _handle_docs(self, args: Optional[str]) -> SlashCommandResult:
        """
        Handle /docs command - list or search documentation.

        Args:
            args: Optional search term or category

        Returns:
            SlashCommandResult with documentation listing
        """
        if not self.docs_base_path.exists():
            return SlashCommandResult(
                success=False,
                command_type=CommandType.DOCS,
                content="📁 Documentation directory not found.",
            )

        if not args:
            # List all documentation categories
            content = self._list_doc_categories()
            return SlashCommandResult(
                success=True,
                command_type=CommandType.DOCS,
                content=content,
            )

        args_lower = args.lower().strip()

        # Check if it's a category request
        if args_lower in self.doc_categories:
            return await self._list_category_docs(args_lower)

        # Search for matching docs
        return await self._search_docs(args)

    def _list_doc_categories(self) -> str:
        """Generate a list of documentation categories."""
        lines = [
            "## 📚 AutoBot Documentation",
            "",
            "Available categories (use `/docs <category>` to browse):",
            "",
        ]

        category_info = {
            "api": "🔌 API Reference - REST endpoints and integrations",
            "architecture": "🏗️ Architecture - System design and diagrams",
            "developer": "👨‍💻 Developer Guide - Setup and coding standards",
            "features": "✨ Features - Platform capabilities",
            "security": "🔒 Security - Security implementation",
            "deployment": "🚀 Deployment - Installation and setup",
            "agents": "🤖 Agents - Agent system documentation",
            "guides": "📖 Guides - How-to guides",
            "workflow": "🔄 Workflow - Workflow automation",
            "testing": "🧪 Testing - Test framework docs",
        }

        for cat, desc in category_info.items():
            if (self.docs_base_path / self.doc_categories[cat]).exists():
                lines.append(f"  • `{cat}` - {desc}")

        lines.extend([
            "",
            "**Quick Access:**",
            "  • `/docs api` - API documentation",
            "  • `/docs developer` - Developer guide",
            "  • `/docs <search term>` - Search all docs",
            "",
            "📄 **Main Index:** `docs/INDEX.md`",
        ])

        return "\n".join(lines)

    async def _list_category_docs(self, category: str) -> SlashCommandResult:
        """List documents in a specific category."""
        cat_path = self.docs_base_path / self.doc_categories[category]

        if not cat_path.exists():
            return SlashCommandResult(
                success=False,
                command_type=CommandType.DOCS,
                content=f"📁 Category '{category}' not found.",
            )

        files = []
        for f in sorted(cat_path.glob("*.md")):
            files.append(f"  • `{f.name}` - {f.relative_to(self.docs_base_path)}")

        if not files:
            content = f"📁 No documentation files found in '{category}' category."
        else:
            lines = [
                f"## 📂 Documentation: {category.title()}",
                "",
                f"Found {len(files)} document(s):",
                "",
            ]
            lines.extend(files[:20])  # Limit to 20 files
            if len(files) > 20:
                lines.append(f"  ... and {len(files) - 20} more")
            lines.extend([
                "",
                f"📍 Path: `docs/{self.doc_categories[category]}`",
            ])
            content = "\n".join(lines)

        file_paths = [str(f.relative_to(self.docs_base_path)) for f in cat_path.glob("*.md")]

        return SlashCommandResult(
            success=True,
            command_type=CommandType.DOCS,
            content=content,
            file_paths=file_paths[:20],
        )

    async def _search_docs(self, query: str) -> SlashCommandResult:
        """Search documentation for matching files."""
        query_lower = query.lower()
        matches = []

        # Search in all markdown files
        for md_file in self.docs_base_path.rglob("*.md"):
            # Skip archive directories
            if "archive" in str(md_file).lower() or "legacy" in str(md_file).lower():
                continue

            rel_path = md_file.relative_to(self.docs_base_path)
            file_name = md_file.stem.lower().replace("_", " ").replace("-", " ")

            # Match filename or path
            if query_lower in file_name or query_lower in str(rel_path).lower():
                matches.append(rel_path)

        if not matches:
            no_match_msg = (
                f"🔍 No documentation found matching '{query}'.\n\n"
                "Try `/docs` to see categories."
            )
            return SlashCommandResult(
                success=True,
                command_type=CommandType.DOCS,
                content=no_match_msg,
            )

        lines = [
            f"## 🔍 Search Results for '{query}'",
            "",
            f"Found {len(matches)} matching document(s):",
            "",
        ]

        for match in sorted(matches)[:15]:
            lines.append(f"  • `{match}`")

        if len(matches) > 15:
            lines.append(f"  ... and {len(matches) - 15} more")

        lines.extend([
            "",
            "💡 Use file browser or read directly for full content.",
        ])

        return SlashCommandResult(
            success=True,
            command_type=CommandType.DOCS,
            content="\n".join(lines),
            file_paths=[str(m) for m in matches[:15]],
        )

    async def _handle_help(self, args: Optional[str]) -> SlashCommandResult:
        """Handle /help command."""
        content = """## 💡 AutoBot Chat Commands

**Available Commands:**

| Command | Description |
|---------|-------------|
| `/docs` | List documentation categories |
| `/docs <category>` | Browse a specific category |
| `/docs <search>` | Search documentation |
| `/help` | Show this help message |
| `/status` | Show system status |

**Documentation Categories:**
  • `api` - API Reference
  • `architecture` - System Architecture
  • `developer` - Developer Guide
  • `features` - Platform Features
  • `security` - Security Docs
  • `deployment` - Deployment Guide
  • `agents` - Agent System
  • `guides` - How-to Guides

**Examples:**
  • `/docs api` - Browse API documentation
  • `/docs redis` - Search for Redis-related docs
  • `/docs developer` - View developer guide

💬 For general questions, just type normally without a slash command."""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.HELP,
            content=content,
        )

    async def _handle_status(self, args: Optional[str]) -> SlashCommandResult:
        """Handle /status command - show system status."""
        # Import here to avoid circular dependencies
        try:
            from backend.services.consolidated_health_service import ConsolidatedHealthService

            health_service = ConsolidatedHealthService()
            status = await health_service.get_health_status()

            content = f"""## ⚡ AutoBot System Status

**Overall Status:** {'✅ Healthy' if status.get('status') == 'healthy' else '⚠️ Degraded'}

**Services:**
  • Backend API: {'✅' if status.get('backend_api') else '❌'}
  • Redis: {'✅' if status.get('redis') else '❌'}
  • LLM Service: {'✅' if status.get('llm_service') else '❌'}

**Timestamp:** {status.get('timestamp', 'N/A')}

For detailed status, visit the monitoring dashboard."""

        except Exception as e:
            logger.warning(f"Could not get detailed status: {e}")
            content = """## ⚡ AutoBot System Status

**Status:** ✅ Running

The chat system is operational. For detailed status information,
check the monitoring dashboard or system logs.

📊 Dashboard: http://localhost:8001/api/health"""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.STATUS,
            content=content,
        )

    async def _handle_unknown(self, args: Optional[str]) -> SlashCommandResult:
        """Handle unknown commands."""
        return SlashCommandResult(
            success=False,
            command_type=CommandType.UNKNOWN,
            content="❓ Unknown command. Type `/help` to see available commands.",
        )


# Module-level instance for easy access
_handler_instance: Optional[SlashCommandHandler] = None


def get_slash_command_handler() -> SlashCommandHandler:
    """
    Get or create the global slash command handler instance.

    Returns:
        SlashCommandHandler singleton instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = SlashCommandHandler()
    return _handler_instance
