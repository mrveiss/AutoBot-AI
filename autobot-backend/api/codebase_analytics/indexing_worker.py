# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Subprocess entry point for isolated codebase indexing (#1180).

Runs do_indexing_with_progress in a separate process so its ChromaDB
PersistentClient does not conflict with the KB's concurrent PersistentClient.
If this process crashes (SIGSEGV in chromadb_rust_bindings), the parent
uvicorn worker that launched it is unaffected.

Usage (internal — called by _run_indexing_subprocess):
    python indexing_worker.py <task_id> <root_path>
"""
import asyncio
import logging
import sys
from pathlib import Path

# Set up sys.path before importing project modules.
# Required because subprocess env may not have PYTHONPATH set identically.
_BACKEND_ROOT = Path(__file__).parent.parent.parent  # .../autobot-backend/
_SHARED_ROOT = _BACKEND_ROOT.parent / "autobot-shared"
for _p in [str(_BACKEND_ROOT.parent), str(_SHARED_ROOT), str(_BACKEND_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.codebase_analytics.scanner import do_indexing_with_progress  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point: parse CLI args and run indexing task."""
    if len(sys.argv) < 3:
        logger.error("Usage: indexing_worker.py <task_id> <root_path>")
        sys.exit(1)

    task_id = sys.argv[1]
    root_path = sys.argv[2]

    logger.info("[Worker] Starting indexing task=%s path=%s", task_id, root_path)
    asyncio.run(do_indexing_with_progress(task_id, root_path))
    logger.info("[Worker] Indexing task=%s finished", task_id)


if __name__ == "__main__":
    main()
