# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Desktop control-lock: per-session agent<->human input arbitration.

Issue #12002 (#11506 T1): x11vnc attaches to the SAME canonical display the
agent drives via xdotool (see gui_controller.CANONICAL_DISPLAY and
api.vnc_manager.start_vnc_server). Without arbitration, a human taking over
the noVNC session and the agent both feed the same X input queue at once.

This module is the single source of truth for "who currently owns desktop
input". State is stored in Redis (not an in-process dict) so the lock is
shared across every backend worker/process, keyed by session_id — the same
per-session convention used by the other vnc_manager.py session endpoints
(e.g. ``session_id: str = "default"`` on /connection/settings).

Architecture note: human input reaches the desktop over the raw VNC/RFB
WebSocket proxy (api.vnc_proxy.websocket_proxy), which forwards binary
protocol frames straight to the VNC server -- it never calls into
api.vnc_manager's xdotool endpoints. Gating therefore only needs to happen
on the AGENT's actuation entrypoints (api.vnc_manager, api.vnc_mcp); human
input is never routed through those functions and is never gated.

Auto-detection of "human is actively sending RFB frames" would require
parsing the binary VNC protocol inside the WebSocket proxy hot path -- out
of scope here (see PR description). Control is therefore explicit
(acquire/release, e.g. a "Take control" / "Release" UI toggle) backed by an
idle-TTL: the lock auto-expires if it is never refreshed, so a human who
navigates away or closes the tab does not permanently mute the agent.
"""

import json
import os
from datetime import datetime, timezone

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client

logger = get_logger(__name__)

# Default/canonical session id, matching the convention already used by
# api.vnc_manager.py's other session_id-keyed endpoints (e.g.
# get_connection_settings / update_connection_settings default to "default").
DEFAULT_DESKTOP_SESSION_ID = "default"

# Env-driven idle-TTL (seconds): if the lock is not refreshed (re-acquired)
# within this window, it auto-expires and the agent resumes. Never hardcode
# -- override via AUTOBOT_DESKTOP_CONTROL_LOCK_TTL_SECONDS.
DESKTOP_CONTROL_LOCK_TTL_SECONDS: int = int(os.environ.get("AUTOBOT_DESKTOP_CONTROL_LOCK_TTL_SECONDS", "120"))

_LOCK_KEY_PREFIX = "autobot:desktop:control_lock:"


def _lock_key(session_id: str) -> str:
    """Build the Redis key for a session's control lock."""
    return f"{_LOCK_KEY_PREFIX}{session_id}"


async def _get_lock_record(session_id: str) -> tuple[dict | None, bool]:
    """Read the raw lock record for a session.

    Returns:
        (record, redis_ok). ``record`` is None when no lock is held (or on
        error). ``redis_ok`` is False when Redis itself could not be reached
        (as opposed to "reached but no lock present").
    """
    key = _lock_key(session_id)
    try:
        redis = await get_redis_client(async_client=True, database="main")
        if redis is None:
            return None, False
        raw = await redis.get(key)
        if raw is None:
            return None, True
        return json.loads(raw), True
    except Exception as e:
        logger.error("desktop_control_lock: Redis error reading %s: %s", key, e)
        return None, False


