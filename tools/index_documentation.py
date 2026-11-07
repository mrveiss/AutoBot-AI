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

#18129: this is now the ONE documentation-indexing command. The two standalone
indexers under ``autobot-infrastructure/shared/`` were retired into shims that run
this module, so every flag they offered lives here and maps onto
``DocIndexerService``: ``--full`` / ``--reindex`` are aliases of ``--force``,
``--tier`` / ``--category`` narrow discovery, ``--file`` indexes one document,
``--dry-run`` prints ``DocIndexerService.plan``, ``--search`` / ``--stats`` read the
collection, ``--output`` writes the result as JSON.
"""

import argparse
import asyncio
import dataclasses
import json
import logging
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


def _add_mode_flags(parser: argparse.ArgumentParser) -> None:
    """Register the mutually exclusive indexing modes."""
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--incremental",
        action="store_true",
        help="Index only files whose content hash changed (the hook's mode).",
    )
    mode.add_argument(
        "--force",
        "--full",
        "--reindex",
        dest="force",
        action="store_true",
        help="Re-index and re-embed every file, ignoring the hash cache.",
    )
    mode.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Delete the collection first, then re-index from scratch (#16934). "
            "The one-time fix for branch docs that reached production before "
            "indexing was gated to main-at-origin-tip -- see "
            "docs/operations/DOC_INDEX_REBUILD.md before running this."
        ),
    )


def _add_scope_flags(parser: argparse.ArgumentParser) -> None:
    """Register the flags that narrow what is indexed, or read instead of index."""
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], help="Index one tier (1=critical, 2=high, 3=medium).")
    parser.add_argument("--category", help="Index only documents in this category (e.g. 'api', 'developer').")
    parser.add_argument("--file", help="Index one document (absolute, or relative to the repo root).")
    parser.add_argument("--dry-run", action="store_true", help="List the files that would be indexed; change nothing.")
    parser.add_argument("--search", help="Search the indexed documentation instead of indexing.")
    parser.add_argument("--results", type=int, default=5, help="Number of --search results (default: 5).")
    parser.add_argument("--stats", action="store_true", help="Show collection statistics instead of indexing.")
    parser.add_argument("--output", help="Write the indexing result to this path as JSON.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the CLI arguments. Kept importable so tests need no subprocess."""
    parser = argparse.ArgumentParser(
        prog="index_documentation.py",
        description="Index repository documentation into the knowledge base.",
    )
    _add_mode_flags(parser)
    _add_scope_flags(parser)
    return parser.parse_args(argv)


def _log_result(logger, result) -> int:
    """Report an IndexResult and return the process exit code."""
    # Report every error: a partial index that reports only the first is
    # how the tree and the index drift apart without anyone noticing.
    for error in result.errors:
        logger.error("Documentation indexing error: %s", error)
    logger.info(
        "Documentation indexing finished: %d indexed, %d failed, %d unchanged, " "%d discovered, %.2fs",
        result.success,
        result.failed,
        result.skipped,
        result.total_files,
        result.elapsed_seconds,
    )
    return 1 if (result.failed or result.errors) else 0


def _file_arg(args: argparse.Namespace) -> Path:
    """Resolve --file against the repo root unless it is absolute."""
    return Path(args.file) if Path(args.file).is_absolute() else REPO_ROOT / args.file


async def _index(service, args: argparse.Namespace):
    """Dispatch to the one service call the flags select."""
    if args.rebuild:
        return await service.rebuild_from_scratch()
    if args.file:
        path = _file_arg(args)
        return await service.index_file(path, tier=service.resolve_tier(path), force=args.force)
    return await service.index_all(force=args.force, tier=args.tier, category=args.category)


def _dry_run(logger, service, args: argparse.Namespace) -> int:
    """Log the files `index_all` would embed and change nothing."""
    if args.file:
        files = [(str(_file_arg(args)), service.resolve_tier(_file_arg(args)))]
    else:
        files = service.plan(force=args.force, tier=args.tier, category=args.category)
    for file_path, tier in files:
        logger.info("[DRY-RUN] tier %d: %s", tier, file_path)
    logger.info("[DRY-RUN] %d file(s) would be indexed", len(files))
    return 0


async def _read_collection(logger, service, args: argparse.Namespace) -> int:
    """Serve --search / --stats against the service's collection."""
    await service.initialize()
    if args.stats:
        logger.info("Documentation collection: %s", await service.get_stats())
        return 0
    for rank in await service.search(args.search, n_results=args.results):
        logger.info("[%.3f] %s: %s", rank.hybrid_score, rank.source_path, rank.content[:200])
    return 0


async def run_index(force: bool, rebuild: bool, args: argparse.Namespace | None = None) -> int:
    """Run the indexer and return a process exit code."""
    _install_import_paths()
    from autobot_shared.logging_manager import get_logger
    from services.knowledge.doc_indexer import get_doc_indexer_service

    logger = get_logger(__name__)
    service = get_doc_indexer_service()
    args = args or parse_args([])
    args.force, args.rebuild = force, rebuild
    if args.search or args.stats:
        return await _read_collection(logger, service, args)
    if args.dry_run:
        return _dry_run(logger, service, args)
    result = await _index(service, args)
    if args.output:
        Path(args.output).write_text(json.dumps(dataclasses.asdict(result), indent=2), encoding="utf-8")
    return _log_result(logger, result)


def main(argv: list[str] | None = None) -> int:
    """Entry point. `--incremental` is the default when no mode is given."""
    args = parse_args(argv)
    if args.verbose:
        from autobot_shared.logging_manager import LoggingManager

        LoggingManager.set_level(logging.DEBUG)
    return asyncio.run(run_index(force=args.force, rebuild=args.rebuild, args=args))


if __name__ == "__main__":
    sys.exit(main())
