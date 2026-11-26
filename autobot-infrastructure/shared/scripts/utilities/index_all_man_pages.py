#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Index ALL Available Man Pages on AutoBot Machines
Indexes every command with a man page for comprehensive CLI tool awareness
Enhanced with OS/Machine context for deduplication and agent awareness

The ingestion itself lives in ``services.man_page_ingestion`` (#22272); this is its CLI entry,
also run by the Celery refresh task. Do not add a second writer here.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from services.man_page_ingestion import index_all_man_pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """Index every man page; the work and its counts come from ``index_all_man_pages`` (#22272)."""
    logger.info("COMPREHENSIVE MAN PAGE INDEXING")
    try:
        result = await index_all_man_pages()
    except Exception as e:
        logger.error("Indexing failed: %s", e)
        import traceback

        traceback.print_exc()
        return 1
    logger.info("INDEXING COMPLETE")
    logger.info("Commands scanned: %s", result["commands_scanned"])
    logger.info("Successfully indexed: %s", result["commands_indexed"])
    logger.info("Total facts in KB: %s", result["total_facts"])
    logger.info("Total vectors: %s", result["total_vectors"])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
