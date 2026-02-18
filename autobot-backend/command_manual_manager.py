# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Manual Manager for AutoBot

This module handles the ingestion, storage, and retrieval of command manuals
from the system's man pages into the knowledge base for enhanced command assistance.
"""

import json
import logging
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Pre-compiled regex for section header detection (Issue #380)
_SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z\s]+$")
_RELATED_COMMAND_RE = re.compile(r"\b(\w+)\(\d+\)")
_OPTION_LINE_RE = re.compile(r"^\s*(-\w|--\w+)")
_OPTION_EXTRACT_RE = re.compile(r"^\s*((?:-\w|--\w+)(?:\s*,\s*(?:-\w|--\w+))*)")
_SECTION_NUMBER_RE = re.compile(r"\((\d+)\)")


@dataclass
class CommandManual:
    """Data class for storing command manual information."""

    command_name: str
    description: str
    syntax: str
    common_options: List[str]
    examples: List[str]
    related_commands: List[str]
    risk_level: str  # LOW, MEDIUM, HIGH
    category: str  # file_operations, network, system, etc.
    manual_text: str  # Full manual text for reference
    section: int  # Manual section (1-8)


class CommandManualManager:
    """Manages command manuals in the knowledge base."""

    def __init__(self, db_path: str = "data/knowledge_base.db"):
        """Initialize the Command Manual Manager.

        Args:
            db_path: Path to the SQLite database
        """
        self.db_path = db_path
        self.risk_patterns = self._load_risk_patterns()
        self.category_patterns = self._load_category_patterns()
        self._initialize_database()

    def _initialize_database(self):
        """Initialize the command_manuals table in the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS command_manuals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        command_name TEXT UNIQUE NOT NULL,
                        description TEXT,
                        syntax TEXT,
                        common_options TEXT,  -- JSON array
                        examples TEXT,        -- JSON array
                        related_commands TEXT, -- JSON array
                        risk_level TEXT,
                        category TEXT,
                        manual_text TEXT,
                        section INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Create index for faster searches
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_command_name
                    ON command_manuals(command_name)
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_category
                    ON command_manuals(category)
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_risk_level
                    ON command_manuals(risk_level)
                """
                )

                conn.commit()
                logger.info("Command manuals database initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize command manuals database: %s", e)
            raise

    def _get_high_risk_commands(self) -> List[str]:
        """Get list of high-risk commands (destructive/privileged)."""
        return [
            "rm",
            "rmdir",
            "dd",
            "mkfs",
            "fdisk",
            "parted",
            "sudo",
            "su",
            "chmod",
            "chown",
            "kill",
            "killall",
            "halt",
            "shutdown",
            "reboot",
            "init",
            "systemctl",
            "service",
            "mount",
            "umount",
            "crontab",
            "at",
        ]

    def _get_medium_risk_commands(self) -> List[str]:
        """Get list of medium-risk commands (network/package operations)."""
        return [
            "mv",
            "cp",
            "tar",
            "gzip",
            "gunzip",
            "zip",
            "unzip",
            "wget",
            "curl",
            "ssh",
            "scp",
            "rsync",
            "netstat",
            "ss",
            "iptables",
            "ufw",
            "systemd",
            "docker",
            "git",
            "npm",
            "pip",
            "apt",
            "yum",
            "dn",
        ]

    def _get_low_risk_commands(self) -> List[str]:
        """Get list of low-risk commands (read-only/informational)."""
        return [
            "ls",
            "cd",
            "pwd",
            "cat",
            "less",
            "more",
            "head",
            "tail",
            "grep",
            "find",
            "locate",
            "which",
            "whereis",
            "man",
            "info",
            "help",
            "ps",
            "top",
            "htop",
            "free",
            "d",
            "du",
            "uptime",
            "whoami",
            "id",
            "groups",
            "date",
            "cal",
            "echo",
            "print",
            "wc",
            "sort",
            "uniq",
            "cut",
            "awk",
            "sed",
            "tr",
            "basename",
            "dirname",
            "realpath",
            "ifconfig",
            "ip",
            "ping",
            "traceroute",
            "nslookup",
            "dig",
            "history",
        ]

    def _load_risk_patterns(self) -> Dict[str, List[str]]:
        """Load patterns for determining command risk levels."""
        return {
            "HIGH": self._get_high_risk_commands(),
            "MEDIUM": self._get_medium_risk_commands(),
            "LOW": self._get_low_risk_commands(),
        }

    def _get_file_operation_commands(self) -> List[str]:
        """Get file operation commands for categorization."""
        return [
            "ls",
            "cd",
            "pwd",
            "mkdir",
            "rmdir",
            "rm",
            "cp",
            "mv",
            "cat",
            "less",
            "more",
            "head",
            "tail",
            "touch",
            "ln",
            "find",
            "locate",
            "which",
            "whereis",
            "file",
            "stat",
            "chmod",
            "chown",
            "chgrp",
            "umask",
            "tar",
            "gzip",
            "gunzip",
            "zip",
            "unzip",
            "basename",
            "dirname",
        ]

    def _get_text_processing_commands(self) -> List[str]:
        """Get text processing commands for categorization."""
        return [
            "grep",
            "awk",
            "sed",
            "tr",
            "cut",
            "sort",
            "uniq",
            "wc",
            "dif",
            "comm",
            "join",
            "paste",
            "fmt",
            "fold",
            "expand",
            "unexpand",
            "split",
            "csplit",
        ]

    def _get_network_commands(self) -> List[str]:
        """Get network commands for categorization."""
        return [
            "ping",
            "traceroute",
            "netstat",
            "ss",
            "ifconfig",
            "ip",
            "route",
            "arp",
            "wget",
            "curl",
            "ssh",
            "scp",
            "rsync",
            "ftp",
            "sftp",
            "nc",
            "nmap",
            "tcpdump",
            "wireshark",
            "iptables",
            "ufw",
            "nslookup",
            "dig",
        ]

    def _get_process_management_commands(self) -> List[str]:
        """Get process management commands for categorization."""
        return [
            "ps",
            "top",
            "htop",
            "jobs",
            "bg",
            "fg",
            "nohup",
            "kill",
            "killall",
            "pgrep",
            "pkill",
            "pido",
            "nice",
            "renice",
            "screen",
            "tmux",
        ]

    def _get_system_info_commands(self) -> List[str]:
        """Get system info commands for categorization."""
        return [
            "uname",
            "whoami",
            "id",
            "groups",
            "w",
            "who",
            "uptime",
            "free",
            "d",
            "du",
            "lscpu",
            "lsmem",
            "lsblk",
            "lsusb",
            "lspci",
            "dmidecode",
            "lshw",
        ]

    def _get_system_control_commands(self) -> List[str]:
        """Get system control commands for categorization."""
        return [
            "sudo",
            "su",
            "systemctl",
            "service",
            "mount",
            "umount",
            "halt",
            "shutdown",
            "reboot",
            "init",
            "crontab",
            "at",
            "chkconfig",
            "update-rc.d",
        ]

    def _get_package_management_commands(self) -> List[str]:
        """Get package management commands for categorization."""
        return [
            "apt",
            "apt-get",
            "dpkg",
            "yum",
            "dn",
            "rpm",
            "zypper",
            "pacman",
            "brew",
            "snap",
            "flatpak",
            "pip",
            "npm",
            "yarn",
            "gem",
            "cargo",
        ]

    def _get_development_commands(self) -> List[str]:
        """Get development commands for categorization."""
        return [
            "git",
            "svn",
            "make",
            "cmake",
            "gcc",
            "g++",
            "clang",
            "python",
            "node",
            "java",
            "javac",
            "ruby",
            "go",
            "rust",
            "docker",
            "kubectl",
        ]

    def _load_category_patterns(self) -> Dict[str, List[str]]:
        """Load patterns for categorizing commands."""
        return {
            "file_operations": self._get_file_operation_commands(),
            "text_processing": self._get_text_processing_commands(),
            "network": self._get_network_commands(),
            "process_management": self._get_process_management_commands(),
            "system_info": self._get_system_info_commands(),
            "system_control": self._get_system_control_commands(),
            "package_management": self._get_package_management_commands(),
            "development": self._get_development_commands(),
        }

    def _get_high_risk_indicators(self) -> List[str]:
        """Get indicators suggesting high risk in manual text."""
        return [
            "delete",
            "remove",
            "destroy",
            "format",
            "partition",
            "overwrite",
            "irreversible",
            "permanent",
            "dangerous",
            "root",
            "administrator",
            "privilege",
            "system file",
        ]

    def _get_medium_risk_indicators(self) -> List[str]:
        """Get indicators suggesting medium risk in manual text."""
        return [
            "modify",
            "change",
            "update",
            "install",
            "network",
            "connection",
            "download",
            "upload",
            "transfer",
        ]

    def _analyze_risk_from_text(self, manual_text: str) -> str:
        """Analyze manual text for risk indicators and return risk level."""
        manual_lower = manual_text.lower()
        high_indicators = self._get_high_risk_indicators()
        medium_indicators = self._get_medium_risk_indicators()

        high_count = sum(1 for ind in high_indicators if ind in manual_lower)
        medium_count = sum(1 for ind in medium_indicators if ind in manual_lower)

        if high_count >= 2:
            return "HIGH"
        elif medium_count >= 2 or high_count >= 1:
            return "MEDIUM"
        return "LOW"

    def _determine_risk_level(self, command_name: str, manual_text: str) -> str:
        """Determine the risk level of a command."""
        command_base = command_name.split()[0] if command_name else ""

        # Check explicit risk patterns first
        for risk_level, patterns in self.risk_patterns.items():
            if command_base in patterns:
                return risk_level

        # Fall back to text analysis
        return self._analyze_risk_from_text(manual_text)

    def _determine_category(self, command_name: str, manual_text: str) -> str:
        """Determine the category of a command.

        Args:
            command_name: Name of the command
            manual_text: Full manual text

        Returns:
            Category name
        """
        command_base = command_name.split()[0] if command_name else ""

        # Check explicit category patterns
        for category, patterns in self.category_patterns.items():
            if command_base in patterns:
                return category

        # Analyze manual text for category indicators
        manual_lower = manual_text.lower()

        category_keywords = {
            "file_operations": ["file", "directory", "folder", "path"],
            "text_processing": ["text", "string", "pattern", "search"],
            "network": ["network", "internet", "connection", "protocol"],
            "process_management": ["process", "job", "task", "signal"],
            "system_info": ["system", "information", "status", "display"],
            "system_control": ["control", "manage", "configure", "admin"],
            "package_management": ["package", "install", "repository"],
            "development": ["development", "programming", "code", "build"],
        }

        best_category = "general"
        best_score = 0

        for category, keywords in category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in manual_lower)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    def _parse_manual_text(self, command_name: str, manual_text: str) -> CommandManual:
        """Parse manual text and extract structured information.

        Args:
            command_name: Name of the command
            manual_text: Raw manual text

        Returns:
            CommandManual object with parsed information
        """
        lines = manual_text.split("\n")

        # Extract different sections using specialized methods
        description = self._extract_description(command_name, lines)
        syntax = self._extract_syntax(command_name, lines)
        examples = self._extract_examples(command_name, lines)
        common_options = self._extract_common_options(lines)
        related_commands = self._extract_related_commands(lines)
        section = self._extract_section_number(manual_text)

        # Determine classification
        risk_level = self._determine_risk_level(command_name, manual_text)
        category = self._determine_category(command_name, manual_text)

        return CommandManual(
            command_name=command_name,
            description=description or f"System command: {command_name}",
            syntax=syntax or f"{command_name} [options]",
            common_options=common_options[:10],  # Limit to top 10 options
            examples=examples[:5],  # Limit to 5 examples
            related_commands=list(set(related_commands))[:10],  # Unique, limit 10
            risk_level=risk_level,
            category=category,
            manual_text=manual_text,
            section=section,
        )

    def _extract_description(self, command_name: str, lines: List[str]) -> str:
        """Extract description from NAME section of manual.

        Args:
            command_name: Name of the command
            lines: Manual text lines

        Returns:
            Extracted description
        """
        description = ""
        in_name_section = False

        for line in lines:
            line = line.strip()

            if _SECTION_HEADER_RE.match(line):
                in_name_section = line.startswith("NAME")
                continue

            if in_name_section and line and not description:
                # Remove command name and dash, keep description
                desc_match = re.search(
                    rf"{re.escape(command_name)}\s*[-–]\s*(.+)", line
                )
                if desc_match:
                    description = desc_match.group(1)
                elif " - " in line:
                    description = line.split(" - ", 1)[1]
                elif line:
                    description = line

        return description

    def _extract_syntax(self, command_name: str, lines: List[str]) -> str:
        """Extract syntax from SYNOPSIS section of manual.

        Args:
            command_name: Name of the command
            lines: Manual text lines

        Returns:
            Extracted syntax
        """
        syntax = ""
        in_synopsis_section = False

        for line in lines:
            line = line.strip()

            if _SECTION_HEADER_RE.match(line):
                in_synopsis_section = line.startswith("SYNOPSIS")
                continue

            if in_synopsis_section and line and not syntax:
                if command_name in line:
                    syntax = line
                    break

        return syntax

    def _extract_examples(self, command_name: str, lines: List[str]) -> List[str]:
        """Extract examples from EXAMPLES section of manual.

        Args:
            command_name: Name of the command
            lines: Manual text lines

        Returns:
            List of extracted examples
        """
        examples = []
        in_examples_section = False

        for line in lines:
            line = line.strip()

            if _SECTION_HEADER_RE.match(line):
                in_examples_section = line.startswith("EXAMPLES")
                continue

            if in_examples_section and line:
                if line.startswith(command_name) or line.startswith("$"):
                    examples.append(line)

        return examples

    def _extract_common_options(self, lines: List[str]) -> List[str]:
        """Extract common options from manual text.

        Args:
            lines: Manual text lines

        Returns:
            List of common options
        """
        common_options = []

        for line in lines:
            # Use pre-compiled patterns (Issue #380)
            if _OPTION_LINE_RE.match(line):
                option_match = _OPTION_EXTRACT_RE.match(line)
                if option_match:
                    common_options.append(option_match.group(1))

        return common_options

    def _extract_related_commands(self, lines: List[str]) -> List[str]:
        """Extract related commands from SEE ALSO section.

        Args:
            lines: Manual text lines

        Returns:
            List of related command names
        """
        related_commands = []
        in_see_also_section = False

        for line in lines:
            line = line.strip()

            if _SECTION_HEADER_RE.match(line):
                in_see_also_section = line.startswith("SEE ALSO")
                continue

            if in_see_also_section and line:
                # Extract command names (format: command(1), command(8), etc.)
                related_matches = _RELATED_COMMAND_RE.findall(line)
                related_commands.extend(related_matches)

        return related_commands

    def _extract_section_number(self, manual_text: str) -> int:
        """Extract section number from manual header.

        Args:
            manual_text: Full manual text

        Returns:
            Section number (defaults to 1)
        """
        # Use pre-compiled pattern (Issue #380)
        section_match = _SECTION_NUMBER_RE.search(manual_text[:200])
        if section_match:
            return int(section_match.group(1))
        return 1

    def get_manual_text(self, command_name: str) -> Optional[str]:
        """Get manual text for a command using the man command.

        Args:
            command_name: Name of the command

        Returns:
            Manual text or None if not found
        """
        try:
            result = subprocess.run(
                ["man", command_name], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning("No manual found for command: %s", command_name)
                return None

        except subprocess.TimeoutExpired:
            logger.error("Timeout getting manual for command: %s", command_name)
            return None
        except Exception as e:
            logger.error("Error getting manual for command %s: %s", command_name, e)
            return None

    def store_manual(self, command_manual: CommandManual) -> bool:
        """Store a command manual in the database.

        Args:
            command_manual: CommandManual object to store

        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO command_manuals (
                        command_name, description, syntax, common_options,
                        examples, related_commands, risk_level, category,
                        manual_text, section, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (
                        command_manual.command_name,
                        command_manual.description,
                        command_manual.syntax,
                        json.dumps(command_manual.common_options),
                        json.dumps(command_manual.examples),
                        json.dumps(command_manual.related_commands),
                        command_manual.risk_level,
                        command_manual.category,
                        command_manual.manual_text,
                        command_manual.section,
                    ),
                )
                conn.commit()
                logger.info(
                    "Stored manual for command: %s", command_manual.command_name
                )
                return True

        except Exception as e:
            logger.error(
                f"Failed to store manual for {command_manual.command_name}: {e}"
            )
            return False

    def _row_to_command_manual(self, row: tuple) -> CommandManual:
        """Convert a database row to a CommandManual object."""
        return CommandManual(
            command_name=row[0],
            description=row[1],
            syntax=row[2],
            common_options=json.loads(row[3]) if row[3] else [],
            examples=json.loads(row[4]) if row[4] else [],
            related_commands=json.loads(row[5]) if row[5] else [],
            risk_level=row[6],
            category=row[7],
            manual_text=row[8],
            section=row[9],
        )

    def get_manual(self, command_name: str) -> Optional[CommandManual]:
        """Retrieve a command manual from the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT command_name, description, syntax, common_options,
                           examples, related_commands, risk_level, category,
                           manual_text, section
                    FROM command_manuals WHERE command_name = ?""",
                    (command_name,),
                )
                row = cursor.fetchone()
                return self._row_to_command_manual(row) if row else None
        except Exception as e:
            logger.error("Failed to retrieve manual for %s: %s", command_name, e)
            return None

    def _build_search_query(
        self, query: str, category: Optional[str]
    ) -> Tuple[str, List[str]]:
        """Build SQL query and params for manual search."""
        sql = """SELECT command_name, description, syntax, common_options,
                       examples, related_commands, risk_level, category,
                       manual_text, section
                FROM command_manuals
                WHERE (command_name LIKE ? OR description LIKE ? OR manual_text LIKE ?)"""
        params = [f"%{query}%", f"%{query}%", f"%{query}%"]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY command_name"
        return sql, params

    def search_manuals(
        self, query: str, category: Optional[str] = None
    ) -> List[CommandManual]:
        """Search command manuals by query and optional category."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                sql, params = self._build_search_query(query, category)
                cursor.execute(sql, params)
                return [self._row_to_command_manual(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Failed to search manuals for query '%s': %s", query, e)
            return []

    def ingest_command(self, command_name: str) -> bool:
        """Ingest a single command manual into the knowledge base.

        Args:
            command_name: Name of the command to ingest

        Returns:
            True if successful, False otherwise
        """
        manual_text = self.get_manual_text(command_name)
        if not manual_text:
            logger.warning("No manual text found for command: %s", command_name)
            return False

        try:
            command_manual = self._parse_manual_text(command_name, manual_text)
            return self.store_manual(command_manual)
        except Exception as e:
            logger.error("Failed to ingest command %s: %s", command_name, e)
            return False

    def get_command_suggestions(self, user_intent: str) -> List[Tuple[str, str, str]]:
        """Get command suggestions based on user intent.

        Args:
            user_intent: User's intent or question

        Returns:
            List of tuples: (command_name, description, risk_level)
        """
        # Search for relevant commands
        manuals = self.search_manuals(user_intent)

        suggestions = []
        for manual in manuals[:5]:  # Limit to top 5 suggestions
            suggestions.append(
                (manual.command_name, manual.description, manual.risk_level)
            )

        return suggestions


def main():
    """Main function for testing the CommandManualManager."""
    manager = CommandManualManager()

    # Test ingesting a simple command
    success = manager.ingest_command("ls")
    logger.debug("Ingested 'ls' command: %s", success)

    # Test retrieving the command
    manual = manager.get_manual("ls")
    if manual:
        logger.debug("Retrieved manual for 'ls':")
        logger.debug("  Description: %s", manual.description)
        logger.debug("  Risk Level: %s", manual.risk_level)
        logger.debug("  Category: %s", manual.category)
        logger.debug("  Common Options: %s", manual.common_options[:3])

    # Test searching
    results = manager.search_manuals("list files")
    logger.debug(f"Search results for 'list files': {len(results)} commands found")


if __name__ == "__main__":
    main()
