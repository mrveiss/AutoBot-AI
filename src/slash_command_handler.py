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
- #312 - Code Smell: Fix Feature Envy patterns
Created: 2025-01-26
Updated: 2025-12-06 - Refactored to fix Feature Envy with Command pattern
"""

import asyncio
import logging
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)

# Issue #380: Module-level cached category info to avoid repeated dict creation
_CATEGORY_INFO: Dict[str, str] = {
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

# Issue #380: Module-level severity emoji mapping to avoid repeated dict creation
_SEVERITY_EMOJIS: Dict[str, str] = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}


class CommandType(Enum):
    """Supported slash command types."""

    DOCS = "docs"
    HELP = "help"
    STATUS = "status"
    SCAN = "scan"
    SECURITY = "security"
    SECRETS = "secrets"  # Issue #211 - Secrets Management
    UNKNOWN = "unknown"


@dataclass
class SlashCommandResult:
    """Result of executing a slash command."""

    success: bool
    command_type: CommandType
    content: str
    file_paths: List[str] = None

    def __post_init__(self):
        """Initialize default file_paths if not provided."""
        if self.file_paths is None:
            self.file_paths = []


# ============================================================================
# Command Pattern Implementation - Fixes Feature Envy
# ============================================================================


class Command(ABC):
    """
    Base command class following Command pattern.

    Each command encapsulates its own execution logic, preventing
    Feature Envy by keeping behavior with the data it operates on.
    """

    @abstractmethod
    async def execute(self) -> SlashCommandResult:
        """Execute the command and return result."""


class DocsCommand(Command):
    """Documentation browsing command."""

    def __init__(self, args: Optional[str], docs_base_path: Path, doc_categories: dict):
        """Initialize docs command with args and documentation paths."""
        self.args = args
        self.docs_base_path = docs_base_path
        self.doc_categories = doc_categories

    async def execute(self) -> SlashCommandResult:
        """Execute /docs command - list or search documentation."""
        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(self.docs_base_path.exists):
            return SlashCommandResult(
                success=False,
                command_type=CommandType.DOCS,
                content="📁 Documentation directory not found.",
            )

        if not self.args:
            # List all documentation categories
            content = self._list_categories()
            return SlashCommandResult(
                success=True,
                command_type=CommandType.DOCS,
                content=content,
            )

        args_lower = self.args.lower().strip()

        # Check if it's a category request
        if args_lower in self.doc_categories:
            return await self._list_category_docs(args_lower)

        # Search for matching docs
        return await self._search_docs(self.args)

    def _list_categories(self) -> str:
        """Generate a list of documentation categories."""
        lines = [
            "## 📚 AutoBot Documentation",
            "",
            "Available categories (use `/docs <category>` to browse):",
            "",
        ]

        # Issue #380: Use module-level cached _CATEGORY_INFO
        for cat, desc in _CATEGORY_INFO.items():
            if (self.docs_base_path / self.doc_categories[cat]).exists():
                lines.append(f"  • `{cat}` - {desc}")

        lines.extend(
            [
                "",
                "**Quick Access:**",
                "  • `/docs api` - API documentation",
                "  • `/docs developer` - Developer guide",
                "  • `/docs <search term>` - Search all docs",
                "",
                "📄 **Main Index:** `docs/INDEX.md`",
            ]
        )

        return "\n".join(lines)

    async def _list_category_docs(self, category: str) -> SlashCommandResult:
        """List documents in a specific category."""
        cat_path = self.docs_base_path / self.doc_categories[category]

        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(cat_path.exists):
            return SlashCommandResult(
                success=False,
                command_type=CommandType.DOCS,
                content=f"📁 Category '{category}' not found.",
            )

        files = []
        # Issue #358 - avoid blocking
        md_files = await asyncio.to_thread(lambda: sorted(cat_path.glob("*.md")))
        for f in md_files:
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
            lines.extend(
                [
                    "",
                    f"📍 Path: `docs/{self.doc_categories[category]}`",
                ]
            )
            content = "\n".join(lines)

        # Issue #358 - avoid blocking
        all_md_files = await asyncio.to_thread(lambda: list(cat_path.glob("*.md")))
        file_paths = [str(f.relative_to(self.docs_base_path)) for f in all_md_files]

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
        # Issue #358 - avoid blocking
        all_md_files = await asyncio.to_thread(
            lambda: list(self.docs_base_path.rglob("*.md"))
        )
        for md_file in all_md_files:
            # Cache str(md_file).lower() to avoid repeated calls (Issue #624)
            md_file_str_lower = str(md_file).lower()
            # Skip archive directories
            if "archive" in md_file_str_lower or "legacy" in md_file_str_lower:
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

        lines.extend(
            [
                "",
                "💡 Use file browser or read directly for full content.",
            ]
        )

        return SlashCommandResult(
            success=True,
            command_type=CommandType.DOCS,
            content="\n".join(lines),
            file_paths=[str(m) for m in matches[:15]],
        )


class HelpCommand(Command):
    """Help information command."""

    async def execute(self) -> SlashCommandResult:
        """Execute /help command."""
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
| `/secrets` | Manage secrets and credentials |

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

**Secrets Management:**
  • `/secrets list` - List all accessible secrets
  • `/secrets add <name> <type> <value>` - Add a secret
  • `/secrets show <name>` - View a secret's value
  • `/secrets delete <name>` - Delete a secret
  • `/secrets transfer <name>` - Transfer to general scope

**Examples:**
  • `/docs api` - Browse API documentation
  • `/docs redis` - Search for Redis-related docs
  • `/secrets add my-key api_key sk-xxx...` - Add an API key

💬 For general questions, just type normally without a slash command."""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.HELP,
            content=content,
        )


