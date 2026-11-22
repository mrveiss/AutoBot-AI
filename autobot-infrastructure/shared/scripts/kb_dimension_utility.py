#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fix knowledge base dimension mismatch by recreating with correct settings.

The destructive half (dropping the llama_index index and its keys) is a #17038 wipe proposal: run with
``--request-wipe`` to raise it, ``--dry-run`` to preview it. This script itself deletes nothing (#21383).
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Runs from any directory with no PYTHONPATH: put the repository root on the path for
# `autobot_shared` (#18964).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The shared wipe-request helper sits beside this script; put it on the path when loaded by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kb_wipe_cli  # noqa: E402


async def fix_dimensions():
    """Initialise a fresh knowledge base and test it. Run after an approved wipe; it deletes nothing."""
    logger.info("\nTesting with the correct embedding model...")

    from knowledge_factory import get_knowledge_base_async

    # Create a fresh knowledge base
    kb = await get_knowledge_base_async()
    if kb is None:
        raise RuntimeError("Knowledge base unavailable: initialization failed or retry cooldown active")
    logger.info(f"Knowledge base will use Redis DB: {kb.redis_db}")
    logger.info("Knowledge base initialized")

    # Test adding a simple document
    test_content = "AutoBot is an autonomous AI agent platform."
    from llama_index.core import Document

    try:
        doc = Document(text=test_content, metadata={"source": "test"})
        kb.index.insert(doc)
        logger.info("Successfully added test document!")

        # Test search
        results = await kb.search("AutoBot", n_results=1)
        logger.info(f"Search test: Found {len(results)} results")

        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Request the KB wipe, or test the KB after an approved wipe.")
    kb_wipe_cli.add_wipe_arguments(parser)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Run the dimension fix; the process exit code: 0 on success, 1 on failure."""
    args = _parse_args(argv)
    if kb_wipe_cli.wipe_wanted(args):
        return 0 if asyncio.run(kb_wipe_cli.request_wipe(args.dry_run)) else 1
    if asyncio.run(fix_dimensions()):
        logger.info("\nKnowledge base is now ready! You can run populate_knowledge_base.py")
        return 0
    logger.error("\nFailed to fix dimensions issue")
    return 1


if __name__ == "__main__":
    sys.exit(main())
