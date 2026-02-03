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
        # Use man -k . to list ALL man pages (Issue #479: Use async subprocess)
        process = await asyncio.create_subprocess_exec(
            'man', '-k', '.',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=30
            )
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
        for line in result_stdout.split('\n'):
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
        logger.info("Found %s commands to index", len(commands))

        return commands

    except Exception as e:
        logger.error("Error scanning commands: %s", e)
        return []


async def index_command_batch(kb_v2, commands_batch, system_ctx=None):
    """Index a batch of commands with OS/machine context"""
    indexed_count = 0

    # Get system context once for the batch
    if system_ctx is None:
        system_ctx = get_system_context()

    for command, section in commands_batch:
        try:
            # Get man page content (Issue #479: Use async subprocess)
            env = os.environ.copy()
            env['MANWIDTH'] = '80'

            process = await asyncio.create_subprocess_exec(
                'man', section, command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=10
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                continue

            if process.returncode != 0:
                continue

            # Clean output
            man_content = stdout.decode().strip()

            # Get description from man -k (Issue #479: Use async subprocess)
            desc_process = await asyncio.create_subprocess_exec(
                'man', '-k', f'^{command}$',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                desc_stdout, _ = await asyncio.wait_for(
                    desc_process.communicate(), timeout=5
                )
            except asyncio.TimeoutError:
                desc_process.kill()
                await desc_process.wait()
                desc_stdout = b""

            description = "System command"
            if desc_process.returncode == 0:
                for line in desc_stdout.decode().split('\n'):
                    if command in line and '-' in line:
                        description = line.split('-', 1)[1].strip()
                        break

            # Build content with enhanced context
            content = """# {command}({section}) - {description}

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
            logger.debug("Timeout for %s", command)
            continue
        except Exception as e:
            logger.debug("Error indexing %s: %s", command, e)
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

        logger.info("✓ Found %s commands to index", len(all_commands))

        # Get system context for indexing
        logger.info("\n3. Detecting system context...")
        system_ctx = get_system_context()
        logger.info("✓ Machine: %s (%s)", system_ctx['machine_id'], system_ctx['machine_ip'])
        logger.info("✓ OS: %s %s", system_ctx['os_name'], system_ctx['os_version'])
        logger.info("✓ Architecture: %s", system_ctx['architecture'])
        logger.info("✓ Compatible with: %s", ', '.join(get_compatible_os_list(system_ctx['os_name'])))

        # Index in batches
        logger.info("\n4. Indexing man pages...")
        batch_size = 50
        total_indexed = 0

        for i in range(0, len(all_commands), batch_size):
            batch = all_commands[i:i+batch_size]
            batch_indexed = await index_command_batch(kb_v2, batch, system_ctx)
            total_indexed += batch_indexed

            progress = min(i + batch_size, len(all_commands))
            logger.info("Progress: %s/%s (%s indexed)", progress, len(all_commands), total_indexed)

        # Get final stats
        stats = await kb_v2.get_stats()

        logger.info("\n" + "=" * 80)
        logger.info("INDEXING COMPLETE")
        logger.info("=" * 80)
        logger.info("✓ Commands scanned: %s", len(all_commands))
        logger.info("✓ Successfully indexed: %s", total_indexed)
        logger.info("✓ Total facts in KB: %s", stats.get('total_facts', 0))
        logger.info("✓ Total vectors: %s", stats.get('total_vectors', 0))
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error("✗ Indexing failed: %s", e)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