class StatusCommand(Command):
    """System status command."""

    async def execute(self) -> SlashCommandResult:
        """Execute /status command - show system status."""
        # Import here to avoid circular dependencies
        try:
            from backend.services.consolidated_health_service import (
                ConsolidatedHealthService,
            )

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
            logger.warning("Could not get detailed status: %s", e)
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


class ScanCommand(Command):
    """Security scan initiation command."""

    def __init__(self, args: Optional[str]):
        """Initialize scan command with target arguments."""
        self.args = args

    async def execute(self) -> SlashCommandResult:
        """Execute /scan command - Start a new security assessment."""
        if not self.args:
            return self._show_usage()

        # Parse the target and options
        scan_params = self._parse_scan_params(self.args)

        try:
            from src.services.security_workflow_manager import (
                get_security_workflow_manager,
            )

            manager = get_security_workflow_manager()
            assessment = await manager.create_assessment(
                name=scan_params["name"],
                target=scan_params["target"],
                training_mode=scan_params["training_mode"],
            )

            return self._format_scan_result(assessment, scan_params["training_mode"])

        except Exception as e:
            logger.error("Failed to create security assessment: %s", e)
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SCAN,
                content=f"❌ Failed to create assessment: {e}\n\nPlease check the logs for details.",
            )

    def _show_usage(self) -> SlashCommandResult:
        """Show scan command usage."""
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

    def _parse_scan_params(self, args: str) -> dict:
        """Parse scan command parameters."""
        parts = args.split()
        target = parts[0]
        training_mode = "--training" in args.lower()

        # Extract custom name if provided
        assessment_name = f"Assessment: {target}"
        if "--name" in args.lower():
            name_idx = args.lower().find("--name")
            name_part = args[name_idx + 6 :].strip()
            if name_part:
                # Get first quoted string or word
                if name_part.startswith('"'):
                    end_quote = name_part.find('"', 1)
                    if end_quote > 0:
                        assessment_name = name_part[1:end_quote]
                else:
                    assessment_name = name_part.split()[0]

        return {
            "target": target,
            "training_mode": training_mode,
            "name": assessment_name,
        }

    def _format_scan_result(
        self, assessment, training_mode: bool
    ) -> SlashCommandResult:
        """Format scan initiation result."""
        mode_emoji = "🎯" if training_mode else "🛡️"
        mode_text = (
            "Training Mode (exploitation enabled)"
            if training_mode
            else "Safe Mode (no exploitation)"
        )

        content = f"""## {mode_emoji} Security Assessment Started

**Assessment ID:** `{assessment.id[:8]}...`
**Name:** {assessment.name}
**Target:** {assessment.target}
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


class SecurityCommand(Command):
    """Security assessment management command."""

    def __init__(self, args: Optional[str]):
        """Initialize security command with subcommand arguments."""
        self.args = args

    async def execute(self) -> SlashCommandResult:
        """Execute /security command - Manage security assessments."""
        if not self.args:
            return self._show_usage()

        # Parse subcommand
        parts = self.args.strip().split(maxsplit=1)
        subcommand = parts[0].lower()
        sub_args = parts[1] if len(parts) > 1 else None

        try:
            from src.services.security_workflow_manager import (
                PHASE_DESCRIPTIONS,
                get_security_workflow_manager,
            )

            manager = get_security_workflow_manager()

            # Dispatch to appropriate subcommand
            subcommand_handlers = {
                "list": lambda: SecurityListSubcommand(manager).execute(),
                "status": lambda: SecurityStatusSubcommand(manager, sub_args).execute(),
                "resume": lambda: SecurityResumeSubcommand(manager, sub_args).execute(),
                "phases": lambda: SecurityPhasesSubcommand(
                    PHASE_DESCRIPTIONS
                ).execute(),
            }

            handler = subcommand_handlers.get(subcommand)
            if handler:
                return await handler()
            else:
                return SlashCommandResult(
                    success=False,
                    command_type=CommandType.SECURITY,
                    content=f"❓ Unknown subcommand: `{subcommand}`\n\nUse `/security` for available commands.",
                )

        except Exception as e:
            logger.error("Security command failed: %s", e)
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content=f"❌ Security command failed: {e}",
            )

    def _show_usage(self) -> SlashCommandResult:
        """Show security command usage."""
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


class SecurityListSubcommand(Command):
    """List active security assessments."""

    def __init__(self, manager):
        """Initialize list subcommand with security manager."""
        self.manager = manager

    async def execute(self) -> SlashCommandResult:
        """List active security assessments."""
        assessments = await self.manager.list_active_assessments()

        if not assessments:
            content = self._format_empty_list()
        else:
            content = self._format_assessment_list(assessments)

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content=content,
        )

    def _format_empty_list(self) -> str:
        """Format empty assessment list message."""
        return """## 📋 Active Security Assessments

