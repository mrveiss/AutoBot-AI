#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Vectorize Existing Documentation Facts Script

Issue #165: Documentation Indexing & Chat Integration

This script vectorizes existing documentation facts that were stored in Redis
but weren't properly vectorized in ChromaDB due to embedding generation issues.

Usage:
    python scripts/utilities/vectorize_existing_docs.py [--batch-size N] [--dry-run]
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from knowledge_base import KnowledgeBase

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _process_fact_result(fact_id: str, result: Dict[str, Any]) -> tuple:
    """
    Process vectorization result for a single fact.

    Helper for vectorize_facts_batch (#825).

    Args:
        fact_id: The fact ID being processed
        result: Result dictionary from vectorize_existing_fact

    Returns:
        Tuple of (success_delta, error_delta, skipped_delta, error_entry or None)
    """
    if result.get("status") == "success":
        return (1, 0, 0, None)
    elif result.get("status") == "skipped":
        return (0, 0, 1, None)
    else:
        error_entry = {
            "fact_id": fact_id,
            "error": result.get("message", "Unknown error"),
        }
        return (0, 1, 0, error_entry)


async def _process_batch(
    kb: KnowledgeBase, batch: List[str], counters: Dict[str, int], errors: List[Dict]
) -> None:
    """
    Process a single batch of facts.

    Helper for vectorize_facts_batch (#825).

    Args:
        kb: KnowledgeBase instance
        batch: List of fact IDs to process
        counters: Dictionary with success_count, error_count, skipped_count keys
        errors: List to append error entries to
    """
    for fact_id in batch:
        try:
            result = await kb.vectorize_existing_fact(fact_id)
            success_d, error_d, skipped_d, error_entry = _process_fact_result(
                fact_id, result
            )
            counters["success_count"] += success_d
            counters["error_count"] += error_d
            counters["skipped_count"] += skipped_d
            if error_entry:
                errors.append(error_entry)

        except Exception as e:
            counters["error_count"] += 1
            errors.append({"fact_id": fact_id, "error": str(e)})


async def get_documentation_fact_ids(kb: KnowledgeBase) -> List[str]:
    """
    Get all fact IDs that are documentation type.

    Returns:
        List of fact_id strings for documentation content
    """
    doc_fact_ids = []

    # Scan all fact keys
    cursor = 0
    while True:
        cursor, keys = kb.redis_client.scan(cursor, match="fact:*", count=1000)

        for key in keys:
            try:
                metadata_raw = kb.redis_client.hget(key, "metadata")
                if metadata_raw:
                    metadata = json.loads(metadata_raw)
                    if metadata.get("content_type") == "documentation":
                        fact_id = key.decode() if isinstance(key, bytes) else key
                        # Extract just the UUID part
                        fact_id = fact_id.replace("fact:", "")
                        doc_fact_ids.append(fact_id)
            except Exception as e:
                logger.debug("Error processing key %s: %s", key, e)

        if cursor == 0:
            break

    return doc_fact_ids


async def vectorize_facts_batch(
    kb: KnowledgeBase, fact_ids: List[str], batch_size: int = 50
) -> Dict[str, Any]:
    """
    Vectorize facts in batches with progress tracking.

    Issue #825: Extracted _process_fact_result and _process_batch helpers
    to reduce function length from 72 to ~40 lines.

    Args:
        kb: KnowledgeBase instance
        fact_ids: List of fact IDs to vectorize
        batch_size: Number of facts per batch

    Returns:
        Summary dict with success/failure counts
    """
    total = len(fact_ids)
    counters = {"success_count": 0, "error_count": 0, "skipped_count": 0}
    errors = []

    logger.info("Starting vectorization of %d documentation facts...", total)

    for i in range(0, total, batch_size):
        batch = fact_ids[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        logger.info(
            "Processing batch %d/%d (%d facts)...", batch_num, total_batches, len(batch)
        )

        await _process_batch(kb, batch, counters, errors)

        # Progress update
        processed = min(i + batch_size, total)
        pct = (processed / total) * 100
        logger.info(
            "Progress: %d/%d (%.1f%%) - Success: %d, Errors: %d, Skipped: %d",
            processed,
            total,
            pct,
            counters["success_count"],
            counters["error_count"],
            counters["skipped_count"],
        )

    return {
        "total": total,
        "success": counters["success_count"],
        "errors": counters["error_count"],
        "skipped": counters["skipped_count"],
        "error_details": errors[:10],  # Only first 10 errors
    }


async def main():
    parser = argparse.ArgumentParser(
        description="Vectorize existing documentation facts"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing (default: 50)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Count facts without vectorizing"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of facts to process (0 = all)",
    )

    args = parser.parse_args()

    logger.info("Initializing Knowledge Base...")
    kb = KnowledgeBase()
    await kb.initialize()

    if not kb.initialized:
        logger.error("Failed to initialize knowledge base")
        return 1

    # Get documentation fact IDs
    logger.info("Scanning for documentation facts...")
    doc_fact_ids = await get_documentation_fact_ids(kb)
    logger.info("Found %d documentation facts", len(doc_fact_ids))

    if args.dry_run:
        logger.info("DRY RUN - Would vectorize %d facts", len(doc_fact_ids))
        return 0

    # Apply limit if specified
    if args.limit > 0:
        doc_fact_ids = doc_fact_ids[: args.limit]
        logger.info("Limited to %d facts", len(doc_fact_ids))

    # Vectorize
    result = await vectorize_facts_batch(kb, doc_fact_ids, batch_size=args.batch_size)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("VECTORIZATION COMPLETE")
    logger.info("=" * 60)
    logger.info("Total Facts: %d", result["total"])
    logger.info("Successful: %d", result["success"])
    logger.info("Errors: %d", result["errors"])
    logger.info("Skipped: %d", result["skipped"])

    if result["error_details"]:
        logger.warning("\nFirst %d errors:", len(result["error_details"]))
        for err in result["error_details"]:
            logger.warning("  %s: %s", err["fact_id"], err["error"])

    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
