# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Background Tasks for AutoBot

Celery tasks for long-running knowledge base operations with progress tracking.
"""

import logging
import subprocess
import sys
from typing import Dict, Any

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.refresh_system_knowledge")
def refresh_system_knowledge(self) -> Dict[str, Any]:
    """
    Refresh ALL system knowledge (man pages + AutoBot docs) in background.

    This is a long-running operation (can take up to 10 minutes) that indexes
    all system man pages and AutoBot documentation into the knowledge base.

    Args:
        self: Celery task instance (bound for progress updates)

    Returns:
        Dict with refresh results:
            - commands_indexed: Number of commands indexed
            - total_facts: Total facts in knowledge base
            - status: 'success' or 'failed'
    """
    try:
        # Update state to show we've started
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 100,
                'status': 'Starting system knowledge refresh...'
            }
        )

        logger.info("Starting comprehensive system knowledge refresh (background task)...")

        # Run the comprehensive indexing script
        # No timeout here - let it run as long as needed
        result = subprocess.run(
            [sys.executable, "scripts/utilities/index_all_man_pages.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            # Parse output for statistics
            output_lines = result.stdout.split("\n")
            indexed_count = 0
            total_facts = 0

            for line in output_lines:
                if "Successfully indexed:" in line:
                    indexed_count = int(line.split(":")[1].strip())
                elif "Total facts in KB:" in line:
                    total_facts = int(line.split(":")[1].strip())

            logger.info(
                f"System knowledge refresh complete: {indexed_count} commands indexed, "
                f"{total_facts} total facts"
            )

            return {
                "status": "success",
                "commands_indexed": indexed_count,
                "total_facts": total_facts,
                "message": "System knowledge refreshed successfully"
            }
        else:
            error_msg = result.stderr[:500] if result.stderr else "Unknown error"
            logger.error(f"System knowledge refresh failed: {error_msg}")

            return {
                "status": "failed",
                "error": error_msg,
                "message": "Knowledge refresh failed"
            }

    except Exception as e:
        logger.exception(f"System knowledge refresh task failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Knowledge refresh failed: {str(e)}"
        }


@celery_app.task(bind=True, name="tasks.reindex_knowledge_base")
def reindex_knowledge_base(self) -> Dict[str, Any]:
    """
    Reindex the entire knowledge base (rebuild vector indexes).

    This operation can take several minutes for large knowledge bases.

    Args:
        self: Celery task instance (bound for progress updates)

    Returns:
        Dict with reindex results
    """
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 100,
                'status': 'Starting knowledge base reindexing...'
            }
        )

        logger.info("Starting knowledge base reindex (background task)...")

        # Import here to avoid circular dependencies
        from src.knowledge_base import KnowledgeBase
        import asyncio

        # Run async reindex in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            kb = KnowledgeBase()
            result = loop.run_until_complete(kb.initialize())

            # Get updated stats
            stats = loop.run_until_complete(kb.get_stats())

            logger.info(f"Knowledge base reindex complete: {stats.get('total_vectors', 0)} vectors")

            return {
                "status": "success",
                "total_vectors": stats.get("total_vectors", 0),
                "total_facts": stats.get("total_facts", 0),
                "message": "Knowledge base reindexed successfully"
            }
        finally:
            loop.close()

    except Exception as e:
        logger.exception(f"Knowledge base reindex task failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Reindex failed: {str(e)}"
        }