async def acquire_human_control(session_id: str, owner: str) -> dict:
    """Acquire (or refresh) the human control lock for a session.

    Always overwrites any existing lock -- takeover is intentionally
    permissive (the last human to click "Take control" wins); this mirrors
    a single shared desktop with one human-observable session.

    Returns:
        {"success", "owner", "human_active", "message", "ttl_seconds"}
    """
    key = _lock_key(session_id)
    record = {
        "owner": owner,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        redis = await get_redis_client(async_client=True, database="main")
        if redis is None:
            logger.error("desktop_control_lock: Redis unavailable, cannot acquire lock for %s", session_id)
            return {
                "success": False,
                "owner": owner,
                "human_active": False,
                "message": "Redis unavailable; control lock could not be acquired",
                "ttl_seconds": DESKTOP_CONTROL_LOCK_TTL_SECONDS,
            }
        await redis.set(key, json.dumps(record, ensure_ascii=False), ex=DESKTOP_CONTROL_LOCK_TTL_SECONDS)
        logger.info(
            "desktop_control_lock: acquired session=%s owner=%s ttl=%ss",
            session_id,
            owner,
            DESKTOP_CONTROL_LOCK_TTL_SECONDS,
        )
        return {
            "success": True,
            "owner": owner,
            "human_active": True,
            "message": f"Control acquired by {owner}",
            "ttl_seconds": DESKTOP_CONTROL_LOCK_TTL_SECONDS,
        }
    except Exception as e:
        logger.error("desktop_control_lock: Redis error acquiring %s: %s", key, e)
        return {
            "success": False,
            "owner": owner,
            "human_active": False,
            "message": "Internal server error acquiring control lock",
            "ttl_seconds": DESKTOP_CONTROL_LOCK_TTL_SECONDS,
        }


async def release_human_control(session_id: str, owner: str) -> dict:
    """Release the human control lock for a session.

    Only the current owner may release the lock (compare-and-delete), so one
    human cannot accidentally hand control back to the agent on another
    human's behalf.

    Returns:
        {"success", "owner", "human_active", "message"}
    """
    key = _lock_key(session_id)
    try:
        redis = await get_redis_client(async_client=True, database="main")
        if redis is None:
            logger.error("desktop_control_lock: Redis unavailable, cannot release lock for %s", session_id)
            return {
                "success": False,
                "owner": None,
                "human_active": True,
                "message": "Redis unavailable; control lock could not be released",
            }
        raw = await redis.get(key)
        if raw is None:
            return {
                "success": True,
                "owner": None,
                "human_active": False,
                "message": "No active control lock to release",
            }
        record = json.loads(raw)
        if record.get("owner") != owner:
            logger.warning(
                "desktop_control_lock: release denied session=%s requester=%s owner=%s",
                session_id,
                owner,
                record.get("owner"),
            )
            return {
                "success": False,
                "owner": record.get("owner"),
                "human_active": True,
                "message": "Control lock is held by another user",
            }
        await redis.delete(key)
        logger.info("desktop_control_lock: released session=%s owner=%s", session_id, owner)
        return {
            "success": True,
            "owner": None,
            "human_active": False,
            "message": "Control released",
        }
    except Exception as e:
        logger.error("desktop_control_lock: Redis error releasing %s: %s", key, e)
        return {
            "success": False,
            "owner": None,
            "human_active": True,
            "message": "Internal server error releasing control lock",
        }


async def is_human_active(session_id: str) -> bool:
    """Return True when a human currently holds the control lock.

    Fails SAFE: if Redis cannot be reached, this returns True (mute the
    agent) rather than False -- an availability blip on the state store
    must never let the agent silently regain input control while the
    control-lock state is unknown.
    """
    record, redis_ok = await _get_lock_record(session_id)
    if not redis_ok:
        logger.error(
            "desktop_control_lock: Redis unavailable for session %s, failing safe (muting agent actuation)",
            session_id,
        )
        return True
    return record is not None


async def get_lock_owner(session_id: str) -> str | None:
    """Return the current lock owner for a session, or None if unheld."""
    record, _ = await _get_lock_record(session_id)
    return record.get("owner") if record else None


async def get_control_lock_state(session_id: str) -> dict:
    """Return the full control-lock state for a session (status/MCP use).

    Returns:
        {"session_id", "human_active", "owner", "acquired_at", "redis_available"}
    """
    record, redis_ok = await _get_lock_record(session_id)
    human_active = (not redis_ok) or (record is not None)
    return {
        "session_id": session_id,
        "human_active": human_active,
        "owner": record.get("owner") if record else None,
        "acquired_at": record.get("acquired_at") if record else None,
        "redis_available": redis_ok,
    }
