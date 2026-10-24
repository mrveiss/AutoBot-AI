# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Node status from heartbeat samples: resource dwell and the DEGRADED reason (#19292).

Split out of ``services/reconciler.py`` (over its file-size ceiling) and kept
free of SQLAlchemy/models imports, so it loads for real under the SLM test
harness's stubs and the reconciler maps the levels here onto ``NodeStatus``.

Two defects this module answers, both observed live in #19292:

1. **The status followed one sample.** Any single heartbeat with cpu, memory
   or disk above the degraded/error threshold changed the node's status at
   once, so a CPU burst flapped online -> error -> degraded -> online every
   20-40 s. The resource level now moves only after
   ``RESOURCE_ENTER_SAMPLES`` consecutive samples worse than it (a sustained
   breach), and back only after ``RESOURCE_EXIT_SAMPLES`` consecutive samples
   better than it (damped recovery). The new level is the least extreme one
   the run saw, so a run alternating 85% and 97% enters DEGRADED, not ERROR.
2. **DEGRADED had one meaning to the remediator and three to the writers.**
   ``_attempt_remediation`` restarted slm-agent on every DEGRADED node, but
   DEGRADED is also written for resource pressure and for service health, and
   a restart lowers neither. The reason now travels with the status, in
   ``Node.extra_data[HEALTH_STATE_KEY]``, and only ``no_heartbeat`` -- the one
   case an agent restart can fix -- selects a node for that remedy.

