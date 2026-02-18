#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test Man Page OS Context System
Index a single man page to verify OS/machine context detection
"""

import asyncio
import json
import logging
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


def _get_man_page_content(command: str, section: str) -> tuple:
    """
    Get man page content and description via subprocess.

    Issue #281: Extracted from test_single_man_page to reduce function length.

    Args:
        command: The command to get man page for.
        section: The man page section.

    Returns:
        Tuple of (man_content, description) or (None, None) on failure.
    """
    logger.info(f"\n3. Fetching man page content for {command}({section})...")
    result = subprocess.run(
        ["man", section, command],
        capture_output=True,
        text=True,
        timeout=10,
        env={"MANWIDTH": "80"},
    )

    if result.returncode != 0:
        logger.error(f"✗ Failed to get man page for {command}({section})")
        return None, None

    man_content = result.stdout.strip()
    logger.info(f"✓ Man page retrieved ({len(man_content)} characters)")

    desc_result = subprocess.run(
        ["man", "-k", f"^{command}$"], capture_output=True, text=True, timeout=5
    )

    description = "System command"
    if desc_result.returncode == 0:
        for line in desc_result.stdout.split("\n"):
            if command in line and "-" in line:
                description = line.split("-", 1)[1].strip()
                break

    logger.info(f"✓ Description: {description}")
    return man_content, description


def _build_man_page_metadata(
    command: str, section: str, system_ctx: dict, compatible_oses: list, unique_key: str
) -> dict:
    """
    Build metadata dictionary for man page fact.

    Issue #281: Extracted from test_single_man_page to reduce function length.

    Args:
        command: The command name.
        section: The man page section.
        system_ctx: System context dictionary.
        compatible_oses: List of compatible OS names.
        unique_key: Unique key for deduplication.

    Returns:
        Metadata dictionary.
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
        "applies_to_os": compatible_oses,
        "unique_key": unique_key,
        "category": "system_commands",
        "source": "test_man_page_context",
    }


async def _store_and_verify_fact(kb_v2, content: str, metadata: dict) -> int:
    """
    Store fact in knowledge base and verify retrieval.

    Issue #281: Extracted from test_single_man_page to reduce function length.

    Args:
        kb_v2: Initialized KnowledgeBase instance.
        content: The content to store.
        metadata: The metadata dictionary.

    Returns:
        0 on success, 1 on failure.
    """
    logger.info("\n4. Storing fact in Knowledge Base...")
    logger.info(f"   Content length: {len(content)} characters")
    logger.info(f"   Metadata fields: {len(metadata)}")

    result = await kb_v2.store_fact(content=content, metadata=metadata)

    if result.get("status") == "success":
        logger.info("✓ Fact stored successfully")
        fact_id = result.get("fact_id")
        logger.info(f"✓ Fact ID: {fact_id}")

        logger.info("\n5. Verifying stored fact...")
        stored_fact = await kb_v2.get_fact(fact_id)

        if stored_fact:
            logger.info("✓ Fact retrieved successfully")
            logger.info("\nStored Metadata:")
            logger.info(json.dumps(stored_fact.get("metadata", {}), indent=2))
        else:
            logger.warning("⚠ Could not retrieve stored fact")

        return 0
    else:
        logger.error(f"✗ Failed to store fact: {result}")
        return 1


async def test_single_man_page(command="ls", section="1"):
    """
    Test indexing a single man page with OS context.

    Issue #281: Extracted helpers _get_man_page_content(), _build_man_page_metadata(),
    and _store_and_verify_fact() to reduce function length from 162 to ~55 lines.
    """
    logger.info("=" * 80)
    logger.info(f"Testing Man Page OS Context: {command}({section})")
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

        # Get system context
        logger.info("\n2. Detecting system context...")
        system_ctx = get_system_context()

        logger.info(f"✓ Machine ID: {system_ctx['machine_id']}")
        logger.info(f"✓ Machine IP: {system_ctx['machine_ip']}")
        logger.info(f"✓ OS Name: {system_ctx['os_name']}")
        logger.info(f"✓ OS Version: {system_ctx['os_version']}")
        logger.info(f"✓ OS Type: {system_ctx['os_type']}")
        logger.info(f"✓ Architecture: {system_ctx['architecture']}")
        logger.info(f"✓ Kernel: {system_ctx['kernel_version']}")

        # Get compatible OS list
        compatible_oses = get_compatible_os_list(system_ctx["os_name"])
        logger.info(f"✓ Compatible with: {', '.join(compatible_oses)}")

        # Generate unique key
        unique_key = generate_unique_key(
            system_ctx["machine_id"], system_ctx["os_name"], command, section
        )
        logger.info(f"✓ Unique Key: {unique_key}")

        # Issue #281: Use extracted helper for man page content
        man_content, description = _get_man_page_content(command, section)
        if man_content is None:
            return 1

        # Build content
        content = f"""# {command}({section}) - {description}

**Machine:** {system_ctx['machine_id']} ({system_ctx['machine_ip']})
**OS:** {system_ctx['os_name']} {system_ctx['os_version']} ({system_ctx['os_type']})
**Architecture:** {system_ctx['architecture']}
**Section:** {section} (User Commands)

{man_content[:2000]}

---
*Full manual: `man {section} {command}`*
"""

        # Issue #281: Use extracted helper for metadata
        metadata = _build_man_page_metadata(
            command, section, system_ctx, compatible_oses, unique_key
        )

        # Issue #281: Use extracted helper for storing and verifying
        result = await _store_and_verify_fact(kb_v2, content, metadata)

        if result == 0:
            logger.info("\n" + "=" * 80)
            logger.info("TEST COMPLETE - OS Context System Working!")
            logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(test_single_man_page("ls", "1")))
