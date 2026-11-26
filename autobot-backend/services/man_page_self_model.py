# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Man-page facts and the self-model's ``command`` entities (#22272, #22299).

A fact records the stable key of the ``command`` entity it describes (``autobot_shared.self_model_keys``, the
formula the SLM uses), under the SLM node id the fact's host address maps to (``slm_self_model.node_ids_for_hosts``
-> the SLM's own ``node_ids_by_host``). On ``self_model.changed``, ``reconcile_staleness`` marks the facts whose
command the model holds ``absent`` or ``stale`` on their host, and clears the mark of a command that is back.
A marked fact is never deleted (#17038).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.self_model_keys import command_key
from knowledge.fact_store import iter_facts
from knowledge.stale_marker import STALE_FIELD
from models.knowledge_fact import KnowledgeFact
from services.slm_self_model import SelfModelUnavailable, node_ids_for_hosts, query_entities

logger = get_logger(__name__)

MAN_PAGE_TYPE = "man_page"
#: Metadata fields linking a fact to the entity it describes.
NODE_FIELD = "self_model_node_id"
KEY_FIELD = "self_model_entity_key"
_UNAVAILABLE = ("absent", "stale")
_PAGE = 500  # the SLM's entity page ceiling


def link_fields(node_id: Optional[str], command: str) -> Dict[str, str]:
    """The metadata linking a fact for *command* to its ``command`` entity; empty when the host is not a node."""
    if not node_id:
        return {}
    return {NODE_FIELD: node_id, KEY_FIELD: command_key(node_id, command)}


async def _node_ids(hosts: List[str]) -> Dict[str, str]:
    """``node_ids_for_hosts``, or ``{}`` with a warning when the SLM cannot answer (facts then stay unlinked)."""
    try:
        return await node_ids_for_hosts(hosts)
    except (SelfModelUnavailable, aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("self-model node ids unavailable; man-page facts stay unlinked: %s", exc)
        return {}


async def host_node_id(host: str) -> Optional[str]:
    """The SLM node id of *host*, or None (not a managed node, or the SLM is unreachable)."""
    return (await _node_ids([host])).get(host)


async def unavailable_commands() -> Dict[str, str]:
    """``entity_key -> status`` of every command entity the model holds ``absent`` or ``stale``."""
    found: Dict[str, str] = {}
    for status in _UNAVAILABLE:
        offset = 0
        while True:
            page = await query_entities({"kind": "command", "status": status, "limit": _PAGE, "offset": offset})
            found.update({row["entity_key"]: row["status"] for row in page["entities"]})
            offset += _PAGE
            if offset >= page["total"]:
                break
    return found


async def _fact_changes(batch: List[Dict[str, Any]], bad: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """``fact_id -> metadata update`` for the facts of *batch* whose link or stale mark is out of date."""
    nodes = await _node_ids(sorted({f["metadata"].get("machine_ip") for f in batch if f["metadata"].get("machine_ip")}))
    changes: Dict[str, Dict[str, str]] = {}
    for fact in batch:
        meta = fact["metadata"]
        link = {} if meta.get(KEY_FIELD) else link_fields(nodes.get(meta.get("machine_ip")), meta.get("command", ""))
        want = bad.get(meta.get(KEY_FIELD) or link.get(KEY_FIELD), "")
        if want != (meta.get(STALE_FIELD) or "") or link:
            changes[fact["fact_id"]] = {**link, STALE_FIELD: want}
    return changes


async def reconcile_staleness(kb) -> Dict[str, int]:
    """Bring every man-page fact's stale mark in line with the self-model; returns checked/updated/failed counts."""
    bad = await unavailable_commands()
    counts = {"checked": 0, "updated": 0, "failed": 0}
    where = (KnowledgeFact.metadata_json["type"].astext == MAN_PAGE_TYPE,)
    async for batch in iter_facts(where=where):
        counts["checked"] += len(batch)
        for fact_id, update in (await _fact_changes(batch, bad)).items():
            result = await kb.update_fact(fact_id, metadata=update)
            counts["updated" if result.get("status") == "success" else "failed"] += 1
    return counts


async def on_self_model_changed(_event: Dict[str, Any]) -> None:
    """``self_model.changed`` listener: refresh the stale marks of the man-page facts."""
    from services.man_page_ingestion import _ready_knowledge_base  # noqa: PLC0415

    counts = await reconcile_staleness(await _ready_knowledge_base())
    log = logger.warning if counts["failed"] else logger.info
    log("man-page stale marks reconciled: %s", counts)
