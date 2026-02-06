# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Extraction Service

Extracts available commands and documentation from infrastructure hosts
on first SSH connection. Uses deduplication to store commands once in
the knowledge base with relations indicating which hosts have them.

Related Issue: #715 - Dynamic SSH/VNC host management via secrets
Related Issue: #729 - SSH operations now proxied through SLM API

TODO (#729): This service needs refactoring to proxy SSH through SLM API

Key Features:
- Extracts all available commands via compgen -c
- Retrieves man page summaries for documentation
- Deduplicates across hosts (command stored once, relations to hosts)
- Integrates with ChromaDB knowledge base
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# TODO (#729): SSH proxied through SLM API
# Infrastructure services removed - now managed by SLM server (#729)
# from backend.services.ssh_connection_service import get_ssh_connection_service

logger = logging.getLogger(__name__)


@dataclass
class ExtractedCommand:
    """Represents an extracted command with its documentation."""

    name: str
    description: Optional[str] = None
    man_summary: Optional[str] = None
    category: Optional[str] = None
    source_hosts: List[str] = None

    def __post_init__(self):
        """Initialize source_hosts list if not provided."""
        if self.source_hosts is None:
            self.source_hosts = []


# Common command categories for classification
COMMAND_CATEGORIES = {
    "network": [
        "ping",
        "curl",
        "wget",
        "ssh",
        "scp",
        "sftp",
        "netstat",
        "ss",
        "ip",
        "ifconfig",
        "route",
        "traceroute",
        "nslookup",
        "dig",
        "host",
        "nc",
        "nmap",
        "tcpdump",
        "iptables",
        "firewall-cmd",
    ],
    "file_management": [
        "ls",
        "cd",
        "pwd",
        "cp",
        "mv",
        "rm",
        "mkdir",
        "rmdir",
        "touch",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "find",
        "locate",
        "which",
        "file",
        "stat",
        "du",
        "df",
        "ln",
        "chmod",
        "chown",
        "chgrp",
    ],
    "text_processing": [
        "grep",
        "egrep",
        "fgrep",
        "sed",
        "awk",
        "cut",
        "sort",
        "uniq",
        "wc",
        "tr",
        "diff",
        "patch",
        "tee",
        "xargs",
    ],
    "process_management": [
        "ps",
        "top",
        "htop",
        "kill",
        "killall",
        "pkill",
        "pgrep",
        "nice",
        "renice",
        "nohup",
        "bg",
        "fg",
        "jobs",
    ],
    "system_admin": [
        "systemctl",
        "service",
        "journalctl",
        "dmesg",
        "uname",
        "hostname",
        "uptime",
        "free",
        "vmstat",
        "iostat",
        "lsof",
        "strace",
        "ltrace",
    ],
    "package_management": [
        "apt",
        "apt-get",
        "dpkg",
        "yum",
        "dnf",
        "rpm",
        "pacman",
        "snap",
        "flatpak",
        "pip",
        "npm",
        "gem",
        "cargo",
    ],
    "archive": [
        "tar",
        "gzip",
        "gunzip",
        "bzip2",
        "bunzip2",
        "xz",
        "zip",
        "unzip",
        "7z",
        "rar",
        "unrar",
    ],
    "development": [
        "git",
        "make",
        "cmake",
        "gcc",
        "g++",
        "python",
        "python3",
        "node",
        "npm",
        "java",
        "javac",
        "go",
        "rust",
        "cargo",
    ],
    "security": [
        "sudo",
        "su",
        "passwd",
        "useradd",
        "userdel",
        "usermod",
        "groupadd",
        "openssl",
        "gpg",
        "ssh-keygen",
        "ssh-agent",
        "ssh-add",
    ],
}


def _categorize_command(command_name: str) -> Optional[str]:
    """Categorize a command based on known patterns."""
    for category, commands in COMMAND_CATEGORIES.items():
        if command_name in commands:
            return category
    return None


def _parse_man_whatis(output: str) -> Dict[str, str]:
    """
    Parse output from 'whatis' or 'apropos' command.

    Returns dict mapping command name to description.
    """
    descriptions = {}
    for line in output.strip().split("\n"):
        if not line.strip():
            continue

        # Format: "command (section) - description"
        match = re.match(r"^(\S+)\s*\([^)]+\)\s*-\s*(.+)$", line)
        if match:
            cmd_name = match.group(1)
            description = match.group(2).strip()
            descriptions[cmd_name] = description

    return descriptions


async def _extract_command_list(
    ssh_service,
    host_id: str,
) -> Set[str]:
    """Extract list of available commands from a host."""
    try:
        result = await ssh_service.execute_command(
            host_id,
            "compgen -c | sort -u",
            timeout=30.0,
            accessed_by="command_extraction",
        )

        if result["exit_code"] == 0:
            commands = set(result["stdout"].strip().split("\n"))
            # Filter out empty strings and very short names
            commands = {cmd for cmd in commands if len(cmd) > 1}
            logger.info("Extracted %d commands from host %s", len(commands), host_id)
            return commands

    except Exception as e:
        logger.error("Failed to extract command list from host %s: %s", host_id, e)

    return set()


async def _extract_command_descriptions(
    ssh_service,
    host_id: str,
    commands: Set[str],
    batch_size: int = 50,
) -> Dict[str, str]:
    """Extract descriptions for commands using whatis."""
    descriptions = {}

    # Process in batches to avoid command line length limits
    command_list = list(commands)
    for i in range(0, len(command_list), batch_size):
        batch = command_list[i : i + batch_size]

        try:
            # Use whatis for batch description lookup
            cmd_str = " ".join(batch)
            result = await ssh_service.execute_command(
                host_id,
                f"whatis {cmd_str} 2>/dev/null || true",
                timeout=30.0,
                accessed_by="command_extraction",
            )

            if result["exit_code"] == 0 and result["stdout"].strip():
                batch_descriptions = _parse_man_whatis(result["stdout"])
                descriptions.update(batch_descriptions)

        except Exception as e:
            logger.warning("Failed to get descriptions for batch: %s", e)
            continue

    logger.info(
        "Extracted descriptions for %d commands from host %s",
        len(descriptions),
        host_id,
    )
    return descriptions


async def extract_host_commands(host_id: str) -> Dict[str, ExtractedCommand]:
    """
    Extract all available commands from an infrastructure host.

    Args:
        host_id: Infrastructure host ID

    Returns:
        Dict mapping command names to ExtractedCommand objects

    Raises:
        NotImplementedError: SSH now proxied through SLM API (#729)
    """
    # TODO (#729): SSH proxied through SLM API - Update in Task 5.2
    raise NotImplementedError(
        "Command extraction temporarily disabled - SSH proxied through SLM API (#729)"
    )


async def store_commands_in_knowledge_base(
    commands: Dict[str, ExtractedCommand],
    host_id: str,
) -> int:
    """
    Store extracted commands in the knowledge base with deduplication.

    Uses ChromaDB to store commands as documents. If a command already exists,
    adds a relation to the new host rather than duplicating.

    NOTE: Infrastructure services removed - now managed by SLM server (#729).
    TODO (#729): Update to use SLM API for host info.

    Args:
        commands: Dict of extracted commands
        host_id: Host ID for relation creation

    Returns:
        Number of new commands added (currently always 0)
    """
    try:
        from backend.services.knowledge_base import get_knowledge_base_service

        get_knowledge_base_service()  # noqa: F841 - Verify import works
    except ImportError:
        logger.warning("Knowledge base service not available")
        return 0

    # Infrastructure services removed - now managed by SLM server (#729)
    logger.warning(
        "store_commands_in_knowledge_base temporarily disabled - "
        "infrastructure services removed (#729)"
    )
    return 0


async def get_commands_for_host(host_id: str) -> List[str]:
    """
    Get list of available commands for a specific host.

    Retrieves from knowledge base if already extracted, otherwise
    triggers extraction.

    NOTE: Infrastructure services removed - now managed by SLM server (#729).
    TODO (#729): Update to use SLM API for host info.

    Args:
        host_id: Infrastructure host ID

    Returns:
        List of command names available on the host (currently always empty)
    """
    # Infrastructure services removed - now managed by SLM server (#729)
    logger.warning(
        "get_commands_for_host temporarily disabled - "
        "infrastructure services removed (#729)"
    )
    return []


async def search_commands(
    query: str,
    host_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
) -> List[Dict]:
    """
    Search for commands across infrastructure hosts.

    Args:
        query: Search query (command name or description)
        host_id: Optional filter by host
        category: Optional filter by category
        limit: Maximum results to return

    Returns:
        List of matching commands with metadata
    """
    try:
        from backend.services.knowledge_base import get_knowledge_base_service

        kb_service = get_knowledge_base_service()

        results = await kb_service.search(
            query=query,
            category="infrastructure_command",
            limit=limit,
        )

        # Filter by host if specified
        if host_id:
            # Infrastructure services removed - now managed by SLM server (#729)
            # TODO (#729): Get host info from SLM API for filtering
            logger.warning(
                "Host filtering temporarily disabled - infrastructure services removed (#729)"
            )

        # Filter by category if specified
        if category:
            results = [r for r in results if r["metadata"].get("category") == category]

        return results

    except ImportError:
        logger.warning("Knowledge base service not available")
        return []
