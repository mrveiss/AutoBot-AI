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
- /scan <target> - Start security assessment scan
- /security [list|resume|status] - Manage security assessments

Related Issues:
- #166 - Architecture Roadmap Phase 1 - Critical Fixes
- #260 - Security Assessment Workflow Manager
Created: 2025-01-26
Updated: 2025-01-29 - Added security commands
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Supported slash command types."""

    DOCS = "docs"
    HELP = "help"
    STATUS = "status"
    SCAN = "scan"
    SECURITY = "security"
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
            # Security assessment commands (#260)
            "scan": CommandType.SCAN,
            "nmap": CommandType.SCAN,
            "security": CommandType.SECURITY,
            "sec": CommandType.SECURITY,
            "assessment": CommandType.SECURITY,
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
            CommandType.SCAN: self._handle_scan,
            CommandType.SECURITY: self._handle_security,
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
| `/scan <target>` | Start security assessment scan |
| `/security` | Manage security assessments |

**Documentation Categories:**
  • `api` - API Reference
  • `architecture` - System Architecture
  • `developer` - Developer Guide
  • `features` - Platform Features
  • `security` - Security Docs
  • `deployment` - Deployment Guide
  • `agents` - Agent System
  • `guides` - How-to Guides

**Security Assessment:**
  • `/scan <network/24>` - Scan a network (e.g., target subnet)
  • `/scan host.com --training` - Scan with exploitation enabled
  • `/security list` - List active assessments
  • `/security status <id>` - Check assessment progress
  • `/security resume <id>` - Resume assessment

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
            content = f"""## ⚡ AutoBot System Status

**Status:** ✅ Running

The chat system is operational. For detailed status information,
check the monitoring dashboard or system logs.

