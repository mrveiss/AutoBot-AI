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
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp

logger = logging.getLogger(__name__)

_DEFAULT_SLM_URL = os.environ.get("SLM_URL", "")
_DEFAULT_SLM_TOKEN = os.environ.get("SLM_AUTH_TOKEN", "")


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


async def _slm_exec(
    node_id: str,
    command: str,
    timeout: int = 30,
    slm_url: str = "",
    auth_token: str = "",
) -> Tuple[bool, str, str]:
    """
    Execute a command on a fleet node via the SLM API.

    Issue #933: Replaces direct SSH calls.

    Args:
        node_id: SLM node identifier
        command: Shell command to run
        timeout: Command timeout in seconds
        slm_url: SLM base URL (falls back to SLM_URL env var)
        auth_token: Bearer token (falls back to SLM_AUTH_TOKEN env var)

    Returns:
        Tuple of (success, stdout, stderr)
    """
    base = (slm_url or _DEFAULT_SLM_URL).rstrip("/")
    token = auth_token or _DEFAULT_SLM_TOKEN
    if not base:
        logger.error("SLM_URL not configured — cannot exec on node %s", node_id)
        return False, "", "SLM_URL not configured"

    url = f"{base}/api/nodes/{node_id}/exec"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {"command": command, "timeout": timeout}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, ssl=False
            ) as resp:
                data: Dict[str, Any] = await resp.json()
                return (
                    data.get("success", False),
                    data.get("stdout", ""),
                    data.get("stderr", ""),
                )
    except Exception as exc:
        logger.error("SLM exec failed for node %s: %s", node_id, exc)
        return False, "", str(exc)


async def _extract_command_list(
    node_id: str, slm_url: str, auth_token: str
) -> Set[str]:
    """Extract list of available commands from a host via SLM API.

    Issue #933: Replaces ssh_service.execute_command.
    """
    success, stdout, _stderr = await _slm_exec(
        node_id,
        "compgen -c | sort -u",
        timeout=30,
        slm_url=slm_url,
        auth_token=auth_token,
    )
    if not success or not stdout.strip():
        logger.error("Failed to extract command list from node %s", node_id)
        return set()
    commands = {cmd for cmd in stdout.strip().split("\n") if len(cmd) > 1}
    logger.info("Extracted %d commands from node %s", len(commands), node_id)
    return commands


async def _extract_command_descriptions(
    node_id: str,
    commands: Set[str],
    slm_url: str,
    auth_token: str,
    batch_size: int = 50,
) -> Dict[str, str]:
    """Extract descriptions for commands using whatis via SLM API.

    Issue #933: Replaces ssh_service.execute_command.
    """
    descriptions: Dict[str, str] = {}
    command_list = list(commands)
    for i in range(0, len(command_list), batch_size):
        batch = command_list[i : i + batch_size]
        cmd_str = " ".join(batch)
        try:
            success, stdout, _stderr = await _slm_exec(
                node_id,
                f"whatis {cmd_str} 2>/dev/null || true",
                timeout=30,
                slm_url=slm_url,
                auth_token=auth_token,
            )
            if success and stdout.strip():
                descriptions.update(_parse_man_whatis(stdout))
        except Exception as exc:
            logger.warning("Failed to get descriptions for batch: %s", exc)
    logger.info(
        "Extracted descriptions for %d commands from node %s",
        len(descriptions),
        node_id,
    )
    return descriptions


async def extract_host_commands(host_id: str) -> Dict[str, ExtractedCommand]:
    """
    Extract all available commands from an infrastructure host via SLM API.

    Issue #933: Implements SLM API proxying (was NotImplementedError).

    Args:
        host_id: SLM node_id of the target host

    Returns:
        Dict mapping command names to ExtractedCommand objects
    """
    slm_url = _DEFAULT_SLM_URL
    auth_token = _DEFAULT_SLM_TOKEN

    command_names = await _extract_command_list(host_id, slm_url, auth_token)
    if not command_names:
        return {}

    descriptions = await _extract_command_descriptions(
        host_id, command_names, slm_url, auth_token
    )

    result: Dict[str, ExtractedCommand] = {}
    for name in command_names:
        result[name] = ExtractedCommand(
            name=name,
            description=descriptions.get(name),
            category=_categorize_command(name),
            source_hosts=[host_id],
        )
    logger.info("Extracted %d commands from host %s", len(result), host_id)
    return result


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
        from services.knowledge_base import get_knowledge_base_service

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
        from services.knowledge_base import get_knowledge_base_service

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