No active assessments found.

**Start a new scan:**
  • `/scan <target_network/24>` - Scan a network
  • `/scan example.com` - Scan a host"""

    def _format_assessment_list(self, assessments: list) -> str:
        """Format assessment list display."""
        lines = [
            "## 📋 Active Security Assessments",
            "",
            f"Found {len(assessments)} active assessment(s):",
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

        for a in assessments[:10]:
            emoji = phase_emojis.get(a.phase.value, "⚪")
            host_count = len(a.hosts)
            vuln_count = sum(len(h.vulnerabilities) for h in a.hosts)

            lines.append(
                f"  {emoji} `{a.id[:8]}` | **{a.name}** | "
                f"{a.phase.value} | {host_count} hosts, {vuln_count} vulns"
            )

        if len(assessments) > 10:
            lines.append(f"  ... and {len(assessments) - 10} more")

        lines.extend(
            [
                "",
                "**Commands:**",
                "  • `/security status <id>` - View details",
                "  • `/security resume <id>` - Continue assessment",
            ]
        )

        return "\n".join(lines)


class SecurityStatusSubcommand(Command):
    """Get status of a specific assessment."""

    def __init__(self, manager, assessment_id: Optional[str]):
        """Initialize status subcommand with manager and assessment ID."""
        self.manager = manager
        self.assessment_id = assessment_id

    async def execute(self) -> SlashCommandResult:
        """Get status of a specific assessment."""
        if not self.assessment_id:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content="❌ Please provide an assessment ID: `/security status <id>`",
            )

        # Find assessment
        assessment = await self._find_assessment(self.assessment_id)
        if not assessment:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content=f"❌ Assessment not found: `{self.assessment_id}`",
            )

        summary = await self.manager.get_assessment_summary(assessment.id)
        content = self._format_status(assessment, summary)

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content=content,
        )

    async def _find_assessment(self, assessment_id: str):
        """Find assessment by ID or prefix."""
        assessments = await self.manager.list_active_assessments()
        for a in assessments:
            if a.id.startswith(assessment_id):
                return a

        # Try to load directly
        return await self.manager.get_assessment(assessment_id)

    def _format_status(self, assessment, summary: dict) -> str:
        """Format assessment status display."""
        # Build severity display
        severity_lines = []
        for sev, count in (
            summary.get("stats", {}).get("severity_distribution", {}).items()
        ):
            sev_emoji = _SEVERITY_EMOJIS.get(sev.lower(), "⚪")
            severity_lines.append(f"    {sev_emoji} {sev.upper()}: {count}")

        severity_text = (
            "\n".join(severity_lines)
            if severity_lines
            else "    No vulnerabilities found yet"
        )

        return f"""## 🔒 Assessment Status

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


