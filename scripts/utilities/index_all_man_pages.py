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
import subprocess
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.system_context import (
    get_system_context,
    get_compatible_os_list,
    generate_unique_key
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def get_all_available_commands():
    """Get ALL commands with man pages on this system"""
    logger.info("Scanning for all available commands with man pages...")

    try:
        # Use man -k . to list ALL man pages
        result = subprocess.run(
            ['man', '-k', '.'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error("Failed to list man pages")
            return []

        commands = []
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue

            # Parse format: command (section) - description
            parts = line.split('(')
            if len(parts) < 2:
                continue

            command_name = parts[0].strip()
            section_part = parts[1].split(')')[0]

            # Only index sections 1, 5, 8 (user commands, config files, admin commands)
            if section_part in ['1', '5', '8']:
                commands.append((command_name, section_part))

        # Remove duplicates
        commands = list(set(commands))
        logger.info(f"Found {len(commands)} commands to index")

        return commands

    except Exception as e:
        logger.error(f"Error scanning commands: {e}")
        return []


async def index_command_batch(kb_v2, commands_batch, system_ctx=None):
    """Index a batch of commands with OS/machine context"""
    indexed_count = 0

    # Get system context once for the batch
    if system_ctx is None:
        system_ctx = get_system_context()

    for command, section in commands_batch:
        try:
            # Get man page content
            result = subprocess.run(
                ['man', section, command],
                capture_output=True,
                text=True,
                timeout=10,
                env={'MANWIDTH': '80'}
            )

            if result.returncode != 0:
                continue

            # Clean output
            man_content = result.stdout.strip()

            # Get description from man -k
            desc_result = subprocess.run(
                ['man', '-k', f'^{command}$'],
                capture_output=True,
                text=True,
                timeout=5
            )

            description = "System command"
            if desc_result.returncode == 0:
                for line in desc_result.stdout.split('\n'):
                    if command in line and '-' in line:
                        description = line.split('-', 1)[1].strip()
                        break

            # Build content with enhanced context
            content = f"""# {command}({section}) - {description}

**Machine:** {system_ctx['machine_id']} ({system_ctx['machine_ip']})
**OS:** {system_ctx['os_name']} {system_ctx['os_version']} ({system_ctx['os_type']})
**Architecture:** {system_ctx['architecture']}
**Section:** {section} ({'User Commands' if section == '1' else 'Configuration Files' if section == '5' else 'System Administration'})

{man_content[:5000]}  # Limit to 5000 chars to avoid huge documents

---
*Full manual: `man {section} {command}`*
"""

            # Generate unique key for deduplication
            unique_key = generate_unique_key(
                system_ctx['machine_id'],
                system_ctx['os_name'],
                command,
                section
            )

            # Store in Knowledge Base with enhanced metadata
            result = await kb_v2.store_fact(
                content=content,
                metadata={
                    "type": "man_page",
                    "command": command,
                    "section": section,
                    "title": f"man {command}({section})",

                    # Machine/OS Context
                    "machine_id": system_ctx['machine_id'],
                    "machine_ip": system_ctx['machine_ip'],
                    "os_name": system_ctx['os_name'],
                    "os_version": system_ctx['os_version'],
                    "os_type": system_ctx['os_type'],
                    "architecture": system_ctx['architecture'],
                    "kernel_version": system_ctx['kernel_version'],

                    # Applicability
                    "applies_to_machines": [system_ctx['machine_id']],
                    "applies_to_os": get_compatible_os_list(system_ctx['os_name']),

                    # Unique key for deduplication
                    "unique_key": unique_key,

                    # Standard fields
                    "category": "system_commands",
                    "source": "comprehensive_man_pages"
                }
            )

            if result.get('status') == 'success':
                indexed_count += 1

        except subprocess.TimeoutExpired:
            logger.debug(f"Timeout for {command}")
            continue
        except Exception as e:
            logger.debug(f"Error indexing {command}: {e}")
            continue

    return indexed_count


async def main():
    """Main indexing function"""
    logger.info("=" * 80)
    logger.info("COMPREHENSIVE MAN PAGE INDEXING")
    logger.info("=" * 80)

    try:
        # Initialize Knowledge Base V2
        from src.knowledge_base import KnowledgeBase

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

        logger.info(f"✓ Found {len(all_commands)} commands to index")

        # Get system context for indexing
        logger.info("\n3. Detecting system context...")
        system_ctx = get_system_context()
        logger.info(f"✓ Machine: {system_ctx['machine_id']} ({system_ctx['machine_ip']})")
        logger.info(f"✓ OS: {system_ctx['os_name']} {system_ctx['os_version']}")
        logger.info(f"✓ Architecture: {system_ctx['architecture']}")
        logger.info(f"✓ Compatible with: {', '.join(get_compatible_os_list(system_ctx['os_name']))}")

        # Index in batches
        logger.info("\n4. Indexing man pages...")
        batch_size = 50
        total_indexed = 0

        for i in range(0, len(all_commands), batch_size):
            batch = all_commands[i:i+batch_size]
            batch_indexed = await index_command_batch(kb_v2, batch, system_ctx)
            total_indexed += batch_indexed

            progress = min(i + batch_size, len(all_commands))
            logger.info(f"Progress: {progress}/{len(all_commands)} ({total_indexed} indexed)")

        # Get final stats
        stats = await kb_v2.get_stats()

        logger.info("\n" + "=" * 80)
        logger.info("INDEXING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"✓ Commands scanned: {len(all_commands)}")
        logger.info(f"✓ Successfully indexed: {total_indexed}")
        logger.info(f"✓ Total facts in KB: {stats.get('total_facts', 0)}")
        logger.info(f"✓ Total vectors: {stats.get('total_vectors', 0)}")
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error(f"✗ Indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
