#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Simple demonstration of the AutoBot Codebase Indexing Service

This script demonstrates the key functionality without complex testing infrastructure.
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def _test_kb_connection():
    """Test knowledge base connection.

    Helper for demo_indexing (Issue #825).
    """
    logger.info("\n4️⃣  Testing knowledge base connection...")
    try:
        from knowledge_base_factory import get_knowledge_base

        kb = await get_knowledge_base()
        if kb:
            logger.info("✅ Knowledge base connection successful")

            try:
                stats = await kb.get_stats()
                logger.info(f"   Current facts: {stats.get('total_facts', 0)}")
                logger.info(f"   Current documents: {stats.get('total_documents', 0)}")
            except Exception as e:
                logger.error(f"   Stats error: {e}")
        else:
            logger.error("❌ Knowledge base connection failed")
            return None

        return kb
    except Exception as e:
        logger.error(f"❌ Knowledge base error: {e}")
        return None


async def _run_indexing_demo():
    """Run quick indexing demo.

    Helper for demo_indexing (Issue #825).
    """
    from services.codebase_indexing_service import index_autobot_codebase

    logger.info("\n5️⃣  Running quick indexing demo (3 files)...")
    try:
        progress = await index_autobot_codebase(max_files=3, batch_size=1)

        logger.info("✅ Quick indexing completed!")
        logger.info(f"   Files processed: {progress.processed_files}")
        logger.info(f"   Successful files: {progress.successful_files}")
        logger.info(f"   Chunks created: {progress.total_chunks}")
        logger.info(f"   Progress: {progress.progress_percentage:.1f}%")

        if progress.errors:
            logger.error(f"   Errors: {len(progress.errors)}")

        return True

    except Exception as e:
        logger.error(f"❌ Indexing demo failed: {e}")
        return False


async def _verify_results(kb):
    """Verify indexing results.

    Helper for demo_indexing (Issue #825).
    """
    logger.info("\n6️⃣  Verifying indexing results...")
    try:
        stats_after = await kb.get_stats()
        logger.info("✅ Updated statistics:")
        logger.info(f"   Total facts: {stats_after.get('total_facts', 0)}")
        logger.info(f"   Total documents: {stats_after.get('total_documents', 0)}")
        logger.info(f"   Categories: {stats_after.get('categories', [])}")

        facts_count = stats_after.get("total_facts", 0)
        if facts_count > 0:
            logger.info(f"✅ Knowledge base now contains {facts_count} indexed items")
        else:
            logger.warning("⚠️  No facts found in knowledge base")

    except Exception as e:
        logger.error(f"❌ Stats verification failed: {e}")


async def demo_indexing():
    """Demonstrate the codebase indexing functionality"""
    logger.info("🚀 AutoBot Codebase Indexing Service Demo")
    logger.info("=" * 50)

    try:
        logger.info("\n1️⃣  Importing indexing service...")
        from services.codebase_indexing_service import get_indexing_service

        logger.info("✅ Successfully imported codebase indexing service")

        logger.info("\n2️⃣  Creating indexing service...")
        service = get_indexing_service()
        logger.info(f"✅ Indexing service created for: {service.root_path}")
        logger.info(f"   Include patterns: {len(service.include_patterns)} file types")
        logger.info(f"   Category mapping: {len(service.category_mapping)} categories")

        logger.info("\n3️⃣  Scanning codebase files...")
        files = service._scan_files()
        logger.info(f"✅ Found {len(files)} indexable files")

        category_counts = {}
        for file_info in files[:50]:
            category = file_info.category
            category_counts[category] = category_counts.get(category, 0) + 1

        logger.info("   File breakdown by category:")
        for category, count in sorted(category_counts.items()):
            logger.info(f"     {category}: {count} files")

        kb = await _test_kb_connection()
        if not kb:
            return False

        if not await _run_indexing_demo():
            return False

        await _verify_results(kb)

        logger.info("\n🎉 Demo completed successfully!")
        return True

    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
        return False


async def main():
    """Main demo function"""
    success = await demo_indexing()

    logger.info("\n" + "=" * 50)
    if success:
        logger.info("✅ DEMO SUCCESSFUL")
        logger.info("\n🎯 The codebase indexing system is working correctly!")
        logger.info("\nNext steps:")
        logger.info("1. Start the AutoBot backend: scripts/start-services.sh start")
        logger.info("2. Use API endpoint: POST /api/knowledge/quick_index")
        logger.info("3. Check Knowledge Manager in the frontend")
        logger.info("4. Search the indexed codebase")
    else:
        logger.error("❌ DEMO FAILED")
        logger.error("Please check the error messages above.")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