class SecurityResumeSubcommand(Command):
    """Resume a security assessment."""

    def __init__(self, manager, assessment_id: Optional[str]):
        """Initialize resume subcommand with manager and assessment ID."""
        self.manager = manager
        self.assessment_id = assessment_id

    async def execute(self) -> SlashCommandResult:
        """Resume a security assessment."""
        if not self.assessment_id:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content="❌ Please provide an assessment ID: `/security resume <id>`",
            )

        # Find assessment
        assessment = await self._find_assessment(self.assessment_id)
        if not assessment:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECURITY,
                content=f"❌ Assessment not found: `{self.assessment_id}`",
            )

        summary = await self.manager.get_assessment_summary(assessment.id)
        content = self._format_resume(assessment, summary)

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content=content,
        )

    async def _find_assessment(self, assessment_id: str):
        """Find assessment by ID or prefix."""
        assessments = await self.manager.list_active_assessments()
        for a in assessments:
            if a.id.startswith(assessment_id):
                return a

        # Try to load directly
        return await self.manager.get_assessment(assessment_id)

    def _format_resume(self, assessment, summary: dict) -> str:
        """Format resume message."""
        return f"""## 🔄 Resuming Security Assessment

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


class SecurityPhasesSubcommand(Command):
    """Show security workflow phases."""

    def __init__(self, phase_descriptions: dict):
        """Initialize security phases subcommand with phase descriptions mapping."""
        self.phase_descriptions = phase_descriptions

    async def execute(self) -> SlashCommandResult:
        """Show security workflow phases."""
        content = self._format_phases()
        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECURITY,
            content=content,
        )

    def _format_phases(self) -> str:
        """Format phases display."""
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

        for phase, info in self.phase_descriptions.items():
            emoji = phase_emojis.get(phase, "⚪")
            desc = info.get("description", "")
            actions = info.get("actions", [])

            lines.append(f"**{emoji} {phase}**")
            lines.append(f"  {desc}")
            if actions:
                lines.append(f"  Actions: {', '.join(actions[:4])}")
            lines.append("")

        lines.extend(
            [
                "**Workflow:**",
                "```",
                "INIT → RECON → PORT_SCAN → ENUMERATION → VULN_ANALYSIS → REPORTING",
                "                                    ↓",
                "                          EXPLOITATION (training mode)",
                "```",
            ]
        )

        return "\n".join(lines)


# ============================================================================
# Secrets Command Implementation (Issue #211)
# ============================================================================


class SecretsCommand(Command):
    """Secrets management command - Issue #211."""

    def __init__(self, args: Optional[str], chat_id: Optional[str] = None):
        """Initialize secrets command with subcommand arguments."""
        self.args = args
        self.chat_id = chat_id

    async def execute(self) -> SlashCommandResult:
        """Execute /secrets command - Manage secrets via chat."""
        if not self.args:
            return self._show_usage()

        # Parse subcommand
        parts = self.args.strip().split(maxsplit=1)
        subcommand = parts[0].lower()
        sub_args = parts[1] if len(parts) > 1 else None

        try:
            from backend.api.secrets import secrets_manager

            # Dispatch to appropriate subcommand
            subcommand_handlers = {
                "list": lambda: SecretsListSubcommand(
                    secrets_manager, self.chat_id
                ).execute(),
                "add": lambda: SecretsAddSubcommand(
                    secrets_manager, sub_args, self.chat_id
                ).execute(),
                "show": lambda: SecretsShowSubcommand(
                    secrets_manager, sub_args, self.chat_id
                ).execute(),
                "delete": lambda: SecretsDeleteSubcommand(
                    secrets_manager, sub_args, self.chat_id
                ).execute(),
                "transfer": lambda: SecretsTransferSubcommand(
                    secrets_manager, sub_args, self.chat_id
                ).execute(),
                "types": lambda: SecretsTypesSubcommand().execute(),
            }

            handler = subcommand_handlers.get(subcommand)
            if handler:
                return await handler()
            else:
                return SlashCommandResult(
                    success=False,
                    command_type=CommandType.SECRETS,
                    content=f"❓ Unknown subcommand: `{subcommand}`\n\nUse `/secrets` for available commands.",
                )

        except Exception as e:
            logger.error("Secrets command failed: %s", e)
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Secrets command failed: {e}",
            )

    def _show_usage(self) -> SlashCommandResult:
        """Show secrets command usage."""
        content = """## 🔐 Secrets Management Commands

**Usage:** `/secrets <subcommand> [options]`

**Subcommands:**

| Command | Description |
|---------|-------------|
| `/secrets list` | List all accessible secrets |
| `/secrets add <name> <type> <value>` | Add a new secret |
| `/secrets show <name>` | Show a secret's value |
| `/secrets delete <name>` | Delete a secret |
| `/secrets transfer <name> [to-general]` | Transfer secret scope |
| `/secrets types` | Show available secret types |

**Secret Types:**
  • `ssh_key` - SSH private/public keys
  • `password` - Passwords and passphrases
  • `api_key` - API keys for services
  • `token` - Authentication tokens
  • `certificate` - X.509 certificates
  • `database_url` - Database connection strings

**Examples:**
  • `/secrets add my-api-key api_key sk-xxx...` - Add an API key
  • `/secrets list` - List all secrets
  • `/secrets show my-api-key` - View secret value
  • `/secrets transfer my-api-key to-general` - Move to general scope

**Scopes:**
  • **Chat-scoped**: Only accessible in current conversation (default)
  • **General**: Accessible across all conversations"""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECRETS,
            content=content,
        )


