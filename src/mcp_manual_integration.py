# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP Manual Integration - System Manual and Help Lookup Service

Provides integration with MCP servers for looking up manual pages, help documentation,
and system command information. This is essential for terminal and system tasks.
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

import aiofiles

from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for searchable doc source types (Issue #326)
SEARCHABLE_DOC_SOURCE_TYPES = {"autobot_docs", "readme"}

# Issue #380: Module-level frozensets for command safety checks
_SAFE_COMMANDS = frozenset({
    "ls", "grep", "cat", "echo", "pwd", "date", "whoami", "id", "curl", "wget",
    "git", "python", "python3", "pip", "pip3", "node", "npm", "yarn", "docker",
    "kubectl", "terraform", "ansible", "ssh", "scp", "rsync", "find", "locate",
    "which", "man", "info", "help", "type", "alias", "history", "env", "ps",
    "top", "htop", "free", "df", "du", "mount", "lsblk", "systemctl", "service",
    "journalctl", "awk", "sed", "sort", "uniq", "wc", "head", "tail", "tr",
    "cut", "paste", "join",
})

_DANGEROUS_COMMANDS = frozenset({
    "rm", "rmdir", "mv", "cp", "dd", "mkfs", "fdisk", "parted", "shutdown",
    "reboot", "halt", "init", "kill", "killall", "pkill", "chmod", "chown",
    "chgrp", "su", "sudo", "passwd", "crontab", "at", "batch",
})

_HELP_ARGS = frozenset({"--help", "-h", "help"})
_HELP_COMMAND_PREFIXES = ("help", "man", "info")  # Tuple for startswith()
_HELP_SKIP_PREFIXES = ("-", "Usage:", "usage:")  # Issue #380: Tuple for startswith()

# MCP tools are available directly through the environment
# No need for separate client manager - we can use MCP tools directly
MCP_AVAILABLE = True

# Import existing command manual manager
try:
    from .command_manual_manager import CommandManualManager

    COMMAND_MANAGER_AVAILABLE = True
except ImportError:
    logger.warning("CommandManualManager not available")
    COMMAND_MANAGER_AVAILABLE = False


class MCPManualService:
    """
    Service for looking up system manuals and help information via MCP.

    Integrates with MCP servers to provide:
    - Linux manual pages (man pages)
    - Command help information (--help output)
    - System documentation
    - Tool usage instructions
    """

    def __init__(self):
        """Initialize the MCP manual service"""
        self.available_mcps = []
        self.command_cache = {}  # Cache for frequently requested commands
        self.cache_timeout = 300  # 5 minutes

        # MCP tools are available directly in this environment
        self.mcp_available = MCP_AVAILABLE
        logger.info("MCP tools available: %s", self.mcp_available)

        # Initialize command manual manager if available
        self.command_manager = None
        if COMMAND_MANAGER_AVAILABLE:
            try:
                self.command_manager = CommandManualManager()
                logger.info("CommandManualManager initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize CommandManualManager: %s", e)
                self.command_manager = None

        logger.info("MCPManualService initialized")

    async def lookup_manual(
        self, query: str, command: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Look up manual information for a query or specific command.

        Args:
            query: Search query or description
            command: Specific command to look up (optional)

        Returns:
            Dictionary with manual information or None if not found
        """
        try:
            # Extract command from query if not provided
            if not command:
                command = self._extract_command_from_query(query)

            if command:
                logger.info("Looking up manual for command: %s", command)

                # Try different lookup strategies
                manual_info = await self._lookup_command_manual(command)
                if manual_info:
                    return manual_info

                # Try help lookup if manual not found
                help_info = await self._lookup_command_help(command)
                if help_info:
                    return help_info

            # General documentation search
            doc_info = await self._search_documentation(query)
            return doc_info

        except Exception as e:
            logger.error("Manual lookup failed for '%s': %s", query, e)
            return None

    def _extract_command_from_query(self, query: str) -> Optional[str]:
        """
        Extract command name from a natural language query.

        Args:
            query: Natural language query

        Returns:
            Extracted command name or None
        """
        # Common patterns for command extraction
        patterns = [
            r"how to use (\w+)",
            r"(\w+) command",
            r"run (\w+)",
            r"execute (\w+)",
            r"help with (\w+)",
            r"manual for (\w+)",
            r"documentation for (\w+)",
            r"(?:^|\s)(\w+)(?:\s|$)",  # Single word (last resort)
        ]

        query_lower = query.lower()

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                command = match.group(1)
                # Filter out common non-command words
                if command not in {
                    "how",
                    "to",
                    "use",
                    "the",
                    "a",
                    "an",
                    "is",
                    "are",
                    "can",
                    "will",
                    "help",
                    "with",
                }:
                    return command

        return None

    async def _lookup_command_manual(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Look up manual page for a specific command.

        Args:
            command: Command name to look up

        Returns:
            Manual page information or None
        """
        try:
            # Check cache first
            cache_key = f"man_{command}"
            if self._check_cache(cache_key):
                return self.command_cache[cache_key]["data"]

            # Use real MCP server integration for manual pages
            manual_data = await self._real_manual_lookup(command)

            if manual_data:
                # Cache the result
                self._cache_result(cache_key, manual_data)
                return manual_data

            return None

        except Exception as e:
            logger.error("Manual lookup failed for command '%s': %s", command, e)
            return None

    async def _lookup_command_help(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Look up help information for a command (--help output).

        Args:
            command: Command name

        Returns:
            Help information or None
        """
        try:
            # Check cache first
            cache_key = f"help_{command}"
            if self._check_cache(cache_key):
                return self.command_cache[cache_key]["data"]

            # Use real MCP server integration for command help
            help_data = await self._real_help_lookup(command)

            if help_data:
                # Cache the result
                self._cache_result(cache_key, help_data)
                return help_data

            return None

        except Exception as e:
            logger.error("Help lookup failed for command '%s': %s", command, e)
            return None

    async def _search_documentation(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search general documentation for a query.

        Args:
            query: Search query

        Returns:
            Documentation results or None
        """
        try:
            # Use real MCP server integration for documentation search
            doc_data = await self._real_documentation_search(query)
            return doc_data

        except Exception as e:
            logger.error("Documentation search failed for '%s': %s", query, e)
            return None

    async def _real_manual_lookup(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Real manual lookup using MCP filesystem server and system commands (Issue #315 - refactored).

        This replaces the mock implementation with actual manual page retrieval.
        """
        try:
            # First, try to get from existing command manager
            existing_manual = await self._try_get_from_command_manager(command)
            if existing_manual:
                return existing_manual

            # If not in command manager, try to execute man command
            return await self._try_execute_and_parse_man(command)

        except Exception as e:
            logger.error("Real manual lookup failed for command '%s': %s", command, e)
            # Fallback to mock data for critical commands
            return await self._fallback_manual_lookup(command)

    async def _try_get_from_command_manager(
        self, command: str
    ) -> Optional[Dict[str, Any]]:
        """Try to get manual from command manager (Issue #315 - extracted)."""
        if not self.command_manager:
            return None

        existing_manual = self.command_manager.get_manual(command)
        if not existing_manual:
            return None

        return {
            "name": existing_manual.command_name,
            "section": str(existing_manual.section),
            "description": existing_manual.description,
            "synopsis": existing_manual.syntax,
            "content": existing_manual.manual_text,
            "source": "command_manager",
            "risk_level": existing_manual.risk_level,
            "category": existing_manual.category,
            "examples": existing_manual.examples,
            "related_commands": existing_manual.related_commands,
        }

    async def _try_execute_and_parse_man(
        self, command: str
    ) -> Optional[Dict[str, Any]]:
        """Execute man command and parse result (Issue #315 - extracted)."""
        manual_text = await self._execute_man_command(command)
        if not manual_text:
            return None

        # Parse the manual text into structured format
        manual_data = self._parse_manual_text(command, manual_text)

        # Store in command manager if available
        if self.command_manager and manual_data:
            try:
                self.command_manager.store_manual(manual_data)
            except Exception as e:
                logger.warning("Failed to store manual for %s: %s", command, e)

        return {
            "name": command,
            "section": "1",  # Default section
            "description": self._extract_description(command, manual_text),
            "synopsis": self._extract_synopsis(command, manual_text),
            "content": manual_text,
            "source": "system_manual",
        }

    async def _execute_man_command(self, command: str) -> Optional[str]:
        """
        Execute the man command to get manual page content.

        Uses MCP filesystem server if available, otherwise falls back to subprocess.
        """
        try:
            # Execute man command directly - this is more reliable than complex MCP scripting
            result = await self._run_subprocess(["man", command])
            return result if result else None

        except Exception as e:
            logger.error("Failed to execute man command for '%s': %s", command, e)
            return None

    async def _run_subprocess(self, cmd: List[str]) -> Optional[str]:
        """Run subprocess command safely and return output."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Wait for the process to complete with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("Command %s timed out", ' '.join(cmd))
                process.kill()
                await process.wait()
                return None

            if process.returncode == 0:
                return stdout.decode("utf-8", errors="ignore")
            else:
                logger.warning(
                    "Command %s failed with return code %d", ' '.join(cmd), process.returncode
                )
                return None

        except Exception as e:
            logger.error("Subprocess execution failed: %s", e)
            return None

    def _parse_manual_text(self, command: str, manual_text: str):
        """Parse manual text using command manager if available."""
        if self.command_manager:
            try:
                return self.command_manager._parse_manual_text(command, manual_text)
            except Exception as e:
                logger.warning("Failed to parse manual text: %s", e)
        return None

    def _extract_description(self, command: str, manual_text: str) -> str:
        """Extract description from manual text."""
        lines = manual_text.split("\n")
        for i, line in enumerate(lines):
            if "DESCRIPTION" in line.upper() and i + 1 < len(lines):
                # Get the first meaningful line after DESCRIPTION
                for j in range(i + 1, min(i + 5, len(lines))):
                    desc_line = lines[j].strip()
                    if desc_line and not desc_line.isupper():
                        return desc_line
        return f"Manual page for {command.split()[0]}"

    def _extract_synopsis(self, command: str, manual_text: str) -> str:
        """Extract synopsis from manual text."""
        lines = manual_text.split("\n")
        for i, line in enumerate(lines):
            if "SYNOPSIS" in line.upper() and i + 1 < len(lines):
                # Get the next non-empty line
                for j in range(i + 1, min(i + 3, len(lines))):
                    synopsis_line = lines[j].strip()
                    if synopsis_line:
                        return synopsis_line
        return f"{command.split()[0]} [options]"

    async def _fallback_manual_lookup(self, command: str) -> Optional[Dict[str, Any]]:
        """Fallback to basic mock data for critical commands."""
        critical_commands = {
            "ls": {
                "name": "ls",
                "section": "1",
                "description": "list directory contents",
                "synopsis": "ls [OPTION]... [FILE]...",
                "content": (
                    "Basic file listing command. Use ls -la for detailed output."
                ),
                "source": "fallback",
            },
            "grep": {
                "name": "grep",
                "section": "1",
                "description": "search text using patterns",
                "synopsis": "grep [OPTIONS] PATTERN [FILE...]",
                "content": "Text search command. Use grep -r for recursive search.",
                "source": "fallback",
            },
            "cat": {
                "name": "cat",
                "section": "1",
                "description": "concatenate files and print on the standard output",
                "synopsis": "cat [OPTION]... [FILE]...",
                "content": "Display file contents. Use cat filename to view a file.",
                "source": "fallback",
            },
        }

        return critical_commands.get(command)

    async def _real_help_lookup(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Real help lookup using command --help execution via MCP filesystem server.

        This replaces the mock implementation with actual command help retrieval.
        """
        try:
            # Try different help variations
            help_variations = [
                [command, "--help"],
                [command, "-h"],
                [command, "help"],
                ["help", command],
            ]

            for cmd_args in help_variations:
                help_text = await self._execute_help_command(cmd_args)
                if help_text and self._is_valid_help_output(help_text):
                    return {
                        "name": command,
                        "description": self._extract_help_description(help_text),
                        "content": help_text,
                        "source": "command_help",
                        "command_args": " ".join(cmd_args),
                    }

            # If no help found, try to get from manual
            manual_data = await self._real_manual_lookup(command)
            if manual_data:
                return {
                    "name": command,
                    "description": manual_data.get(
                        "description", f"Help for {command}"
                    ),
                    "content": manual_data.get("content", ""),
                    "source": "manual_fallback",
                }

            return None

        except Exception as e:
            logger.error("Real help lookup failed for command '%s': %s", command, e)
            return await self._fallback_help_lookup(command)

    async def _execute_help_command(self, cmd_args: List[str]) -> Optional[str]:
        """
        Execute a help command to get help output.

        Uses MCP filesystem server if available, otherwise falls back to subprocess.
        """
        try:
            # Validate command arguments for safety
            if not self._is_safe_command(cmd_args):
                logger.warning("Unsafe command rejected: %s", ' '.join(cmd_args))
                return None

            # Execute help command directly with timeout for safety
            result = await self._run_subprocess(cmd_args)
            return result if result else None

        except Exception as e:
            logger.error("Failed to execute help command %s: %s", ' '.join(cmd_args), e)
            return None

    def _is_safe_command(self, cmd_args: List[str]) -> bool:
        """Check if command is safe to execute for help lookup."""
        if not cmd_args:
            return False

        command = cmd_args[0].lower()

        # Issue #380: Use module-level frozensets for O(1) lookups
        if command in _DANGEROUS_COMMANDS:
            return False

        # Only allow help-related arguments
        if len(cmd_args) > 1 and not any(arg in _HELP_ARGS for arg in cmd_args[1:]):
            # Special case for 'help command'
            if cmd_args[0] != "help":
                return False

        return command in _SAFE_COMMANDS or command.startswith(_HELP_COMMAND_PREFIXES)

    def _is_valid_help_output(self, output: str) -> bool:
        """Check if output looks like valid help text."""
        if not output or len(output.strip()) < 10:
            return False

        # Look for common help indicators
        help_indicators = [
            "usage:",
            "Usage:",
            "USAGE:",
            "options:",
            "Options:",
            "OPTIONS:",
            "help",
            "Help",
            "HELP",
            "commands:",
            "Commands:",
            "COMMANDS:",
            "examples:",
            "Examples:",
            "EXAMPLES:",
        ]

        output_lower = output.lower()
        return any(indicator.lower() in output_lower for indicator in help_indicators)

    def _extract_help_description(self, help_text: str) -> str:
        """Extract description from help text."""
        lines = help_text.split("\n")

        # Look for description patterns
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line and not line.startswith(_HELP_SKIP_PREFIXES):
                # Skip lines that are just the command name
                if len(line.split()) > 2:
                    return line

        # Fallback to first non-empty line
        for line in lines:
            line = line.strip()
            if line and len(line) > 10:
                return line

        return "Command help information"

    async def _fallback_help_lookup(self, command: str) -> Optional[Dict[str, Any]]:
        """Fallback help lookup for critical commands."""
        critical_help = {
            "ls": {
                "name": "ls",
                "description": "list directory contents",
                "content": (
                    "Usage: ls [OPTION]... [FILE]...\nList information about the FILEs."
                ),
                "source": "fallback_help",
            },
            "grep": {
                "name": "grep",
                "description": "search text using patterns",
                "content": (
                    "Usage: grep [OPTIONS] PATTERN [FILE...]\nSearch for PATTERN in each FILE."
                ),
                "source": "fallback_help",
            },
            "cat": {
                "name": "cat",
                "description": "concatenate files and print on the standard output",
                "content": (
                    "Usage: cat [OPTION]... [FILE]...\nConcatenate FILE(s) to standard output."
                ),
                "source": "fallback_help",
            },
            "curl": {
                "name": "curl",
                "description": "transfer data from or to a server",
                "content": (
                    "Usage: curl [options...] <url>\nTransfer data from or to a server."
                ),
                "source": "fallback_help",
            },
        }

        return critical_help.get(command)

    async def _real_documentation_search(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Real documentation search using MCP filesystem and SQLite servers.

        This replaces the mock implementation with actual documentation search.
        """
        try:
            results = []

            # Search through different documentation sources
            doc_sources = await self._get_documentation_sources()

            for source in doc_sources:
                source_results = await self._search_documentation_source(query, source)
                results.extend(source_results)

            # Search existing command manuals using command manager
            if self.command_manager:
                manual_results = await self._search_command_manuals(query)
                results.extend(manual_results)

            # Search system info files
            info_results = await self._search_info_files(query)
            results.extend(info_results)

            # Sort results by relevance
            results.sort(key=lambda x: x.get("relevance", 0), reverse=True)

            # Limit results to top 10
            results = results[:10]

            return {
                "query": query,
                "results": results,
                "total_found": len(results),
                "sources_searched": [source["name"] for source in doc_sources],
            }

        except Exception as e:
            logger.error("Real documentation search failed for '%s': %s", query, e)
            return await self._fallback_documentation_search(query)

    async def _get_documentation_sources(self) -> List[Dict[str, Any]]:
        """Get list of available documentation sources."""
        sources = []

        # Common documentation directories
        common_doc_dirs = [
            "/usr/share/doc",
            "/usr/local/share/doc",
            "/opt/autobot/docs",
            f"{PATH.PROJECT_ROOT}/docs",
            "/usr/share/man",
            "/usr/local/share/man",
        ]

        if self.mcp_available:
            # Use filesystem MCP to check which directories exist
            for doc_dir in common_doc_dirs:
                try:
                    # Issue #358 - avoid blocking
                    dir_exists = await asyncio.to_thread(os.path.exists, doc_dir)
                    is_dir = await asyncio.to_thread(os.path.isdir, doc_dir) if dir_exists else False
                    if dir_exists and is_dir:
                        sources.append(
                            {"name": doc_dir, "type": "directory", "searchable": True}
                        )
                except Exception as e:
                    # Directory doesn't exist or not accessible
                    logger.debug("Documentation directory %s not accessible: %s", doc_dir, e)

        # Add AutoBot specific documentation
        autobot_docs = [
            {
                "name": f"{PATH.PROJECT_ROOT}/docs",
                "type": "autobot_docs",
                "searchable": True,
            },
            {
                "name": f"{PATH.PROJECT_ROOT}/README.md",
                "type": "readme",
                "searchable": True,
            },
        ]

        sources.extend(autobot_docs)
        return sources

    async def _collect_doc_files_from_dir(
        self, dir_path: str, max_depth: int = 2, max_files_per_dir: int = 20
    ) -> List[str]:
        """Collect documentation files from a directory (Issue #298 - extracted helper)."""
        files = []
        # Issue #358 - already uses lambda wrapper correctly for os.walk
        walk_results = await asyncio.to_thread(lambda: list(os.walk(dir_path)))

        for root, dirs, filenames in walk_results:
            # Limit depth to avoid excessive scanning
            if root.count(os.sep) - dir_path.count(os.sep) > max_depth:
                continue

            for filename in filenames[:max_files_per_dir]:
                file_path = os.path.join(root, filename)
                if self._is_documentation_file(file_path):
                    files.append(file_path)

        return files

    async def _search_directory_docs(
        self, query: str, dir_path: str, max_files: int = 20
    ) -> List[Dict[str, Any]]:
        """Search documentation files in a directory (Issue #298 - extracted helper)."""
        results = []
        try:
            files = await self._collect_doc_files_from_dir(dir_path)
            for file_path in files[:max_files]:
                file_results = await self._search_file_content(query, file_path)
                results.extend(file_results)
        except Exception as e:
            logger.warning("Failed to search directory %s: %s", dir_path, e)
        return results

    async def _search_documentation_source(
        self, query: str, source: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Search a specific documentation source (Issue #298 - reduced nesting)."""
        results = []

        try:
            source_type = source["type"]
            source_name = source["name"]

            # Directory search
            if source_type == "directory" and self.mcp_available:
                return await self._search_directory_docs(query, source_name)

            # AutoBot docs or readme
            if source_type not in SEARCHABLE_DOC_SOURCE_TYPES or not self.mcp_available:
                return results

            is_dir = await asyncio.to_thread(os.path.isdir, source_name)
            if is_dir:
                return await self._search_directory_docs(query, source_name)

            # Single file
            return await self._search_file_content(query, source_name)

        except Exception as e:
            logger.warning("Failed to search documentation source %s: %s", source['name'], e)

        return results

    def _is_documentation_file(self, file_path: str) -> bool:
        """Check if a file is likely documentation."""
        doc_extensions = {
            ".md",
            ".txt",
            ".rst",
            ".man",
            ".1",
            ".2",
            ".3",
            ".4",
            ".5",
            ".6",
            ".7",
            ".8",
        }
        doc_names = {
            "readme",
            "changelog",
            "license",
            "install",
            "usage",
            "help",
            "manual",
        }

        file_lower = file_path.lower()

        # Check extension
        for ext in doc_extensions:
            if file_lower.endswith(ext):
                return True

        # Check filename
        filename = os.path.basename(file_lower)
        for name in doc_names:
            if name in filename:
                return True

        return False

    async def _search_file_content(
        self, query: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Search content of a specific file (Issue #315 - refactored)."""
        try:
            # Read file content directly
            file_exists = await asyncio.to_thread(os.path.exists, file_path)
            is_file = await asyncio.to_thread(os.path.isfile, file_path)

            # Early return if file doesn't exist
            if not (file_exists and is_file):
                return []

            return await self._read_and_search_file(query, file_path)

        except Exception as e:
            logger.warning("Failed to search file %s: %s", file_path, e)
            return []

    async def _read_and_search_file(
        self, query: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Read file with encoding fallback and search (Issue #315 - extracted)."""
        # Try UTF-8 first
        content = await self._try_read_file_utf8(file_path)
        if content:
            return self._find_query_matches(query, content, file_path)

        # Fallback to latin-1 for binary files
        content = await self._try_read_file_latin1(file_path)
        if content:
            return self._find_query_matches(query, content, file_path)

        return []

    async def _try_read_file_utf8(self, file_path: str) -> Optional[str]:
        """Try reading file with UTF-8 encoding (Issue #315 - extracted)."""
        try:
            async with aiofiles.open(
                file_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                return await f.read()
        except (UnicodeDecodeError, OSError) as e:
            logger.debug("UTF-8 read failed for %s: %s", file_path, e)
            return None
        except Exception as e:
            logger.debug("Skipping unreadable file %s: %s", file_path, e)
            return None

    async def _try_read_file_latin1(self, file_path: str) -> Optional[str]:
        """Try reading file with latin-1 encoding (Issue #315 - extracted)."""
        try:
            async with aiofiles.open(
                file_path, "r", encoding="latin-1", errors="ignore"
            ) as f:
                return await f.read()
        except (OSError, Exception) as e:
            logger.debug("Latin-1 read failed for %s: %s", file_path, e)
            return None

    def _find_query_matches(
        self, query: str, content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Find matches for query in file content (Issue #315 - refactored)."""
        matches = []
        query_lower = query.lower()
        lines = content.split("\n")

        for i, line in enumerate(lines):
            # Skip non-matching lines
            if query_lower not in line.lower():
                continue

            # Calculate relevance and create match entry
            match_entry = self._create_match_entry(query, query_lower, line, i, lines, file_path)
            matches.append(match_entry)

        return matches

    def _create_match_entry(
        self, query: str, query_lower: str, line: str, line_index: int, all_lines: List[str], file_path: str
    ) -> Dict[str, Any]:
        """Create a match entry with relevance and context (Issue #315 - extracted)."""
        # Calculate relevance based on exact match and context
        relevance = self._calculate_relevance(query, query_lower, line)

        # Get context lines
        start_line = max(0, line_index - 2)
        end_line = min(len(all_lines), line_index + 3)
        context = "\n".join(all_lines[start_line:end_line])

        return {
            "title": f"{os.path.basename(file_path)} (line {line_index + 1})",
            "content": context,
            "source": file_path,
            "line_number": line_index + 1,
            "relevance": relevance,
            "match_line": line.strip(),
        }

    def _calculate_relevance(self, query: str, query_lower: str, line: str) -> float:
        """Calculate relevance score for a match (Issue #315 - extracted)."""
        relevance = 0.5

        if query_lower == line.lower().strip():
            relevance = 1.0
        elif query in line:  # Case-sensitive match
            relevance = 0.8
        elif len(line.strip()) < 100:  # Short lines likely more relevant
            relevance += 0.2

        return relevance

    async def _search_command_manuals(self, query: str) -> List[Dict[str, Any]]:
        """Search through stored command manuals."""
        results = []

        try:
            if self.command_manager:
                # Use command manager's search functionality
                manual_matches = self.command_manager.search_manuals(
                    query_text=query, limit=5
                )

                for manual in manual_matches:
                    results.append(
                        {
                            "title": f"Manual: {manual.command_name}",
                            "content": (
                                f"{manual.description}\n\nSyntax: {manual.syntax}"
                            ),
                            "source": "command_manual",
                            "relevance": 0.7,
                            "command": manual.command_name,
                            "category": manual.category,
                            "risk_level": manual.risk_level,
                        }
                    )

        except Exception as e:
            logger.warning("Failed to search command manuals: %s", e)

        return results

    async def _search_info_files(self, query: str) -> List[Dict[str, Any]]:
        """Search GNU info files."""
        results = []

        try:
            # Try to get info about the query
            info_output = await self._run_subprocess(["info", "--where", query])
            if info_output and info_output.strip():
                info_file = info_output.strip()

                # Get actual info content
                content = await self._run_subprocess(["info", query, "--output=-"])
                if content:
                    results.append(
                        {
                            "title": f"Info: {query}",
                            "content": (
                                content[:500] + "..." if len(content) > 500 else content
                            ),
                            "source": f"info:{info_file}",
                            "relevance": 0.8,
                        }
                    )

        except Exception as e:
            logger.warning("Failed to search info files for %s: %s", query, e)

        return results

    async def _fallback_documentation_search(
        self, query: str
    ) -> Optional[Dict[str, Any]]:
        """Fallback documentation search with basic results."""
        fallback_docs = {
            "autobot": {
                "title": "AutoBot Documentation",
                "content": (
                    "AutoBot is an intelligent automation platform with distributed VM architecture."
                ),
                "source": "fallback",
                "relevance": 0.9,
            },
            "linux": {
                "title": "Linux Command Information",
                "content": (
                    "Use man command_name to get detailed manual pages for Linux commands."
                ),
                "source": "fallback",
                "relevance": 0.7,
            },
            "help": {
                "title": "Getting Help",
                "content": (
                    "Use --help flag with most commands to get usage information."
                ),
                "source": "fallback",
                "relevance": 0.8,
            },
        }

        # Find best match
        for key, doc in fallback_docs.items():
            if key in query.lower():
                return {
                    "query": query,
                    "results": [doc],
                    "total_found": 1,
                    "sources_searched": ["fallback"],
                }

        # Generic response
        return {
            "query": query,
            "results": [
                {
                    "title": f"Documentation search for: {query}",
                    "content": (
                        f'Search performed for "{query}". Try using man command_name for manual pages.'
                    ),
                    "source": "fallback",
                    "relevance": 0.5,
                }
            ],
            "total_found": 1,
            "sources_searched": ["fallback"],
        }

    def _check_cache(self, cache_key: str) -> bool:
        """Check if cached result is still valid"""
        import time

        if cache_key in self.command_cache:
            cache_entry = self.command_cache[cache_key]
            if time.time() - cache_entry["timestamp"] < self.cache_timeout:
                return True
            else:
                # Remove expired cache entry
                del self.command_cache[cache_key]

        return False

    def _cache_result(self, cache_key: str, data: Dict[str, Any]):
        """Cache lookup result"""
        import time

        self.command_cache[cache_key] = {"data": data, "timestamp": time.time()}

        # Limit cache size
        if len(self.command_cache) > 100:
            # Remove oldest entries
            sorted_keys = sorted(
                self.command_cache.keys(),
                key=lambda k: self.command_cache[k]["timestamp"],
            )
            for key in sorted_keys[:20]:  # Remove oldest 20 entries
                del self.command_cache[key]


# Global service instance
mcp_manual_service = MCPManualService()


async def lookup_system_manual(
    query: str, command: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Convenience function to look up system manual information.

    Args:
        query: Search query or description
        command: Specific command to look up (optional)

    Returns:
        Manual information or None if not found
    """
    return await mcp_manual_service.lookup_manual(query, command)


async def get_command_help(command: str) -> Optional[str]:
    """
    Get help information for a specific command.

    Args:
        command: Command name

    Returns:
        Help text or None if not found
    """
    result = await mcp_manual_service._lookup_command_help(command)
    if result:
        return result.get("content", "")
    return None


async def search_system_documentation(query: str) -> List[Dict[str, Any]]:
    """
    Search system documentation for a query.

    Args:
        query: Search query

    Returns:
        List of documentation results
    """
    result = await mcp_manual_service._search_documentation(query)
    if result and "results" in result:
        return result["results"]
    return []
