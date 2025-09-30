#!/usr/bin/env python3
"""
Index ALL Available Man Pages on AutoBot Machines
Indexes every command with a man page for comprehensive CLI tool awareness
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

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

async def index_command_batch(kb_v2, commands_batch, machine_id="main"):
    """Index a batch of commands"""
    indexed_count = 0

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

            # Build content
            content = f"""# {command}({section}) - {description}

**Machine:** {machine_id}
**Section:** {section} ({'User Commands' if section == '1' else 'Configuration Files' if section == '5' else 'System Administration'})

{man_content[:5000]}  # Limit to 5000 chars to avoid huge documents

---
*Full manual: `man {section} {command}`*
"""

            # Store in Knowledge Base
            result = await kb_v2.store_fact(
                content=content,
                metadata={
                    "type": "man_page",
                    "command": command,
                    "section": section,
                    "machine_id": machine_id,
                    "category": "system_commands",
                    "source": "comprehensive_man_pages",
                    "title": f"man {command}({section})"
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
        from src.knowledge_base_v2 import KnowledgeBaseV2

        logger.info("\n1. Initializing Knowledge Base V2...")
        kb_v2 = KnowledgeBaseV2()
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

        # Index in batches
        logger.info("\n3. Indexing man pages...")
        batch_size = 50
        total_indexed = 0

        for i in range(0, len(all_commands), batch_size):
            batch = all_commands[i:i+batch_size]
            batch_indexed = await index_command_batch(kb_v2, batch)
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