class SecretsListSubcommand(Command):
    """List accessible secrets."""

    def __init__(self, manager, chat_id: Optional[str]):
        """Initialize list subcommand with secrets manager."""
        self.manager = manager
        self.chat_id = chat_id

    async def execute(self) -> SlashCommandResult:
        """List accessible secrets."""
        secrets = self.manager.list_secrets(chat_id=self.chat_id)

        if not secrets:
            content = self._format_empty_list()
        else:
            content = self._format_secrets_list(secrets)

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECRETS,
            content=content,
        )

    def _format_empty_list(self) -> str:
        """Format empty secrets list message."""
        return """## 🔐 Your Secrets

No secrets found.

**Add a secret:**
  • `/secrets add <name> <type> <value>`
  • Example: `/secrets add my-key api_key sk-xxx...`"""

    def _format_secrets_list(self, secrets: list) -> str:
        """Format secrets list display."""
        lines = [
            "## 🔐 Your Secrets",
            "",
            f"Found {len(secrets)} secret(s):",
            "",
        ]

        type_emojis = {
            "ssh_key": "🔑",
            "password": "🔒",
            "api_key": "🔌",
            "token": "🎫",
            "certificate": "📜",
            "database_url": "🗄️",
            "other": "📦",
        }

        for s in secrets[:15]:
            emoji = type_emojis.get(s.get("type", "other"), "📦")
            scope = "💬" if s.get("scope") == "chat" else "🌐"
            name = s.get("name", "unknown")
            secret_type = s.get("type", "unknown")
            lines.append(f"  {emoji} `{name}` ({secret_type}) {scope}")

        if len(secrets) > 15:
            lines.append(f"  ... and {len(secrets) - 15} more")

        lines.extend(
            [
                "",
                "**Scope:** 💬 = Chat-scoped, 🌐 = General",
                "",
                "**Commands:**",
                "  • `/secrets show <name>` - View value",
                "  • `/secrets delete <name>` - Remove secret",
            ]
        )

        return "\n".join(lines)


