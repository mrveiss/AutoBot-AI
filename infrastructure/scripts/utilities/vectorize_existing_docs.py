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

from src.knowledge_base import KnowledgeBase

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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

    Args:
        kb: KnowledgeBase instance
        fact_ids: List of fact IDs to vectorize
        batch_size: Number of facts per batch

    Returns:
        Summary dict with success/failure counts
    """
    total = len(fact_ids)
    success_count = 0
    error_count = 0
    skipped_count = 0
    errors = []

    logger.info("Starting vectorization of %d documentation facts...", total)

    for i in range(0, total, batch_size):
        batch = fact_ids[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        logger.info(
            "Processing batch %d/%d (%d facts)...", batch_num, total_batches, len(batch)
        )

        for fact_id in batch:
            try:
                result = await kb.vectorize_existing_fact(fact_id)

                if result.get("status") == "success":
                    success_count += 1
                elif result.get("status") == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1
                    errors.append(
                        {
                            "fact_id": fact_id,
                            "error": result.get("message", "Unknown error"),
                        }
                    )

            except Exception as e:
                error_count += 1
                errors.append({"fact_id": fact_id, "error": str(e)})

        # Progress update
        processed = min(i + batch_size, total)
        pct = (processed / total) * 100
        logger.info(
            "Progress: %d/%d (%.1f%%) - Success: %d, Errors: %d, Skipped: %d",
            processed,
            total,
            pct,
            success_count,
            error_count,
            skipped_count,
        )

    return {
        "total": total,
        "success": success_count,
        "errors": error_count,
        "skipped": skipped_count,
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
