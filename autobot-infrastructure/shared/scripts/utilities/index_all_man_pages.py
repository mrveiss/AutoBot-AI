#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Index ALL Available Man Pages on AutoBot Machines
Indexes every command with a man page for comprehensive CLI tool awareness
Enhanced with OS/Machine context for deduplication and agent awareness
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.system_context import (
    generate_unique_key,
    get_compatible_os_list,
    get_system_context,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def get_all_available_commands():
    """Get ALL commands with man pages on this system"""
    logger.info("Scanning for all available commands with man pages...")

    try:
        # Use man -k . to list ALL man pages (Issue #479: Use async subprocess)
        process = await asyncio.create_subprocess_exec(
            "man",
            "-k",
            ".",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.error("Timeout listing man pages")
            return []

        if process.returncode != 0:
            logger.error("Failed to list man pages")
            return []

        # Use decoded stdout
        output_text = stdout.decode()
        result_stdout = output_text

        commands = []
        for line in result_stdout.split("\n"):
            if not line.strip():
                continue

            # Parse format: command (section) - description
            parts = line.split("(")
            if len(parts) < 2:
                continue

            command_name = parts[0].strip()
            section_part = parts[1].split(")")[0]

            # Only index sections 1, 5, 8 (user commands, config files, admin commands)
            if section_part in ["1", "5", "8"]:
                commands.append((command_name, section_part))

        # Remove duplicates
        commands = list(set(commands))
        logger.info("Found %s commands to index", len(commands))

        return commands

    except Exception as e:
        logger.error("Error scanning commands: %s", e)
        return []


async def _get_man_page_description(command: str) -> str:
    """
    Get command description from man -k.

    Helper for index_command_batch (#825).

    Args:
        command: Command name

    Returns:
        Description string or empty string
    """
    desc_process = await asyncio.create_subprocess_exec(
        "man",
        "-k",
        f"^{command}$",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        desc_stdout, _ = await asyncio.wait_for(desc_process.communicate(), timeout=5)
    except asyncio.TimeoutError:
        desc_process.kill()
        await desc_process.wait()
        return ""

    if desc_process.returncode == 0:
        for line in desc_stdout.decode().split("\n"):
            if command in line and "-" in line:
                return line.split("-", 1)[1].strip()

    return ""


def _build_man_page_metadata(
    command: str, section: str, system_ctx: dict, unique_key: str
) -> dict:
    """
    Build metadata dict for man page fact.

    Helper for index_command_batch (#825).

    Args:
        command: Command name
        section: Man section
        system_ctx: System context dict
        unique_key: Unique key for deduplication

    Returns:
        Metadata dictionary
    """
    return {
        "type": "man_page",
        "command": command,
        "section": section,
        "title": f"man {command}({section})",
        "machine_id": system_ctx["machine_id"],
        "machine_ip": system_ctx["machine_ip"],
        "os_name": system_ctx["os_name"],
        "os_version": system_ctx["os_version"],
        "os_type": system_ctx["os_type"],
        "architecture": system_ctx["architecture"],
        "kernel_version": system_ctx["kernel_version"],
        "applies_to_machines": [system_ctx["machine_id"]],
        "applies_to_os": get_compatible_os_list(system_ctx["os_name"]),
        "unique_key": unique_key,
        "category": "system_commands",
        "source": "comprehensive_man_pages",
    }


async def _get_man_content(command: str, section: str) -> str:
    """
    Get man page content for a command.

    Helper for index_command_batch (#825).

    Args:
        command: Command name
        section: Man section

    Returns:
        Man page content string or empty string on error
    """
    env = os.environ.copy()
    env["MANWIDTH"] = "80"

    process = await asyncio.create_subprocess_exec(
        "man",
        section,
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return ""

    if process.returncode != 0:
        return ""

    return stdout.decode().strip()


def _format_man_content(
    command: str, section: str, description: str, man_content: str, system_ctx: dict
) -> str:
    """
    Format man page content with system context.

    Helper for index_command_batch (#825).

    Args:
        command: Command name
        section: Man section
        description: Command description
        man_content: Raw man page content
        system_ctx: System context dict

    Returns:
        Formatted content string
    """
    section_name = (
        "User Commands"
        if section == "1"
        else "Configuration Files"
        if section == "5"
        else "System Administration"
    )

    return f"""# {command}({section}) - {description}

**Machine:** {system_ctx['machine_id']} ({system_ctx['machine_ip']})
**OS:** {system_ctx['os_name']} {system_ctx['os_version']} ({system_ctx['os_type']})
**Architecture:** {system_ctx['architecture']}
**Section:** {section} ({section_name})

{man_content[:5000]}

---
*Full manual: `man {section} {command}`*
"""


async def index_command_batch(kb_v2, commands_batch, system_ctx=None):
    """Index a batch of commands with OS/machine context"""
    indexed_count = 0

    # Get system context once for the batch
    if system_ctx is None:
        system_ctx = get_system_context()

    for command, section in commands_batch:
        try:
            # Get man page content
            man_content = await _get_man_content(command, section)
            if not man_content:
                continue

            # Get description
            description = await _get_man_page_description(command)

            # Build content with enhanced context
            content = _format_man_content(
                command, section, description, man_content, system_ctx
            )

            # Generate unique key
            unique_key = generate_unique_key(
                system_ctx["machine_id"], system_ctx["os_name"], command, section
            )

            # Build metadata
            metadata = _build_man_page_metadata(
                command, section, system_ctx, unique_key
            )

            # Store in Knowledge Base
            result = await kb_v2.store_fact(content=content, metadata=metadata)

            if result.get("status") == "success":
                indexed_count += 1

        except subprocess.TimeoutExpired:
            logger.debug("Timeout for %s", command)
            continue
        except Exception as e:
            logger.debug("Error indexing %s: %s", command, e)
            continue

    return indexed_count


async def _log_system_context(system_ctx: dict):
    """
    Log system context information.

    Helper for main (#825).

    Args:
        system_ctx: System context dictionary
    """
    logger.info("\n3. Detecting system context...")
    logger.info(
        "✓ Machine: %s (%s)", system_ctx["machine_id"], system_ctx["machine_ip"]
    )
    logger.info("✓ OS: %s %s", system_ctx["os_name"], system_ctx["os_version"])
    logger.info("✓ Architecture: %s", system_ctx["architecture"])
    logger.info(
        "✓ Compatible with: %s",
        ", ".join(get_compatible_os_list(system_ctx["os_name"])),
    )


async def _index_commands_in_batches(kb_v2, all_commands, system_ctx: dict) -> int:
    """
    Index commands in batches.

    Helper for main (#825).

    Args:
        kb_v2: KnowledgeBase instance
        all_commands: List of (command, section) tuples
        system_ctx: System context dict

    Returns:
        Total number of indexed commands
    """
    logger.info("\n4. Indexing man pages...")
    batch_size = 50
    total_indexed = 0

    for i in range(0, len(all_commands), batch_size):
        batch = all_commands[i : i + batch_size]
        batch_indexed = await index_command_batch(kb_v2, batch, system_ctx)
        total_indexed += batch_indexed

        progress = min(i + batch_size, len(all_commands))
        logger.info(
            "Progress: %s/%s (%s indexed)",
            progress,
            len(all_commands),
            total_indexed,
        )

    return total_indexed


async def main():
    """Main indexing function"""
    logger.info("=" * 80)
    logger.info("COMPREHENSIVE MAN PAGE INDEXING")
    logger.info("=" * 80)

    try:
        # Initialize Knowledge Base V2
        from knowledge_base import KnowledgeBase

        logger.info("\n1. Initializing Knowledge Base V2...")
        kb_v2 = KnowledgeBase()
        await kb_v2.initialize()

        if not kb_v2.initialized:
            logger.error("✗ Knowledge Base V2 initialization failed")
            return 1

        logger.info("✓ Knowledge Base V2 initialized")

        # Get all available commands
        logger.info("\n2. Scanning for all available commands...")
        all_commands = await get_all_available_commands()

        if not all_commands:
            logger.error("✗ No commands found")
            return 1

        logger.info("✓ Found %s commands to index", len(all_commands))

        # Get system context for indexing
        system_ctx = get_system_context()
        await _log_system_context(system_ctx)

        # Index in batches
        total_indexed = await _index_commands_in_batches(
            kb_v2, all_commands, system_ctx
        )

        # Get final stats
        stats = await kb_v2.get_stats()

        logger.info("\n" + "=" * 80)
        logger.info("INDEXING COMPLETE")
        logger.info("=" * 80)
        logger.info("✓ Commands scanned: %s", len(all_commands))
        logger.info("✓ Successfully indexed: %s", total_indexed)
        logger.info("✓ Total facts in KB: %s", stats.get("total_facts", 0))
        logger.info("✓ Total vectors: %s", stats.get("total_vectors", 0))
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error("✗ Indexing failed: %s", e)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