📊 Dashboard: http://localhost:{NetworkConstants.BACKEND_PORT}/api/health"""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.STATUS,
            content=content,
        )

    async def _handle_scan(self, args: Optional[str]) -> SlashCommandResult:
        """
        Handle /scan command - Start a new security assessment.

        Args:
            args: Target specification (IP, CIDR, or hostname)

        Returns:
            SlashCommandResult with assessment details or instructions
        """
        if not args:
            content = """## 🔍 Security Scan Command

**Usage:** `/scan <target> [options]`

**Examples:**
  • `/scan <target_host>` - Scan single host
  • `/scan <target_network/24>` - Scan network range
  • `/scan example.com` - Scan by hostname
  • `/scan <target_host> --training` - Enable training mode (exploitation)

**Options:**
  • `--training` - Enable exploitation phase (for authorized testing)
  • `--name <name>` - Custom assessment name

**Next Steps:**
1. Specify a target to begin scanning
2. The system will create a structured security assessment
3. Progress through phases: RECON → PORT_SCAN → ENUMERATION → VULN_ANALYSIS

💡 Use `/security list` to see existing assessments."""

            return SlashCommandResult(
                success=True,
                command_type=CommandType.SCAN,
                content=content,
            )

        # Parse the target and options
        parts = args.split()
        target = parts[0]
        training_mode = "--training" in args.lower()

        # Extract custom name if provided
        assessment_name = f"Assessment: {target}"
        if "--name" in args.lower():
            name_idx = args.lower().find("--name")
            name_part = args[name_idx + 6:].strip()
            if name_part:
                # Get first quoted string or word
                if name_part.startswith('"'):
                    end_quote = name_part.find('"', 1)
                    if end_quote > 0:
                        assessment_name = name_part[1:end_quote]
                else:
                    assessment_name = name_part.split()[0]

        try:
            from src.services.security_workflow_manager import get_security_workflow_manager

            manager = get_security_workflow_manager()
            assessment = await manager.create_assessment(
                name=assessment_name,
                target=target,
                training_mode=training_mode,
            )

            mode_emoji = "🎯" if training_mode else "🛡️"
            mode_text = "Training Mode (exploitation enabled)" if training_mode else "Safe Mode (no exploitation)"

            content = f"""## {mode_emoji} Security Assessment Started

**Assessment ID:** `{assessment.id[:8]}...`
**Name:** {assessment.name}
**Target:** {target}
**Mode:** {mode_text}
**Phase:** {assessment.phase.value}

**Current Phase:** INIT - Assessment initialized

**Next Steps:**
1. Begin reconnaissance with network discovery
2. Use nmap/masscan for port scanning
3. Enumerate services on discovered ports
4. Analyze for vulnerabilities

**Commands:**
  • `/security status {assessment.id[:8]}` - Check progress
  • `/security resume {assessment.id[:8]}` - Continue assessment

💡 The agent will guide you through each phase."""

            return SlashCommandResult(
                success=True,
                command_type=CommandType.SCAN,
                content=content,
            )

        except Exception as e:
            logger.error(f"Failed to create security assessment: {e}")
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SCAN,
                content=f"❌ Failed to create assessment: {e}\n\nPlease check the logs for details.",
            )

    async def _handle_security(self, args: Optional[str]) -> SlashCommandResult:
        """
        Handle /security command - Manage security assessments.

        Args:
            args: Subcommand (list, resume, status, etc.)

        Returns:
            SlashCommandResult with assessment information
        """
        if not args:
            # Show security command help
            content = """## 🔒 Security Assessment Commands

**Usage:** `/security <subcommand> [options]`

**Subcommands:**

| Command | Description |
|---------|-------------|
| `/security list` | List all active assessments |
| `/security status <id>` | Show assessment status |
| `/security resume <id>` | Resume an assessment |
| `/security phases` | Show workflow phases |

**Quick Start:**
  • `/scan <target_network/24>` - Start new scan
  • `/security list` - See active assessments
  • `/security status abc123` - Check specific assessment

**Workflow Phases:**
INIT → RECON → PORT_SCAN → ENUMERATION → VULN_ANALYSIS → REPORTING"""

            return SlashCommandResult(
                success=True,
                command_type=CommandType.SECURITY,
                content=content,
            )

        # Parse subcommand
        parts = args.strip().split(maxsplit=1)
        subcommand = parts[0].lower()
        sub_args = parts[1] if len(parts) > 1 else None

        try:
            from src.services.security_workflow_manager import (
                PHASE_DESCRIPTIONS,
                get_security_workflow_manager,
            )

            manager = get_security_workflow_manager()

            if subcommand == "list":
                return await self._security_list(manager)
            elif subcommand == "status":
                return await self._security_status(manager, sub_args)
            elif subcommand == "resume":
                return await self._security_resume(manager, sub_args)
            elif subcommand == "phases":
                return self._security_phases(PHASE_DESCRIPTIONS)
            else:
                return SlashCommandResult(
                    success=False,
                    command_type=CommandType.SECURITY,
                    content=f"❓ Unknown subcommand: `{subcommand}`\n\nUse `/security` for available commands.",
                )

        except Exception as e:
            logger.error(f"Security command failed: {e}")
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content=f"❌ Security command failed: {e}",
            )

    async def _security_list(self, manager) -> SlashCommandResult:
        """List active security assessments."""
        assessments = await manager.list_active_assessments()

        if not assessments:
            content = """## 📋 Active Security Assessments

No active assessments found.

**Start a new scan:**
  • `/scan <target_network/24>` - Scan a network
  • `/scan example.com` - Scan a host"""
        else:
            lines = [
                "## 📋 Active Security Assessments",
                "",
                f"Found {len(assessments)} active assessment(s):",
                "",
            ]

            for a in assessments[:10]:
                phase_emoji = {
                    "INIT": "🔵",
                    "RECON": "🔍",
                    "PORT_SCAN": "📡",
                    "ENUMERATION": "📊",
                    "VULN_ANALYSIS": "⚠️",
                    "EXPLOITATION": "🎯",
                    "REPORTING": "📝",
                    "COMPLETE": "✅",
                    "ERROR": "❌",
                }.get(a.phase.value, "⚪")

                host_count = len(a.hosts)
                vuln_count = sum(len(h.vulnerabilities) for h in a.hosts)

                lines.append(
                    f"  {phase_emoji} `{a.id[:8]}` | **{a.name}** | "
                    f"{a.phase.value} | {host_count} hosts, {vuln_count} vulns"
                )

            if len(assessments) > 10:
                lines.append(f"  ... and {len(assessments) - 10} more")

            lines.extend([
                "",
                "**Commands:**",
                "  • `/security status <id>` - View details",
                "  • `/security resume <id>` - Continue assessment",
            ])

            content = "\n".join(lines)

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content=content,
        )

    async def _security_status(self, manager, assessment_id: Optional[str]) -> SlashCommandResult:
        """Get status of a specific assessment."""
        if not assessment_id:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content="❌ Please provide an assessment ID: `/security status <id>`",
            )

        # Find assessment by ID prefix
        assessments = await manager.list_active_assessments()
        assessment = None
        for a in assessments:
            if a.id.startswith(assessment_id):
                assessment = a
                break

        if not assessment:
            # Try to load directly
            assessment = await manager.get_assessment(assessment_id)

        if not assessment:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content=f"❌ Assessment not found: `{assessment_id}`",
            )

        summary = await manager.get_assessment_summary(assessment.id)

        # Build severity display
        severity_lines = []
        for sev, count in summary.get("stats", {}).get("severity_distribution", {}).items():
            sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(sev.lower(), "⚪")
            severity_lines.append(f"    {sev_emoji} {sev.upper()}: {count}")

        severity_text = "\n".join(severity_lines) if severity_lines else "    No vulnerabilities found yet"

        content = f"""## 🔒 Assessment Status

**ID:** `{assessment.id[:8]}...`
**Name:** {assessment.name}
**Target:** {assessment.target}
**Phase:** {assessment.phase.value}
**Training Mode:** {'✅ Enabled' if assessment.training_mode else '❌ Disabled'}

**Statistics:**
  • Hosts: {summary['stats']['hosts']}
  • Open Ports: {summary['stats']['ports']}
  • Services: {summary['stats']['services']}
  • Vulnerabilities: {summary['stats']['vulnerabilities']}

**Severity Distribution:**
{severity_text}

**Phase Description:** {summary.get('phase_description', 'N/A')}

**Next Actions:** {', '.join(summary.get('next_actions', [])[:3]) or 'N/A'}

**Commands:**
  • `/security resume {assessment.id[:8]}` - Continue this assessment"""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content=content,
        )

    async def _security_resume(self, manager, assessment_id: Optional[str]) -> SlashCommandResult:
        """Resume a security assessment."""
        if not assessment_id:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content="❌ Please provide an assessment ID: `/security resume <id>`",
            )

        # Find assessment
        assessments = await manager.list_active_assessments()
        assessment = None
        for a in assessments:
            if a.id.startswith(assessment_id):
                assessment = a
                break

        if not assessment:
            assessment = await manager.get_assessment(assessment_id)

        if not assessment:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content=f"❌ Assessment not found: `{assessment_id}`",
            )

        summary = await manager.get_assessment_summary(assessment.id)

        content = f"""## 🔄 Resuming Security Assessment

**Assessment:** {assessment.name}
**ID:** `{assessment.id[:8]}...`
**Current Phase:** {assessment.phase.value}
**Target:** {assessment.target}

**Progress:**
  • Hosts discovered: {summary['stats']['hosts']}
  • Ports scanned: {summary['stats']['ports']}
  • Services enumerated: {summary['stats']['services']}
  • Vulnerabilities found: {summary['stats']['vulnerabilities']}

**Phase Description:** {summary.get('phase_description', 'N/A')}

**Recommended Actions:**
{chr(10).join(f'  • {action}' for action in summary.get('next_actions', [])[:5])}

💡 The agent is ready to continue. Describe your next action or ask for guidance."""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content=content,
        )

    def _security_phases(self, phase_descriptions: dict) -> SlashCommandResult:
        """Show security workflow phases."""
        lines = [
            "## 🔄 Security Assessment Phases",
            "",
            "The security workflow follows these phases:",
            "",
        ]

        phase_emojis = {
            "INIT": "🔵",
            "RECON": "🔍",
            "PORT_SCAN": "📡",
            "ENUMERATION": "📊",
            "VULN_ANALYSIS": "⚠️",
            "EXPLOITATION": "🎯",
            "REPORTING": "📝",
            "COMPLETE": "✅",
            "ERROR": "❌",
        }

        for phase, info in phase_descriptions.items():
            emoji = phase_emojis.get(phase, "⚪")
            desc = info.get("description", "")
            actions = info.get("actions", [])

            lines.append(f"**{emoji} {phase}**")
            lines.append(f"  {desc}")
            if actions:
                lines.append(f"  Actions: {', '.join(actions[:4])}")
            lines.append("")

        lines.extend([
            "**Workflow:**",
            "```",
            "INIT → RECON → PORT_SCAN → ENUMERATION → VULN_ANALYSIS → REPORTING",
            "                                    ↓",
            "                          EXPLOITATION (training mode)",
            "```",
        ])

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content="\n".join(lines),
        )

    async def _handle_unknown(self, args: Optional[str]) -> SlashCommandResult:
        """Handle unknown commands."""
        return SlashCommandResult(
            success=False,
            command_type=CommandType.UNKNOWN,
            content="❓ Unknown command. Type `/help` to see available commands.",
        )


# Module-level instance for easy access (thread-safe)
import threading

_handler_instance: Optional[SlashCommandHandler] = None
_handler_instance_lock = threading.Lock()


def get_slash_command_handler() -> SlashCommandHandler:
    """
    Get or create the global slash command handler instance (thread-safe).

    Returns:
        SlashCommandHandler singleton instance
    """
    global _handler_instance
    if _handler_instance is None:
        with _handler_instance_lock:
            # Double-check after acquiring lock
            if _handler_instance is None:
                _handler_instance = SlashCommandHandler()
    return _handler_instance
