# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend producers of the SLM self-model (#22277).

On a schedule, the route, tool and agent catalogues are pushed as ``declared`` entities and the
service-health snapshot as ``probed_ok`` / ``probed_failed`` services. Each catalogue is one complete
batch for its kinds, so an entity the backend stopped declaring becomes ``absent`` in the model.
The accessors (``route_records``, ``tool_records``, ``agent_records``, ``read_snapshot``) are the
catalogue of record; nothing here restates a name list.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from fastapi import FastAPI

from api.self_capabilities import route_records
from autobot_shared.logging_manager import get_logger
from autobot_shared.self_model_constants import PUSH_INTERVAL_S
from events.bus import PersistStrategy, publish_event
from events.event_types import SELF_MODEL_CHANGED
from orchestration.agent_record import agent_records
from services.service_health_probe import read_snapshot
from services.slm_self_model import push_observations
from tools.tool_records import tool_records

logger = get_logger(__name__)

CATALOGUE_SOURCE = "backend_catalogue"
HEALTH_SOURCE = "backend_service_health"
_SERVICE = "service"
_HEALTHY = "healthy"
_NAME_MAX = 255  # the SLM entity name column
_EVENT_CHANNEL = "global"
_PROBED_FAILED = ("unhealthy", "circuit_open", "degraded")


def _from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """One catalogue record as a declared observation under its serving service."""
    return {
        "kind": record["kind"],
        "name": record["name"][:_NAME_MAX],
        "status": "declared",
        "parent": {"kind": _SERVICE, "name": record["serving_service"]},
        # default=str: presence and health fields carry datetimes, which the JSON body cannot.
        "attrs": json.loads(json.dumps(record["fields"], default=str)),
    }


def _service_observations(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The distinct serving services of *records*, declared (a probe, when one exists, upgrades them)."""
    names = sorted({r["serving_service"] for r in records})
    return [{"kind": _SERVICE, "name": name, "status": "declared"} for name in names]


def health_observations(snapshot: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Probed services from the health snapshot; a service whose probe has not answered stays declared."""
    out = []
    for name, health in sorted(snapshot.items()):
        status = health.get("status")
        probed = "probed_ok" if status == _HEALTHY else "probed_failed" if status in _PROBED_FAILED else "declared"
        out.append({"kind": _SERVICE, "name": name, "status": probed, "attrs": {"health": health}})
    return out


_last_revision: int | None = None


async def _announce_if_changed(result: Dict[str, Any]) -> None:
    """Publish ``self_model.changed`` when the SLM's revision moved since the last push.

    The revision counts history rows, so it moves for changes other producers made too (a node's inventory).
    The first push only records the baseline: a restart is not a change of the model.
    """
    global _last_revision
    revision = result["revision"]
    moved = _last_revision is not None and revision != _last_revision
    _last_revision = revision
    if moved:
        await publish_event(_EVENT_CHANNEL, SELF_MODEL_CHANGED, {"revision": revision}, persist=PersistStrategy.NONE)


async def push_catalogue(app: FastAPI) -> None:
    """Push the route, tool and agent catalogues (one batch: the services they are served by come with them)."""
    records = [*await route_records(app), *tool_records(), *agent_records()]
    unique = {(r["kind"], r["name"]): r for r in records}  # a tool may be registered in two catalogues
    observations = [*_service_observations(records), *(_from_record(r) for r in unique.values())]
    result = await push_observations(CATALOGUE_SOURCE, ("service", "route", "tool", "agent"), observations)
    logger.info("self-model catalogue pushed: %s", result)
    await _announce_if_changed(result)


async def push_service_health() -> None:
    """Push the latest service-health probe as probed services."""
    result = await push_observations(HEALTH_SOURCE, (_SERVICE,), health_observations(await read_snapshot()))
    logger.info("self-model service health pushed: %s", result)
    await _announce_if_changed(result)


async def _run_forever(app: FastAPI) -> None:
    while True:
        for push in (push_catalogue(app), push_service_health()):
            try:
                await push
            except Exception as exc:  # noqa: BLE001 - one failed push must not end the loop; the next tick retries
                logger.warning("self-model push failed (will retry in %ss): %s", PUSH_INTERVAL_S, exc)
        await asyncio.sleep(PUSH_INTERVAL_S)


def start_self_model_producer(app: FastAPI) -> "asyncio.Task[None]":
    """Start the periodic push; the caller keeps the task on ``app.state`` so shutdown can cancel it."""
    return asyncio.create_task(_run_forever(app), name="self-model-producer")
