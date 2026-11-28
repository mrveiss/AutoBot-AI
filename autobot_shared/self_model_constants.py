# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Timing constants of the self-model, shared by the node agent, the SLM and the backend (#22277).

Registered in ``env_registry_self_model``; read through ``env_utils`` so a malformed value falls back
to the default with a warning instead of failing the import.
"""

from __future__ import annotations

from datetime import timedelta

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.fleet_constants import DEFAULT_HEARTBEAT_INTERVAL
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: The entity kinds of the self-model: one list for the SLM's validation and the backend's queries.
ENTITY_KINDS = ("node", "service", "route", "tool", "model", "command", "agent", "package")

#: The sources a producer may claim entities under: the backend's two pushes. The SLM refuses any other.
CATALOGUE_SOURCE = "backend_catalogue"
HEALTH_SOURCE = "backend_service_health"
PRODUCER_SOURCES = (CATALOGUE_SOURCE, HEALTH_SOURCE)

#: A node rescans its package and command lists at least this often, even when the mtime signature did not
#: change: a mode change (exec permission) moves ctime, never the directory's mtime.
INVENTORY_RESCAN_S = env_int_clamped("AUTOBOT_SELF_MODEL_INVENTORY_RESCAN_MINUTES", 30, min_v=1, max_v=1440) * 60

#: A node resends its full inventory at least this often, even when the hash did not change.
INVENTORY_RESEND_S = env_int_clamped("AUTOBOT_SELF_MODEL_INVENTORY_RESEND_HOURS", 6, min_v=1, max_v=168) * 3600

#: Heartbeat intervals of silence before a node's probed entities are ``stale``.
STALE_HEARTBEATS = env_int_clamped("AUTOBOT_SELF_MODEL_STALE_HEARTBEATS", 3, min_v=1, max_v=1000)

#: ``STALE_HEARTBEATS`` heartbeats, as a duration.
STALE_AFTER = timedelta(seconds=STALE_HEARTBEATS * DEFAULT_HEARTBEAT_INTERVAL)

#: Seconds between the backend's pushes; it must stay within half of ``STALE_AFTER`` or its probed entities go stale.
_PUSH_INTERVAL_REQUESTED_S = env_int_clamped("AUTOBOT_SELF_MODEL_PUSH_INTERVAL_S", 60, min_v=10, max_v=3600)


def coherent_push_interval(push_s: int, stale_s: float) -> int:
    """*push_s* when it is at most half of *stale_s*, else half the stale window, with a warning naming both settings.

    Half is the margin: a push that merely beats the window by a second is lost to one slow cycle.
    The two settings are clamped one by one, so only the pair can say that the backend's pushes would arrive
    after its probed entities went ``stale``.
    """
    if push_s <= stale_s / 2:
        return push_s
    corrected = max(1, int(stale_s // 2))
    logger.warning(
        "AUTOBOT_SELF_MODEL_PUSH_INTERVAL_S=%d is not within half of the stale window of %d s "
        "(AUTOBOT_SELF_MODEL_STALE_HEARTBEATS=%d x %d s); using %d s",
        push_s,
        int(stale_s),
        STALE_HEARTBEATS,
        DEFAULT_HEARTBEAT_INTERVAL,
        corrected,
    )
    return corrected


PUSH_INTERVAL_S = coherent_push_interval(_PUSH_INTERVAL_REQUESTED_S, STALE_AFTER.total_seconds())
