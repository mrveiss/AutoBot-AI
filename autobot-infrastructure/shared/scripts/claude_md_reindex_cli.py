# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-index CLAUDE.md in the knowledge base: propose the chunk deletion, then re-index once it is approved (#21383).

``--request`` raises the #17038 proposal that deletes the stale CLAUDE.md chunks (``--dry-run``, the default,
only lists what it would delete); the backend deletes them when an admin approves. ``--reindex`` then adds the
current CLAUDE.md, and refuses while old chunks remain so a re-index never duplicates them. This script deletes
nothing itself. Used by ``database/reindex_claude_md.sh``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# The shared wipe-request helpers sit beside this script; put them on the path when loaded by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kb_wipe_cli  # noqa: E402
from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[3]


async def request(dry_run: bool) -> bool:
    """List the chunks the deletion would remove; unless ``dry_run``, raise the approval proposal for it."""
    from services.claude_md_reindex_action import plan_claude_md_reindex, propose_claude_md_reindex

    plan = await plan_claude_md_reindex()
    selector = plan["selector"]
    logger.info(
        "   %s chunks with %s=%r in the %s database",
        plan["chunks"],
        selector["field"],
        selector["value"],
        selector["database"],
    )
    if dry_run:
        logger.info("   Dry run: nothing was deleted.")
        return True
    approval_id = await kb_wipe_cli.file_proposal(propose_claude_md_reindex, plan)
    logger.info("   Deletion requested (approval %s). Nothing is deleted until an admin approves it.", approval_id)
    return True


async def reindex() -> int:
    """Add the current CLAUDE.md. Refuses while chunks with its title remain: approve the deletion first."""
    from knowledge import KnowledgeBase
    from services.claude_md_reindex_action import SELECTOR_VALUE, plan_claude_md_reindex

    if (stale := (await plan_claude_md_reindex())["chunks"]) > 0:
        logger.error("%s stale CLAUDE.md chunks remain; run --request and have an admin approve it first", stale)
        return 1
    path = _REPO_ROOT / "CLAUDE.md"
    if not path.exists():
        logger.error("CLAUDE.md not found at %s; nothing was re-indexed", path)
        return 1
    content = path.read_text(encoding="utf-8")
    kb = KnowledgeBase()
    await kb._ensure_redis_initialized()
    metadata = {
        "title": SELECTOR_VALUE,
        "source": "autobot_docs",
        "category": "autobot_documentation",
        "file_path": str(path),
        "file_size": len(content),
        "indexed_at": datetime.now().isoformat(),
    }
    logger.info("Re-indexing result: %s", await kb.add_document(content=content, metadata=metadata, doc_id=None))
    return 0


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Request the CLAUDE.md chunk deletion, then re-index.")
    parser.add_argument("--request", action="store_true", help="ask for the deletion (needs admin approval)")
    parser.add_argument("--dry-run", action="store_true", help="list the chunks the deletion would remove (default)")
    parser.add_argument(
        "--reindex", action="store_true", help="after the approved deletion: index the current CLAUDE.md"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Exit code: 0 on success, 1 on failure."""
    args = _parse_args(argv)
    if args.reindex:
        return asyncio.run(reindex())
    return 0 if asyncio.run(request(dry_run=args.dry_run or not args.request)) else 1


if __name__ == "__main__":
    sys.exit(main())
