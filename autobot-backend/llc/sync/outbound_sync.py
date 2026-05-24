# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC outbound project management sync service (GH#8257).

Subscribes to ``llc:work_item:*`` Redis pub/sub events and pushes state changes
to external PM systems (Jira, Trello, Asana) via the existing connector layer.

Design:
- Non-fatal: sync failures are logged to llc_activity_log and never block the
  work item transition that triggered them.
- Async: dispatch is fire-and-forget from the caller's perspective.
- Credential storage: the encrypted JSON blob in ``organizations.external_pm_config``
  is decrypted here; plaintext credentials never hit the DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any, Dict, Optional

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)

# Redis pub/sub channel pattern for LLC work item events
_LLC_WORK_ITEM_CHANNEL = "llc:work_item:*"

# ──────────────────────────────────────────────────────────────────────────────
# Leader election (multi-worker duplicate-dispatch prevention, GH#8257 CR fix)
# ──────────────────────────────────────────────────────────────────────────────

_LEADER_KEY = "llc:outbound_sync:leader"
_LEADER_TTL_MS = 30_000  # 30-second lease
_LEADER_REFRESH_S = 10  # leader refreshes its lease every 10 s
_LEADER_POLL_S = 15  # non-leaders poll every 15 s

# Atomic compare-and-expire: refresh TTL only if the key still holds our
# worker_id.  A plain GET→PEXPIRE pair is non-atomic and risks dual-leader
# under GC pause or network delay.
_REFRESH_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
"""

# ──────────────────────────────────────────────────────────────────────────────
# Field mapping: LLC → external PM
# ──────────────────────────────────────────────────────────────────────────────

_WORK_ITEM_TYPE_TO_JIRA: Dict[str, str] = {
    "epic": "Epic",
    "feature": "Story",
    "pbi": "Story",
    "task": "Task",
    "bug": "Bug",
    "subtask": "Sub-task",
    "spike": "Task",
    "risk": "Task",
}

_WORK_ITEM_TYPE_TO_TRELLO: Dict[str, str] = {
    # Trello is flat — all map to "card"
    "epic": "card",
    "feature": "card",
    "pbi": "card",
    "task": "card",
    "bug": "card",
    "subtask": "card",
    "spike": "card",
    "risk": "card",
}

_WORK_ITEM_TYPE_TO_ASANA: Dict[str, str] = {
    "epic": "task",
    "feature": "task",
    "pbi": "task",
    "task": "task",
    "bug": "task",
    "subtask": "task",
    "spike": "task",
    "risk": "task",
}

_WORK_ITEM_TYPE_TO_AZURE: Dict[str, str] = {
    "epic": "Epic",
    "feature": "Feature",
    "pbi": "Product Backlog Item",
    "task": "Task",
    "bug": "Bug",
    "subtask": "Task",
    "spike": "Task",
    "risk": "Impediment",
}

# Default LLC status → Jira transition name mapping (configurable per company
# via external_pm_config["status_map"])
_DEFAULT_STATUS_MAP: Dict[str, str] = {
    "backlog": "Backlog",
    "ready": "Selected for Development",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
    "cancelled": "Done",
    "blocked": "Blocked",
}


def map_work_item_type(pm_type: str, llc_type: str) -> str:
    """Return the external PM item type for a given LLC work item type."""
    mapping = {
        "jira": _WORK_ITEM_TYPE_TO_JIRA,
        "trello": _WORK_ITEM_TYPE_TO_TRELLO,
        "asana": _WORK_ITEM_TYPE_TO_ASANA,
        "azure_devops": _WORK_ITEM_TYPE_TO_AZURE,
    }.get(pm_type, {})
    return mapping.get(llc_type, "Task")


def map_status(pm_config: Dict[str, Any], llc_status: str) -> str:
    """Return the external workflow state for a given LLC status.

    Checks ``pm_config["status_map"]`` first; falls back to the default map.
    """
    custom_map: Dict[str, str] = pm_config.get("status_map", {})
    return custom_map.get(llc_status) or _DEFAULT_STATUS_MAP.get(llc_status, llc_status)


# ──────────────────────────────────────────────────────────────────────────────
# Credential decryption
# ──────────────────────────────────────────────────────────────────────────────


def _decrypt_pm_config(encrypted_blob: str) -> Dict[str, Any]:
    """Decrypt the AES-256 encrypted PM config blob.

    Uses ``AUTOBOT_FIELD_ENCRYPTION_KEY`` from the environment (same key used
    by the secrets module).  Returns the decoded JSON dict.
    """
    from autobot_shared.field_encryption import decrypt_field

    plaintext = decrypt_field(encrypted_blob)
    return json.loads(plaintext)


# ──────────────────────────────────────────────────────────────────────────────
# Connector dispatch
# ──────────────────────────────────────────────────────────────────────────────


async def _resolve_jira_transition_id(
    integration: Any, issue_key: str, transition_name: str
) -> Optional[str]:
    """Fetch available transitions and map a human-readable name to its numeric ID.

    Jira's POST /transitions endpoint requires a numeric ID (e.g. "31"), not
    a display name.  Returns None when no matching transition is found.
    """
    result = await integration.execute_action("list_transitions", {"issue_key": issue_key})
    for t in result.get("transitions", []):
        if t.get("name", "").lower() == transition_name.lower():
            return str(t["id"])
    return None


async def _dispatch_to_jira(pm_config: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
    from integrations.base import IntegrationConfig
    from integrations.project_management_integration import JiraIntegration

    cfg = IntegrationConfig(
        name="jira",
        provider="jira",
        base_url=pm_config["base_url"],
        username=pm_config["username"],
        api_key=pm_config["api_key"],
    )
    integration = JiraIntegration(cfg)
    project_key = pm_config.get("project_key", "")

    if event == "created":
        issue_type = map_work_item_type("jira", payload.get("type", "task"))
        await integration.execute_action(
            "create_issue",
            {
                "project_key": project_key,
                "summary": payload.get("title", ""),
                "description": payload.get("description", ""),
                "issue_type": issue_type,
            },
        )
    elif event == "transitioned" or event == "completed":
        issue_key = payload.get("external_id")
        if issue_key:
            transition_name = map_status(pm_config, payload.get("status", ""))
            transition_id = await _resolve_jira_transition_id(integration, issue_key, transition_name)
            if transition_id is None:
                raise ValueError(
                    f"No Jira transition found matching '{transition_name}' on {issue_key}"
                )
            await integration.execute_action(
                "update_issue_status",
                {"issue_key": issue_key, "transition_id": transition_id},
            )


async def _dispatch_to_trello(pm_config: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
    from integrations.base import IntegrationConfig
    from integrations.project_management_integration import TrelloIntegration

    cfg = IntegrationConfig(
        name="trello",
        provider="trello",
        api_key=pm_config["api_key"],
        token=pm_config["token"],
    )
    integration = TrelloIntegration(cfg)
    list_id = pm_config.get("list_id", "")

    if event == "created":
        await integration.execute_action(
            "create_card",
            {
                "list_id": list_id,
                "name": payload.get("title", ""),
                "description": payload.get("description", ""),
            },
        )
    elif event in ("transitioned", "completed"):
        card_id = payload.get("external_id")
        done_list_id = pm_config.get("done_list_id", list_id)
        if card_id:
            await integration.execute_action(
                "move_card",
                {"card_id": card_id, "list_id": done_list_id},
            )


async def _dispatch_to_asana(pm_config: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
    from integrations.base import IntegrationConfig
    from integrations.project_management_integration import AsanaIntegration

    cfg = IntegrationConfig(name="asana", provider="asana", token=pm_config["token"])
    integration = AsanaIntegration(cfg)
    workspace_gid = pm_config.get("workspace_gid", "")
    project_gid = pm_config.get("project_gid")

    if event == "created":
        params: Dict[str, Any] = {
            "workspace_gid": workspace_gid,
            "name": payload.get("title", ""),
            "notes": payload.get("description", ""),
        }
        if project_gid:
            params["project_gid"] = project_gid
        await integration.execute_action("create_task", params)
    elif event == "completed":
        task_gid = payload.get("external_id")
        if task_gid:
            await integration.execute_action(
                "update_task",
                {"task_gid": task_gid, "completed": True},
            )


_DISPATCHER = {
    "jira": _dispatch_to_jira,
    "trello": _dispatch_to_trello,
    "asana": _dispatch_to_asana,
}


# ──────────────────────────────────────────────────────────────────────────────
# Activity log helper
# ──────────────────────────────────────────────────────────────────────────────


async def _log_sync_failed(
    company_id: str,
    work_item_id: str,
    event: str,
    error: str,
) -> None:
    """Append a sync_failed entry to the LLC activity log via Redis."""
    redis = await get_async_redis_client()
    if redis is None:
        return
    entry = json.dumps(
        {
            "event_type": "sync_failed",
            "company_id": company_id,
            "work_item_id": work_item_id,
            "sync_event": event,
            "error": error,
        },
        ensure_ascii=False,
    )
    await redis.lpush("llc:activity_log", entry)


# ──────────────────────────────────────────────────────────────────────────────
# Main service
# ──────────────────────────────────────────────────────────────────────────────


class LLCOutboundSyncService:
    """Subscribes to ``llc:work_item:*`` and pushes events to external PM systems.

    Instantiate once (e.g. in the FastAPI lifespan) and call ``start()``.
    The background task loops until ``stop()`` is called.

    Multi-worker safety: a Redis SETNX leader lock ensures only one uvicorn
    worker processes messages at a time, preventing duplicate PM dispatches.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._leader_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._stop_event = asyncio.Event()
        self._is_leader = False
        self._worker_id = "%s-%d" % (socket.gethostname(), os.getpid())

    async def start(self) -> None:
        """Start the background subscriber task and leader election loop."""
        self._stop_event.clear()
        self._leader_task = asyncio.create_task(
            self._leader_loop(), name="llc-outbound-sync-leader"
        )
        self._task = asyncio.create_task(self._run(), name="llc-outbound-sync")
        logger.info("LLCOutboundSyncService started (worker=%s)", self._worker_id)

    async def stop(self) -> None:
        """Signal the subscriber to exit and await task completion."""
        self._stop_event.set()
        for t in (self._task, self._leader_task):
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        logger.info("LLCOutboundSyncService stopped")

    async def _leader_loop(self) -> None:
        """Continuously attempt to hold or acquire the Redis leader lock."""
        while not self._stop_event.is_set():
            try:
                won = await self._try_acquire_or_refresh()

                if won and not self._is_leader:
                    logger.info("LLCOutboundSyncService: became leader (%s)", self._worker_id)
                    self._is_leader = True
                elif not won and self._is_leader:
                    logger.warning(
                        "LLCOutboundSyncService: lost leadership (%s)", self._worker_id
                    )
                    self._is_leader = False

                sleep_s = _LEADER_REFRESH_S if self._is_leader else _LEADER_POLL_S
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._stop_event.wait()), timeout=sleep_s
                    )
                    return  # stop_event fired — exit gracefully
                except asyncio.TimeoutError:
                    pass  # normal: sleep interval elapsed, loop again
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("LLCOutboundSyncService leader loop error: %s", exc)
                await asyncio.sleep(_LEADER_POLL_S)

    async def _try_acquire_or_refresh(self) -> bool:
        """Acquire leader lock via SETNX (new) or atomic Lua refresh (existing)."""
        redis = await get_async_redis_client()
        if redis is None:
            return False
        try:
            if self._is_leader:
                # Atomic refresh via server-side Lua — prevents dual-leader from
                # a non-atomic GET+PEXPIRE pair splitting under GC pause.
                result = await redis.eval(  # noqa: S603  (Redis server-side Lua, not Python eval)
                    _REFRESH_LUA, 1, _LEADER_KEY, self._worker_id, str(_LEADER_TTL_MS)
                )
                return bool(result)
            else:
                result = await redis.set(_LEADER_KEY, self._worker_id, nx=True, px=_LEADER_TTL_MS)
                return result is not None
        except Exception as exc:
            logger.warning("LLCOutboundSyncService leader election error: %s", exc)
            return False

    async def _run(self) -> None:
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("LLCOutboundSyncService: Redis unavailable — not starting")
            return

        pubsub = redis.pubsub()
        await pubsub.psubscribe(_LLC_WORK_ITEM_CHANNEL)
        logger.info("Subscribed to %s", _LLC_WORK_ITEM_CHANNEL)

        try:
            while not self._stop_event.is_set():
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                asyncio.create_task(self._handle_message(message))
        finally:
            await pubsub.punsubscribe(_LLC_WORK_ITEM_CHANNEL)
            await pubsub.close()

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        if not self._is_leader:
            return  # non-leaders skip dispatch; leader handles for all workers
        channel: str = (message.get("channel") or b"").decode("utf-8", errors="replace")
        # channel format: llc:work_item:<event>
        parts = channel.split(":")
        event = parts[2] if len(parts) >= 3 else "unknown"

        try:
            data = json.loads(message.get("data") or b"{}")
        except (json.JSONDecodeError, TypeError):
            logger.warning("LLCOutboundSyncService: malformed message on %s", channel)
            return

        company_id: str = data.get("company_id", "")
        work_item_id: str = data.get("work_item_id", "")

        if not company_id:
            return

        await self._sync(company_id, work_item_id, event, data)

    async def _sync(
        self,
        company_id: str,
        work_item_id: str,
        event: str,
        payload: Dict[str, Any],
    ) -> None:
        """Look up company PM config and dispatch to the right connector."""
        from sqlalchemy import select

        from user_management.database import AsyncSessionLocal
        from user_management.models.organization import Organization

        try:
            async with AsyncSessionLocal() as session:
                row = await session.execute(
                    select(Organization.external_pm_type, Organization.external_pm_config).where(
                        Organization.id == uuid.UUID(company_id)
                    )
                )
                result = row.one_or_none()

            if result is None:
                return

            pm_type, encrypted_config = result
            if not pm_type or pm_type == "none" or not encrypted_config:
                return

            pm_config = _decrypt_pm_config(encrypted_config)
            dispatcher = _DISPATCHER.get(pm_type)
            if dispatcher is None:
                logger.warning("LLCOutboundSyncService: unsupported pm_type=%s", pm_type)
                return

            await dispatcher(pm_config, event, payload)
            logger.debug(
                "LLC outbound sync: company=%s event=%s pm=%s ok",
                company_id,
                event,
                pm_type,
            )

        except Exception as exc:
            logger.exception(
                "LLC outbound sync failed: company=%s event=%s",
                company_id,
                event,
            )
            await _log_sync_failed(company_id, work_item_id, event, str(exc))


# Module-level singleton
_service: Optional[LLCOutboundSyncService] = None


def get_outbound_sync_service() -> LLCOutboundSyncService:
    global _service
    if _service is None:
        _service = LLCOutboundSyncService()
    return _service
