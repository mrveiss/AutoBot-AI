#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CLI entry point for documentation indexing (#15845).

`post-commit-doc-sync` has looked for this path since #250 and never found it,
so the hook has printed its banner and exited 0 on every documentation commit.
The indexer itself was present the whole time as
``services.knowledge.doc_indexer.DocIndexerService`` -- a service class with no
``__main__``, so there was nothing for the hook to execute.

This module is that missing entry point and nothing more. It owns no indexing
logic: it resolves the process-level service through the canonical
``get_doc_indexer_service`` factory and calls ``index_all``.

``--incremental`` is ``index_all(force=False)``: the hash cache filters files
whose content has not changed. ``--force`` re-embeds everything. The two flags
are mutually exclusive because they name the same knob.
"""

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "autobot-backend"


def _install_import_paths() -> None:
    """Put the backend package root on `sys.path`, as the app's own entry points do.

    `autobot-backend` is hyphenated and so is not importable as a package; every
    caller of `services.knowledge.*` reaches it by path rather than by import.
    """
    for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the CLI arguments. Kept importable so tests need no subprocess."""
    parser = argparse.ArgumentParser(
        prog="index_documentation.py",
        description="Index repository documentation into the knowledge base.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--incremental",
        action="store_true",
        help="Index only files whose content hash changed (the hook's mode).",
    )
    mode.add_argument(
        "--force",
        action="store_true",
        help="Re-index and re-embed every file, ignoring the hash cache.",
    )
    return parser.parse_args(argv)


async def run_index(force: bool) -> int:
    """Run the indexer and return a process exit code."""
    _install_import_paths()
    from autobot_shared.logging_manager import get_logger
    from services.knowledge.doc_indexer import get_doc_indexer_service

    logger = get_logger(__name__)
    service = get_doc_indexer_service()
    result = await service.index_all(force=force)

    if result.errors:
        # Report every error: a partial index that reports only the first is
        # how the tree and the index drift apart without anyone noticing.
        for error in result.errors:
            logger.error("Documentation indexing error: %s", error)

    logger.info(
        "Documentation indexing finished: %d indexed, %d failed, %d unchanged, "
        "%d discovered, %.2fs",
        result.success,
        result.failed,
        result.skipped,
        result.total_files,
        result.elapsed_seconds,
    )
    return 1 if (result.failed or result.errors) else 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. `--incremental` is the default when no mode is given."""
    args = parse_args(argv)
    return asyncio.run(run_index(force=args.force))


if __name__ == "__main__":
    sys.exit(main())
