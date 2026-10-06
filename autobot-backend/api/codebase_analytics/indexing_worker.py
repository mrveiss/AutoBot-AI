# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Subprocess entry point for isolated codebase indexing (#1180).

Runs do_indexing_with_progress in a separate process so its ChromaDB
PersistentClient does not conflict with the KB's concurrent PersistentClient.
If this process crashes (SIGSEGV in chromadb_rust_bindings), the parent
uvicorn worker that launched it is unaffected.

Usage (internal — called by _run_indexing_subprocess):
    python indexing_worker.py <task_id> <root_path> [source_id]
"""

import logging
import os
import sys
from pathlib import Path

# Set up sys.path before importing project modules.
#
# #17631: the previous form was `if _p not in sys.path: sys.path.insert(0, _p)`,
# which is a no-op in production and left this worker unable to start at all.
#
# Python puts THIS FILE'S OWN DIRECTORY at sys.path[0] for a script run, and
# that directory contains `models.py` -- a module that shadows the backend's
# `models/` PACKAGE. The service unit already exports
# PYTHONPATH=<backend>:<backend>:<shared>:<root>, so every root below was
# already present, every `insert` was skipped, and sys.path[0] stayed the
# script directory. The deep import chain
#
#     scanner -> analyzers -> llm_shared -> anthropic_adapter
#             -> services.provider_key_vault -> `from models.secret import Secret`
#
# then resolved `models` to this directory's module and died with
# "No module named 'models.secret'; 'models' is not a package", exit code 1,
# on every single indexing run. The guard was meant to avoid duplicate entries;
# what it actually guarded against was the fix working whenever PYTHONPATH was
# set -- which is always, in production.
#
# So: force the roots to the FRONT regardless of whether they are already
# present, and drop the script directory, which must never win a top-level
# import. Order after this block is [backend, shared, repo root, ...].
_BACKEND_ROOT = Path(__file__).parent.parent.parent  # .../autobot-backend/
_SHARED_ROOT = _BACKEND_ROOT.parent / "autobot_shared"
_SCRIPT_DIR = str(Path(__file__).parent)

for _p in [str(_BACKEND_ROOT.parent), str(_SHARED_ROOT), str(_BACKEND_ROOT)]:
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

# The script directory shadows `models`, and nothing here is imported as a
# top-level name, so it has no business on the path.
while _SCRIPT_DIR in sys.path:
    sys.path.remove(_SCRIPT_DIR)

from api.codebase_analytics.scanner import do_indexing_with_progress  # noqa: E402
from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = get_logger(__name__)


def main() -> None:
    """Entry point: parse CLI args and run indexing task."""
    if len(sys.argv) < 3:
        logger.error("Usage: indexing_worker.py <task_id> <root_path>")
        sys.exit(1)

    # Issue #1303: Lower process priority so the embedding-heavy indexing
    # subprocess doesn't starve backend API workers of CPU.
    try:
        os.nice(10)
    except OSError:
        logger.debug("Could not set nice priority (non-root)")

    task_id = sys.argv[1]
    root_path = sys.argv[2]
    source_id = sys.argv[3] if len(sys.argv) > 3 else None

    logger.info(
        "[Worker] Starting indexing task=%s path=%s source=%s",
        task_id,
        root_path,
        source_id,
    )
    run_or_schedule(do_indexing_with_progress(task_id, root_path, source_id=source_id))
    logger.info("[Worker] Indexing task=%s finished", task_id)


if __name__ == "__main__":
    main()
