#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Request a reset of the knowledge base so its index is recreated with the correct dimensions.

The reset itself (dropping the index and deleting its keys) runs in the backend only after a human approves
the #17038 proposal this script raises; the script deletes nothing (#21383).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# The shared wipe-request helper sits beside this script; put it on the path when loaded by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kb_wipe_cli  # noqa: E402
from autobot_shared.logging_manager import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)


async def reset_knowledge_base_index(dry_run: bool = False) -> bool:
    """Request (or, with ``dry_run``, preview) the knowledge-base wipe. Deletes nothing."""
    logger.info("Resetting the knowledge base index: requesting a wipe through the approval gate")
    done = await kb_wipe_cli.request_wipe(dry_run)
    if done and not dry_run:
        logger.info("Once an admin approves it the index is recreated with correct dimensions on the next add.")
    return done


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Request a knowledge-base reset (needs admin approval).")
    parser.add_argument("--dry-run", action="store_true", help="list what the reset would delete; delete nothing")
    return parser.parse_args(argv)


if __name__ == "__main__":
    setup_logging()  # script startup: file logging on (#20894)
    args = _parse_args()
    sys.exit(0 if asyncio.run(reset_knowledge_base_index(dry_run=args.dry_run)) else 1)
