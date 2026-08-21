# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Memory lifecycle observability — read-only admin view (#12631, umbrella #12630).

Facts move through `unverified → verified → reinforced → prune-eligible`, and none
of that was readable. `memory:consolidate_facts:last_run` had no readers,
`access_count` / `last_accessed` / the effective score were invisible, and the
nightly decay shipped inert and dry-run with no way to see what it *would* delete.

An operator could not answer "is decay working, and what is it about to remove"
except by reading code. That is the shape #13852 tracks: a mechanism that reports
nothing is indistinguishable from a mechanism with nothing to report.

Read-only by construction. Every path calls an existing getter or
`consolidate_facts(dry_run=True)`, which cannot delete. Degrades rather than
failing: an unreachable store yields a partial payload with `degraded: true`,
never a 500, because a monitoring endpoint that 500s tells an operator less than
one that says which half it could not read.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["memory-lifecycle"])

# Hard server-side ceiling. The `limit` query param is bounded by FastAPI, but the
# prune preview is bounded separately: it is the list an operator reviews before
# enabling enforcement, and an unbounded one is not reviewable.
_MAX_LIMIT = 100

_LAST_RUN_KEY = "memory:consolidate_facts:last_run"

_USAGE_FIELDS = ("fact_id", "quality_score", "access_count", "last_accessed")


def _slim(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Only the usage signals. The fact text itself is not an operator's business here."""
    return {key: fact.get(key) for key in _USAGE_FIELDS}


async def _reinforcement_section(limit: int) -> Dict[str, List[Dict[str, Any]]]:
    """Hottest and coldest facts by effective score.

    Both ends matter: the hot list shows reinforcement is happening at all, and the
    cold list is what decay will eventually reach. Showing only one would leave the
    other invisible, which is how this area got dark in the first place.
    """
    from knowledge import get_knowledge_base
    from memory import essential_story

    kb = await get_knowledge_base()
    facts = await kb.list_facts_with_usage()
    if not facts:
        return {"hot": [], "cold": []}

    now = datetime.now(tz=timezone.utc)
    max_access = max((int(f.get("access_count") or 0) for f in facts), default=0)
    scored = [{**_slim(f), "effective_score": essential_story._effective_score(f, now, max_access)} for f in facts]
    scored.sort(key=lambda f: f["effective_score"], reverse=True)
    return {"hot": scored[:limit], "cold": list(reversed(scored[-limit:]))}


async def _decay_section(limit: int) -> Dict[str, Any]:
    """Last run, resolved config, and what a prune would delete right now."""
    from knowledge import get_knowledge_base

    kb = await get_knowledge_base()
    section: Dict[str, Any] = {
        "last_run": None,
        "config": kb.prune_config_snapshot(),
        "prune_preview": [],
    }

    # The last-run key is read separately from the preview: its absence means the
    # scheduled task has never completed, which is a different fault from the
    # preview being empty, and collapsing the two would hide it.
    # Caught locally, not re-raised. Review found this section claimed independent
    # degradation in its own docstring while a Redis blip on the last-run key threw
    # away the already-computed config AND the not-yet-attempted preview — the
    # coupling the top-level split exists to avoid, reproduced one level down.
    # `last_run: None` is the honest answer to "could not read it".
    try:
        from autobot_shared.redis_client import get_async_redis_client

        # #12631 review: the WRITER decides which database this key lives in.
        # `workers/consolidate_tasks.py` writes it with database="analytics";
        # reading from "main" is a different logical database, so the key is
        # never found and `last_run` is permanently None — the exact "no
        # readers" state this endpoint exists to end, reproduced as a reader
        # that cannot read.
        client = await get_async_redis_client(database="analytics")
        if client is not None:
            raw = await client.get(_LAST_RUN_KEY)
            section["last_run"] = raw.decode() if isinstance(raw, bytes) else raw
    except Exception:
        logger.exception("memory lifecycle: last-run lookup failed")
        section["last_run_unavailable"] = True

    preview = await kb.consolidate_facts(dry_run=True)
    section["prune_preview"] = (preview.get("candidate_details") or [])[:_MAX_LIMIT]
    section["epoch_unset"] = bool(preview.get("epoch_unset"))
    return section


@router.get("/lifecycle")
@with_error_handling(error_code_prefix="MEMORY_LIFECYCLE")
async def get_memory_lifecycle(
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Read-only view of the memory lifecycle. Never mutates, never 500s."""
    degraded = False
    reinforcement: Dict[str, List[Dict[str, Any]]] = {"hot": [], "cold": []}
    decay: Dict[str, Any] = {"last_run": None, "config": {}, "prune_preview": []}

    # The two sections degrade independently. One store being unreachable must not
    # blank the half that is readable — a fully empty payload cannot be told apart
    # from a system with no facts.
    try:
        reinforcement = await _reinforcement_section(limit)
    except Exception:
        logger.exception("memory lifecycle: reinforcement section failed")
        degraded = True

    try:
        decay = await _decay_section(limit)
    except Exception:
        logger.exception("memory lifecycle: decay section failed")
        degraded = True

    return {"reinforcement": reinforcement, "decay": decay, "degraded": degraded}
