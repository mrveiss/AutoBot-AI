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

#: The entity kinds of the self-model: one list for the SLM's validation and the backend's queries.
ENTITY_KINDS = ("node", "service", "route", "tool", "model", "command", "agent", "package")

#: A node resends its full inventory at least this often, even when the hash did not change.
INVENTORY_RESEND_S = env_int_clamped("AUTOBOT_SELF_MODEL_INVENTORY_RESEND_HOURS", 6, min_v=1, max_v=168) * 3600

#: Heartbeat intervals of silence before a node's probed entities are ``stale``.
STALE_HEARTBEATS = env_int_clamped("AUTOBOT_SELF_MODEL_STALE_HEARTBEATS", 3, min_v=1, max_v=1000)

#: ``STALE_HEARTBEATS`` heartbeats, as a duration.
STALE_AFTER = timedelta(seconds=STALE_HEARTBEATS * DEFAULT_HEARTBEAT_INTERVAL)

#: Seconds between the backend's pushes; it must stay below ``STALE_AFTER`` or its probed entities go stale.
PUSH_INTERVAL_S = env_int_clamped("AUTOBOT_SELF_MODEL_PUSH_INTERVAL_S", 60, min_v=10, max_v=3600)