class SecretsAddSubcommand(Command):
    """Add a new secret."""

    # Issue #620: Class constant for valid secret types
    VALID_SECRET_TYPES = [
        "ssh_key",
        "password",
        "api_key",
        "token",
        "certificate",
        "database_url",
        "other",
    ]

    def __init__(self, manager, args: Optional[str], chat_id: Optional[str]):
        """Initialize add subcommand with manager and arguments."""
        self.manager = manager
        self.args = args
        self.chat_id = chat_id

    def _parse_and_validate_args(self) -> Optional[SlashCommandResult]:
        """
        Parse and validate arguments for add command.

        Issue #620: Extracted from execute to reduce function length.

        Returns:
            SlashCommandResult on error, None on success (sets self._parsed_args)
        """
        if not self.args:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=(
                    "❌ Usage: `/secrets add <name> <type> <value>`\n\n"
                    "Example: `/secrets add my-key api_key sk-xxx...`"
                ),
            )

        parts = self.args.split(maxsplit=2)
        if len(parts) < 3:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content="❌ Missing arguments. Usage: `/secrets add <name> <type> <value>`",
            )

        name, secret_type, value = parts

        if secret_type not in self.VALID_SECRET_TYPES:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Invalid type `{secret_type}`.\n\nValid types: {', '.join(self.VALID_SECRET_TYPES)}",
            )

        self._parsed_name = name
        self._parsed_type = secret_type
        self._parsed_value = value
        return None

    def _build_success_response(
        self, name: str, secret_type: str, scope
    ) -> SlashCommandResult:
        """
        Build success response for secret creation.

        Issue #620: Extracted from execute to reduce function length.
        """
        from backend.api.secrets import SecretScope

        scope_text = "chat-scoped 💬" if scope == SecretScope.CHAT else "general 🌐"
        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECRETS,
            content=f"""## ✅ Secret Created

**Name:** `{name}`
**Type:** {secret_type}
**Scope:** {scope_text}

Your secret has been securely encrypted and stored.

**Next steps:**
  • `/secrets list` - View all secrets
  • `/secrets show {name}` - View the value""",
        )

    async def execute(self) -> SlashCommandResult:
        """Add a new secret. Issue #620: Refactored to use helper methods."""
        # Validate and parse arguments - Issue #620
        validation_error = self._parse_and_validate_args()
        if validation_error:
            return validation_error

        try:
            from backend.api.secrets import SecretCreateRequest, SecretScope, SecretType

            scope = SecretScope.CHAT if self.chat_id else SecretScope.GENERAL
            request = SecretCreateRequest(
                name=self._parsed_name,
                type=SecretType(self._parsed_type),
                scope=scope,
                value=self._parsed_value,
                chat_id=self.chat_id,
                description="Created via /secrets add command",
            )

            self.manager.create_secret(request)
            return self._build_success_response(
                self._parsed_name, self._parsed_type, scope
            )

        except ValueError as e:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Failed to create secret: {e}",
            )
        except Exception as e:
            logger.error("Failed to create secret: %s", e)
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Failed to create secret: {e}",
            )


class SecretsShowSubcommand(Command):
    """Show a secret's value."""

    def __init__(self, manager, secret_name: Optional[str], chat_id: Optional[str]):
        """Initialize show subcommand."""
        self.manager = manager
        self.secret_name = secret_name
        self.chat_id = chat_id

    async def execute(self) -> SlashCommandResult:
        """Show a secret's value."""
        if not self.secret_name:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content="❌ Please provide a secret name: `/secrets show <name>`",
            )

        # Find the secret by name
        secrets = self.manager.list_secrets(chat_id=self.chat_id)
        target_secret = None

        for s in secrets:
            if s.get("name") == self.secret_name:
                target_secret = s
                break

        if not target_secret:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Secret not found: `{self.secret_name}`",
            )

        try:
            # Get the full secret with value
            full_secret = self.manager.get_secret(
                target_secret["id"],
                chat_id=self.chat_id,
            )

            if not full_secret:
                return SlashCommandResult(
                    success=False,
                    command_type=CommandType.SECRETS,
                    content=f"❌ Could not retrieve secret: `{self.secret_name}`",
                )

            # Mask value for display (show first/last 4 chars)
            value = full_secret.get("value", "")
            if len(value) > 12:
                masked = f"{value[:4]}...{value[-4:]}"
            else:
                masked = "****" if value else "(empty)"

            # Build response with metadata only (no full value for security)
            description = full_secret.get("description", "")
            desc_line = f"\n**Description:** {description}" if description else ""

            return SlashCommandResult(
                success=True,
                command_type=CommandType.SECRETS,
                content=f"""## 🔐 Secret: {self.secret_name}

**Type:** {full_secret.get('type', 'unknown')}
**Scope:** {'Chat' if full_secret.get('scope') == 'chat' else 'General'}
**Value (masked):** `{masked}`{desc_line}

💡 Use `/secrets copy {self.secret_name}` to copy the full value to clipboard.
📋 The full value is NOT displayed to protect against chat history exposure.""",
            )

        except PermissionError:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Access denied to secret: `{self.secret_name}`",
            )


