#!/usr/bin/env python3
"""
Test Man Page OS Context System
Index a single man page to verify OS/machine context detection
"""

import asyncio
import logging
import subprocess
import sys
import json
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


async def test_single_man_page(command="ls", section="1"):
    """Test indexing a single man page with OS context"""
    logger.info("=" * 80)
    logger.info(f"Testing Man Page OS Context: {command}({section})")
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
        compatible_oses = get_compatible_os_list(system_ctx['os_name'])
        logger.info(f"✓ Compatible with: {', '.join(compatible_oses)}")

        # Generate unique key
        unique_key = generate_unique_key(
            system_ctx['machine_id'],
            system_ctx['os_name'],
            command,
            section
        )
        logger.info(f"✓ Unique Key: {unique_key}")

        # Get man page content
        logger.info(f"\n3. Fetching man page content for {command}({section})...")
        result = subprocess.run(
            ['man', section, command],
            capture_output=True,
            text=True,
            timeout=10,
            env={'MANWIDTH': '80'}
        )

        if result.returncode != 0:
            logger.error(f"✗ Failed to get man page for {command}({section})")
            return 1

        man_content = result.stdout.strip()
        logger.info(f"✓ Man page retrieved ({len(man_content)} characters)")

        # Get description
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

        logger.info(f"✓ Description: {description}")

        # Build content
        content = f"""# {command}({section}) - {description}

**Machine:** {system_ctx['machine_id']} ({system_ctx['machine_ip']})
**OS:** {system_ctx['os_name']} {system_ctx['os_version']} ({system_ctx['os_type']})
**Architecture:** {system_ctx['architecture']}
**Section:** {section} (User Commands)

{man_content[:2000]}  # Truncated for testing

---
*Full manual: `man {section} {command}`*
"""

        # Build metadata
        metadata = {
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
            "applies_to_os": compatible_oses,

            # Unique key for deduplication
            "unique_key": unique_key,

            # Standard fields
            "category": "system_commands",
            "source": "test_man_page_context"
        }

        # Store in Knowledge Base
        logger.info(f"\n4. Storing fact in Knowledge Base...")
        logger.info(f"   Content length: {len(content)} characters")
        logger.info(f"   Metadata fields: {len(metadata)}")

        result = await kb_v2.store_fact(
            content=content,
            metadata=metadata
        )

        if result.get('status') == 'success':
            logger.info(f"✓ Fact stored successfully")
            fact_id = result.get('fact_id')
            logger.info(f"✓ Fact ID: {fact_id}")

            # Retrieve and display the stored fact
            logger.info(f"\n5. Verifying stored fact...")
            stored_fact = await kb_v2.get_fact(fact_id)

            if stored_fact:
                logger.info(f"✓ Fact retrieved successfully")
                logger.info(f"\nStored Metadata:")
                logger.info(json.dumps(stored_fact.get('metadata', {}), indent=2))
            else:
                logger.warning(f"⚠ Could not retrieve stored fact")

        else:
            logger.error(f"✗ Failed to store fact: {result}")
            return 1

        logger.info("\n" + "=" * 80)
        logger.info("TEST COMPLETE - OS Context System Working!")
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(test_single_man_page("ls", "1")))