Service health (#1604, #14465) is the reconciler's ``_service_health_degraded``.
It once degraded on ``n_restarts > 3``, but systemd's ``NRestarts`` only climbs
while a unit keeps failing, so one long-resolved crash loop held the node
DEGRADED forever. It was replaced by two signals over the same field:
``restart_churn_active`` is a LEVEL over the restart-churn window, not a pulse
(health_collector's discovery sweep is cached for 300 s against a 30 s beat, so
a pulse fired on ~1 in 10 beats and flapped the node), and
``status == "failed"`` catches a unit that has settled into systemd's
start-limit end state. Both are scoped by ``is_managed_autobot_service``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from autobot_shared.env_utils import env_int_clamped

REASON_NO_HEARTBEAT = "no_heartbeat"
REASON_RESOURCE_PRESSURE = "resource_pressure"
REASON_SERVICE_HEALTH = "service_health"

# Reserved key on Node.extra_data. Prefixed so a heartbeat's own extra_data,
# merged into the same dict, cannot collide with it.
HEALTH_STATE_KEY = "slm_health_state"

# The agent_version the SLM's own self-heartbeat writes (services/compose_fleet.py);
# how a self-written heartbeat is told apart from a real slm-agent's.
SELF_AGENT_VERSION = "slm-local"

LEVEL_OK = "ok"
LEVEL_DEGRADED = "degraded"
LEVEL_ERROR = "error"
_RANK = {LEVEL_OK: 0, LEVEL_DEGRADED: 1, LEVEL_ERROR: 2}

RESOURCE_DEGRADED_PCT = env_int_clamped("AUTOBOT_NODE_RESOURCE_DEGRADED_PCT", 80, min_v=1, max_v=100)
RESOURCE_ERROR_PCT = env_int_clamped("AUTOBOT_NODE_RESOURCE_ERROR_PCT", 95, min_v=RESOURCE_DEGRADED_PCT, max_v=100)
RESOURCE_ENTER_SAMPLES = env_int_clamped("AUTOBOT_NODE_RESOURCE_ENTER_SAMPLES", 3, min_v=1, max_v=1000)
RESOURCE_EXIT_SAMPLES = env_int_clamped("AUTOBOT_NODE_RESOURCE_EXIT_SAMPLES", 3, min_v=1, max_v=1000)


def classify_resource_sample(cpu_percent: float, memory_percent: float, disk_percent: float) -> str:
    """The resource level ONE heartbeat sample reports, before any dwell."""
    peak = max(cpu_percent, memory_percent, disk_percent)
    if peak > RESOURCE_ERROR_PCT:
        return LEVEL_ERROR
    if peak > RESOURCE_DEGRADED_PCT:
        return LEVEL_DEGRADED
    return LEVEL_OK


def read_health_state(node) -> dict:
    """The node's persisted health state; empty for a node never scored."""
    extra = getattr(node, "extra_data", None) or {}
    state = extra.get(HEALTH_STATE_KEY)
    return dict(state) if isinstance(state, dict) else {}


def _write_health_state(node, state: dict) -> None:
    """Reassign (not mutate) extra_data so a JSON column sees the change."""
    node.extra_data = {**(getattr(node, "extra_data", None) or {}), HEALTH_STATE_KEY: state}


def degraded_reason(node) -> str | None:
    """Why the node is DEGRADED/ERROR, or None when unknown (pre-#19292 row)."""
    return read_health_state(node).get("reason")


def set_degraded_reason(node, reason: str | None) -> None:
    """Record why the node holds its current status (None when ONLINE)."""
    _write_health_state(node, {**read_health_state(node), "reason": reason})


def next_resource_state(state: dict, sample_level: str) -> dict:
    """Advance the dwell state by one sample; returns the new state dict.

    ``resource_level`` is the damped level; ``pending``/``streak`` count the
    current run of samples on one side of it. A sample at the current level,
    or on the other side of it, restarts the run.
    """
    current = state.get("resource_level", LEVEL_OK)
    if _RANK[sample_level] == _RANK[current]:
        return {**state, "resource_level": current, "pending": None, "streak": 0}
    worsening = _RANK[sample_level] > _RANK[current]
    pending = state.get("pending")
    same_side = pending is not None and (_RANK[pending] > _RANK[current]) == worsening
    if same_side:
        pick = min if worsening else max
        pending = pick(pending, sample_level, key=_RANK.__getitem__)
        streak = state.get("streak", 0) + 1
    else:
        pending, streak = sample_level, 1
    needed = RESOURCE_ENTER_SAMPLES if worsening else RESOURCE_EXIT_SAMPLES
    if streak >= needed:
        return {**state, "resource_level": pending, "pending": None, "streak": 0}
    return {**state, "resource_level": current, "pending": pending, "streak": streak}


def advance_resource_dwell(node, sample_level: str) -> str:
    """Apply one sample to the node's persisted dwell state; returns the damped level."""
    state = next_resource_state(read_health_state(node), sample_level)
    _write_health_state(node, state)
    return state["resource_level"]


def status_level_and_reason(resource_level: str, service_degraded: bool) -> tuple[str, str | None]:
    """(level, reason) for a heartbeating node: resource ERROR, then service health, then resource DEGRADED."""
    if resource_level == LEVEL_ERROR:
        return LEVEL_ERROR, REASON_RESOURCE_PRESSURE
    if service_degraded:
        return LEVEL_DEGRADED, REASON_SERVICE_HEALTH
    if resource_level == LEVEL_DEGRADED:
        return LEVEL_DEGRADED, REASON_RESOURCE_PRESSURE
    return LEVEL_OK, None


def as_utc(moment: datetime | None) -> datetime | None:
    """A naive DB timestamp is UTC; an aware one is returned unchanged."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _agent_last_beat(node) -> datetime | None:
    """The last beat a real AGENT sent: the recorded one if the self-heartbeat took over, else the row's."""
    lost = read_health_state(node).get("agent_last_beat")
    if lost:
        return as_utc(datetime.fromisoformat(lost))
    return as_utc(getattr(node, "last_heartbeat", None))


def needs_agent_restart(node, now: datetime, heartbeat_timeout_s: float) -> bool:
    """Whether restarting slm-agent can help this DEGRADED node -- decided on the row as read NOW.

    Only a missing heartbeat can be fixed by a restart, so the stored reason
    must be ``no_heartbeat`` (or absent, on a pre-#19292 row) AND the agent's
    last beat must still be older than the timeout: a beat that landed after
    the reason was written means the agent is alive (#19292 review).
    """
    if degraded_reason(node) not in (None, REASON_NO_HEARTBEAT):
        return False
    last = _agent_last_beat(node)
    return last is None or last < now - timedelta(seconds=heartbeat_timeout_s)


def clear_health_state(node) -> None:
    """Forget dwell and reason, e.g. when the node goes offline: a later return starts clean."""
    _write_health_state(node, {})


def strip_reserved(extra_data: dict | None) -> dict | None:
    """Drop ``HEALTH_STATE_KEY`` from a heartbeat's extra_data, so an agent cannot set its own reason or dwell."""
    if not extra_data or HEALTH_STATE_KEY not in extra_data:
        return extra_data
    return {k: v for k, v in extra_data.items() if k != HEALTH_STATE_KEY}


def mark_agent_lost(node) -> None:
    """Record that the node's real agent stopped beating, as of its last beat (self-managed nodes)."""
    beat = as_utc(getattr(node, "last_heartbeat", None))
    stamp = beat.isoformat() if beat else datetime.now(timezone.utc).isoformat()
    _write_health_state(node, {**read_health_state(node), "agent_last_beat": stamp})


def apply_agent_presence(node, agent_version: str | None, status_reason: tuple, degraded_status) -> tuple:
    """Keep a lost agent visible through self-heartbeats; a real agent's beat clears the mark.

    While ``agent_last_beat`` is set, a ``SELF_AGENT_VERSION`` beat cannot
    report the node healthy: it stays ``(degraded_status, no_heartbeat)``.
    """
    state = read_health_state(node)
    if agent_version and agent_version != SELF_AGENT_VERSION:
        if "agent_last_beat" in state:
            state.pop("agent_last_beat")
            _write_health_state(node, state)
        return status_reason
    if state.get("agent_last_beat"):
        return degraded_status, REASON_NO_HEARTBEAT
    return status_reason