class SecretsDeleteSubcommand(Command):
    """Delete a secret."""

    def __init__(self, manager, secret_name: Optional[str], chat_id: Optional[str]):
        """Initialize delete subcommand."""
        self.manager = manager
        self.secret_name = secret_name
        self.chat_id = chat_id

    async def execute(self) -> SlashCommandResult:
        """Delete a secret."""
        if not self.secret_name:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content="❌ Please provide a secret name: `/secrets delete <name>`",
            )

        # Find the secret by name
        secrets = self.manager.list_secrets(chat_id=self.chat_id)
        target_secret = None

        for s in secrets:
            if s.get("name") == self.secret_name:
                target_secret = s
                break

        if not target_secret:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Secret not found: `{self.secret_name}`",
            )

        try:
            success = self.manager.delete_secret(
                target_secret["id"],
                chat_id=self.chat_id,
            )

            if success:
                return SlashCommandResult(
                    success=True,
                    command_type=CommandType.SECRETS,
                    content=f"## ✅ Secret Deleted\n\n`{self.secret_name}` has been permanently removed.",
                )
            else:
                return SlashCommandResult(
                    success=False,
                    command_type=CommandType.SECRETS,
                    content=f"❌ Failed to delete secret: `{self.secret_name}`",
                )

        except PermissionError:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Access denied: Cannot delete `{self.secret_name}`",
            )


class SecretsTransferSubcommand(Command):
    """Transfer a secret between scopes."""

    def __init__(self, manager, args: Optional[str], chat_id: Optional[str]):
        """Initialize transfer subcommand."""
        self.manager = manager
        self.args = args
        self.chat_id = chat_id

    async def execute(self) -> SlashCommandResult:
        """Transfer a secret between scopes."""
        if not self.args:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content="❌ Usage: `/secrets transfer <name> [to-general|to-chat]`",
            )

        parts = self.args.split()
        secret_name = parts[0]
        target_scope = parts[1] if len(parts) > 1 else "to-general"

        # Find the secret by name
        secrets = self.manager.list_secrets(chat_id=self.chat_id)
        target_secret = None

        for s in secrets:
            if s.get("name") == secret_name:
                target_secret = s
                break

        if not target_secret:
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Secret not found: `{secret_name}`",
            )

        try:
            from backend.api.secrets import SecretScope, SecretTransferRequest

            if target_scope == "to-general":
                new_scope = SecretScope.GENERAL
                scope_text = "General 🌐"
            else:
                new_scope = SecretScope.CHAT
                scope_text = "Chat 💬"

            request = SecretTransferRequest(
                secret_ids=[target_secret["id"]],
                target_scope=new_scope,
                target_chat_id=self.chat_id if new_scope == SecretScope.CHAT else None,
            )

            result = self.manager.transfer_secrets(request, chat_id=self.chat_id)

            if result.get("transferred"):
                return SlashCommandResult(
                    success=True,
                    command_type=CommandType.SECRETS,
                    content=f"## ✅ Secret Transferred\n\n`{secret_name}` is now {scope_text}.",
                )
            else:
                return SlashCommandResult(
                    success=False,
                    command_type=CommandType.SECRETS,
                    content=f"❌ Failed to transfer secret: {result.get('failed', [])}",
                )

        except Exception as e:
            logger.error("Failed to transfer secret: %s", e)
            return SlashCommandResult(
                success=False,
                command_type=CommandType.SECRETS,
                content=f"❌ Failed to transfer secret: {e}",
            )


