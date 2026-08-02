#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repair KB facts poisoned with empty vector documents (Issue #13277).

``BackgroundVectorizer`` inserted ``Document(text="")`` for every fact it
reconciled and then stamped ``vectorization_status=completed`` (#13274). The
stamp makes those facts invisible to the fixed reconciler, so they stay
unreachable by search until they are rebuilt from the (intact) Redis content.

Dry-run by default. Nothing is written without ``--apply``, and ``--apply``
refuses to run without an explicit fact-id scope.

Step 1 — census (read-only, safe to run any time)::

    python scripts/repair_kb_vector_index.py --census --write-ids-to affected-facts.txt

Step 2 — review ``affected-facts.txt``, then dry-run the exact scope::

    python scripts/repair_kb_vector_index.py --fact-ids-file affected-facts.txt

Step 3 — apply, once the dry-run plan looks right::

    python scripts/repair_kb_vector_index.py --fact-ids-file affected-facts.txt --apply

Step 4 — confirm: re-run step 2. A repaired index reports zero unreachable
facts and every id as ``already_clean``.

Exit codes: 0 clean, 1 one or more facts could not be repaired, 2 bad usage.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "autobot-backend"))
sys.path.insert(0, str(REPO_ROOT))

from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2


def _usage_error(message: str) -> NoReturn:
    """Refuse the run loudly with the dedicated usage exit code."""
    logger.error("%s", message)
    raise SystemExit(EXIT_USAGE)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repair_kb_vector_index.py",
        description="Repair facts whose vector rows contain an empty document (#13277).",
        epilog="Dry-run unless --apply is given. --apply requires an explicit fact-id scope.",
    )
    scope = parser.add_argument_group("scope (required for --apply)")
    scope.add_argument("--fact-id", action="append", default=[], metavar="ID", help="repeatable fact id to repair")
    scope.add_argument("--fact-ids-file", type=Path, metavar="PATH", help="file with one fact id per line")
    scope.add_argument(
        "--census",
        action="store_true",
        help="read-only survey of the whole collection; incompatible with --apply",
    )
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument(
        "--write-ids-to", type=Path, metavar="PATH", help="write the affected fact ids to a file for review"
    )
    parser.add_argument("--page-size", type=int, default=None, metavar="N", help="rows per scan page")
    return parser


def _read_ids_file(path: Path) -> List[str]:
    """Read one fact id per line, ignoring blanks and ``#`` comments."""
    if not path.is_file():
        _usage_error("fact-ids file not found: %s" % path)
    lines = path.read_text(encoding="utf-8").splitlines()
    return [stripped for stripped in (line.strip() for line in lines) if stripped and not stripped.startswith("#")]


def _resolve_fact_ids(args: argparse.Namespace) -> List[str] | None:
    """Turn the scope flags into an explicit id list, or ``None`` for a census."""
    ids = list(args.fact_id)
    if args.fact_ids_file:
        ids.extend(_read_ids_file(args.fact_ids_file))
    return list(dict.fromkeys(ids)) or None


def _validate(args: argparse.Namespace, fact_ids: List[str] | None) -> None:
    """Reject the argument combinations that could cause an unscoped write."""
    if args.census and args.apply:
        _usage_error("--census is read-only and cannot be combined with --apply")
    if args.census and fact_ids:
        _usage_error("--census surveys everything; drop --fact-id/--fact-ids-file to use it")
    if args.apply and not fact_ids:
        _usage_error("--apply needs an explicit scope: --fact-id and/or --fact-ids-file")
    if not args.census and not fact_ids:
        _usage_error("nothing to do: pass --census, --fact-id or --fact-ids-file")


async def _open_knowledge_base():
    """Initialise the KnowledgeBase singleton (no FastAPI app context needed)."""
    from knowledge_factory import get_knowledge_base_async

    kb = await get_knowledge_base_async()
    if kb is None:
        raise SystemExit("knowledge base failed to initialise — check the service logs")
    if not getattr(kb, "vector_store", None):
        raise SystemExit("vector store unavailable — refusing to run without somewhere to write vectors")
    return kb


def _open_collection(kb):
    """Return the live vector collection behind this knowledge base."""
    from knowledge.backends import get_default_client

    client = get_default_client(db_path=str(kb.chromadb_path), allow_reset=False, anonymized_telemetry=False)
    return client.get_collection(kb.chromadb_collection)


def _make_revectorizer(kb):
    """Wrap the fixed inline vectorization path, flushing any write buffer.

    The write buffer would otherwise leave the rewrite in memory, and the
    verification step would correctly — but unhelpfully — call it a failure.
    """

    async def revectorize(fact_id: str):
        result = await kb.vectorize_existing_fact(fact_id=fact_id)
        buffer = getattr(kb, "_write_buffer", None)
        if buffer is not None:
            await buffer.flush_now()
        return result

    return revectorize


def _write_ids(path: Path, fact_ids: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join("%s\n" % fact_id for fact_id in fact_ids), encoding="utf-8")
    logger.info("Wrote %d affected fact id(s) to %s", len(fact_ids), path)


async def _run(args: argparse.Namespace, fact_ids: List[str] | None) -> int:
    from knowledge.vector_repair import SCAN_PAGE_SIZE, FactStateStore, render_report, run_repair

    kb = await _open_knowledge_base()
    report = await run_repair(
        _open_collection(kb),
        FactStateStore(kb.redis_client),
        _make_revectorizer(kb),
        fact_ids=fact_ids,
        apply_changes=args.apply,
        page_size=args.page_size or SCAN_PAGE_SIZE,
    )

    for line in render_report(report):
        logger.info("%s", line)
    if args.write_ids_to:
        _write_ids(args.write_ids_to, report.scope)
    if report.failures:
        logger.error("%d fact(s) could not be repaired — see FAILURES above", len(report.failures))
        return EXIT_FAILURES
    return EXIT_OK


def main(argv: List[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    fact_ids = _resolve_fact_ids(args)
    _validate(args, fact_ids)
    if not args.apply:
        logger.info("DRY-RUN — no changes will be written. Re-run with --apply to write.")
    return asyncio.run(_run(args, fact_ids))


if __name__ == "__main__":
    os.environ.setdefault("AUTOBOT_LOG_LEVEL", "INFO")
    sys.exit(main())
