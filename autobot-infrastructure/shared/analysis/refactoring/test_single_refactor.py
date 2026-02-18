#!/usr/bin/env python3
"""
Test refactoring on a single file to validate the approach
"""

import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import unified_config_manager
from constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


def test_refactor_single_file():
    """Test refactoring on config_consolidated.py"""
    # Use project-relative path instead of hardcoded absolute path
    project_root = Path(__file__).parent.parent.parent
    file_path = project_root / "src" / "config_consolidated.py"

    with open(file_path, "r") as f:
        content = f.read()

    logger.info("Original IPs found:")
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        if "172.16.168" in line:
            logger.info(f"  Line {i}: {line.strip()}")

    # Get configuration values (use NetworkConstants as fallback)
    redis_config = unified_config_manager.get_redis_config()
    redis_host = redis_config.get("host", NetworkConstants.REDIS_VM_IP)

    # Test replacement patterns (dynamically from config)
    replacements = {
        '"172.16.168.20"': "NetworkConstants.MAIN_MACHINE_IP",
        '"172.16.168.21"': "NetworkConstants.FRONTEND_VM_IP",
        f'"{redis_host}"': "NetworkConstants.REDIS_VM_IP",
        '"172.16.168.24"': "NetworkConstants.AI_STACK_VM_IP",
        '"172.16.168.25"': "NetworkConstants.BROWSER_VM_IP",
    }

    new_content = content
    for old, new in replacements.items():
        new_content = new_content.replace(old, new)

    logger.info("\nAfter replacement:")
    new_lines = new_content.split("\n")
    for i, line in enumerate(new_lines, 1):
        if "NetworkConstants" in line:
            logger.info(f"  Line {i}: {line.strip()}")

    # Check if import is needed
    if (
        "NetworkConstants" in new_content
        and "from constants import NetworkConstants" not in new_content
    ):
        logger.info(
            "\nWould need to add import: from constants import NetworkConstants"
        )

    logger.info(f"\nChanges made: {content != new_content}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_refactor_single_file()