class SecretsTypesSubcommand(Command):
    """Show available secret types."""

    async def execute(self) -> SlashCommandResult:
        """Show available secret types."""
        content = """## 🔐 Secret Types

| Type | Description | Use Case |
|------|-------------|----------|
| `ssh_key` | SSH private/public keys | Remote server access |
| `password` | Passwords & passphrases | Authentication |
| `api_key` | API keys for services | External API access |
| `token` | Authentication tokens | OAuth, JWT tokens |
| `certificate` | X.509 certificates | TLS/SSL, signing |
| `database_url` | Database connection strings | Database access |
| `other` | Other sensitive data | Custom use |

**Usage:**
```
/secrets add <name> <type> <value>
```

**Examples:**
  • `/secrets add openai-key api_key sk-xxx...`
  • `/secrets add server-ssh ssh_key "-----BEGIN..."`
  • `/secrets add db-prod database_url postgres://...`"""

        return SlashCommandResult(
            success=True,
            command_type=CommandType.SECRETS,
            content=content,
        )


class UnknownCommand(Command):
    """Handler for unknown commands."""

    async def execute(self) -> SlashCommandResult:
        """Handle unknown commands."""
        return SlashCommandResult(
            success=False,
            command_type=CommandType.UNKNOWN,
            content="❓ Unknown command. Type `/help` to see available commands.",
        )


# ============================================================================
# Main Handler - Delegates to Command Objects
# ============================================================================


class SlashCommandHandler:
    """
    Handler for slash commands in the chat interface.

    Detects and processes commands starting with '/' character,
    providing quick access to documentation and system features.

    Refactored to use Command pattern to fix Feature Envy code smells.
    Each command type is now a separate class that encapsulates its
    own execution logic.
    """

    def __init__(self, docs_base_path: str = "docs"):
        """
        Initialize the slash command handler.

        Args:
            docs_base_path: Base path to documentation directory
        """
        self.docs_base_path = Path(docs_base_path)
        self._command_pattern = re.compile(r"^/(\w+)(?:\s+(.*))?$", re.IGNORECASE)

        # Current chat context for secrets (Issue #211)
        self.current_chat_id: Optional[str] = None

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

        logger.info(
            "SlashCommandHandler initialized with docs path: %s", docs_base_path
        )

    def set_chat_context(self, chat_id: Optional[str]) -> None:
        """Set the current chat context for chat-scoped commands (Issue #211).

        Args:
            chat_id: Current chat ID or None for general context
        """
        self.current_chat_id = chat_id

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
            # Secrets management commands (#211)
            "secrets": CommandType.SECRETS,
            "secret": CommandType.SECRETS,
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

        # Create appropriate command object - Tell, Don't Ask
        command = self._create_command(cmd_type, args)
        return await command.execute()

    def _get_command_factories(self) -> Dict[CommandType, callable]:
        """Get command type to factory mapping (Issue #315 - dispatch table)."""
        return {
            CommandType.DOCS: lambda args: DocsCommand(
                args, self.docs_base_path, self.doc_categories
            ),
            CommandType.HELP: lambda args: HelpCommand(),
            CommandType.STATUS: lambda args: StatusCommand(),
            CommandType.SCAN: lambda args: ScanCommand(args),
            CommandType.SECURITY: lambda args: SecurityCommand(args),
            # Issue #211 - Secrets management
            CommandType.SECRETS: lambda args: SecretsCommand(
                args, self.current_chat_id
            ),
        }

    def _create_command(self, cmd_type: CommandType, args: Optional[str]) -> Command:
        """
        Create the appropriate command object (Issue #315 - refactored depth 5 to 2).

        Factory method that encapsulates command creation logic.
        """
        factories = self._get_command_factories()
        if cmd_type in factories:
            return factories[cmd_type](args)
        return UnknownCommand()


# Module-level instance for easy access (thread-safe)
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
