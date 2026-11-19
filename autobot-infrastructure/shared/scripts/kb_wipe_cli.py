# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one way an operator script asks for a knowledge-base wipe: it proposes, it never deletes (#21383).

The KB reset scripts used to drop the search index with its documents or delete keys themselves. The
wipe now runs in the backend only after a human approves the #17038 proposal (``services.kb_wipe_action``),
so every script shares this entry: ``--request-wipe`` raises (or reuses) the pending proposal, ``--dry-run``
lists what a wipe would delete and raises nothing. A run with neither flag deletes nothing either.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# A backend tool (#18288): it drives the backend's wipe service, so it puts the backend and the repository
# root (for `autobot_shared`) on its own path and runs from any directory with no PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[3]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)


def add_wipe_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the two flags every KB reset script shares."""
    parser.add_argument("--request-wipe", action="store_true", help="ask for the knowledge-base wipe (needs approval)")
    parser.add_argument("--dry-run", action="store_true", help="list what the wipe would delete; delete nothing")


def wipe_wanted(args: argparse.Namespace) -> bool:
    """True when the operator asked for the wipe or its preview instead of the script's non-destructive work."""
    return bool(args.request_wipe or args.dry_run)


def log_plan(plan: dict) -> None:
    """Log what a wipe would delete, store by store."""
    for store in plan["databases"]:
        logger.info("   Database %s: %s keys (%s)", store["database"], store["keys"], store["note"])
        for index in store["indexes"]:
            logger.info("   Index %s: %s documents", index["name"], index["documents"])
    for collection in plan["chroma_collections"]:
        logger.info("   Chroma collection %s: %s vectors", collection["name"], collection["vectors"])
    logger.info("   Total keys: %s, total vectors: %s", plan["total_keys"], plan["total_vectors"])


async def propose_wipe(plan: dict) -> str:
    """Raise (or reuse) the human-approval proposal for the wipe; return its approval id. Deletes nothing."""
    from services.kb_wipe_action import CHANNEL_OPERATOR, propose_kb_wipe
    from user_management.database import get_async_session_factory

    async with get_async_session_factory()() as db:
        approval = await propose_kb_wipe(db, getpass.getuser(), plan, channel=CHANNEL_OPERATOR)
    return str(approval.id)


async def request_wipe(dry_run: bool) -> bool:
    """Dry run lists the KB stores; otherwise request approval. Neither deletes anything (#21383, #21048)."""
    from services.kb_wipe_action import plan_kb_wipe

    plan = await plan_kb_wipe()
    log_plan(plan)
    if dry_run:
        logger.info("   Dry run: nothing was deleted.")
        return True
    approval_id = await propose_wipe(plan)
    logger.info("   Wipe requested (approval %s). Nothing is deleted until an admin approves it.", approval_id)
    return True
