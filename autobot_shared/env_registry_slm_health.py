# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SLM node-health AUTOBOT_* environment variable registrations (#19292).

A sibling of ``env_registry_slm.py``, imported from its end: that module has
too little room under the 600-line limit for these five, and
``env_registry.py`` sits at its grandfathered ceiling, so it cannot take
another sibling import line either.

Registration contract (import side effect, ordering): see ``env_registry``.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var


def _register(name: str, default: int, description: str, range_: tuple) -> None:
    register_env_var(
        EnvVarSpec(name=name, type=int, default=default, description=description, component="slm", range=range_)
    )


_register(
    "AUTOBOT_NODE_RESOURCE_DEGRADED_PCT",
    80,
    "CPU, memory or disk percent above which a heartbeat sample counts as resource "
    "pressure (node DEGRADED, reason resource_pressure) once the dwell below is met "
    "(autobot-slm-backend/services/node_health_status.py, #19292).",
    (1, 100),
)

_register(
    "AUTOBOT_NODE_RESOURCE_ERROR_PCT",
    95,
    "CPU, memory or disk percent above which a heartbeat sample counts toward node "
    "ERROR once the dwell below is met. Clamped to at least the degraded level "
    "(autobot-slm-backend/services/node_health_status.py, #19292).",
    (1, 100),
)

_register(
    "AUTOBOT_NODE_RESOURCE_ENTER_SAMPLES",
    3,
    "Consecutive heartbeat samples worse than a node's current resource level before "
    "its status worsens. 1 restores the old follow-one-sample behaviour that let a "
    "single CPU burst flap the node (autobot-slm-backend/services/node_health_status.py, #19292).",
    (1, 1000),
)

_register(
    "AUTOBOT_NODE_RESOURCE_EXIT_SAMPLES",
    3,
    "Consecutive heartbeat samples better than a node's current resource level before "
    "its status recovers, so recovery is damped too "
    "(autobot-slm-backend/services/node_health_status.py, #19292).",
    (1, 1000),
)

_register(
    "AUTOBOT_SELF_HEARTBEAT_STANDDOWN_BEATS",
    2,
    "The agent's own heartbeat intervals (as it reports them, else the fleet's) that a real "
    "slm-agent's last beat on a self-managed node (the SLM "
    "manager) keeps the SLM's local self-heartbeat stood down, so the node has one "
    "heartbeat source. 2 tolerates one missed agent beat; the local loop resumes after "
    "that (autobot-slm-backend/services/compose_fleet.py, #19292).",
    (1, 1000),
)

_register(
    "AUTOBOT_SELF_HEARTBEAT_AGENT_INTERVAL_MAX_S",
    3600,
    "Largest heartbeat interval, in seconds, the SLM accepts from a real slm-agent's own "
    "report when sizing the self-heartbeat stand-down window; a larger, zero or non-integer "
    "report falls back to the fleet's interval, so a misreporting agent cannot freeze the "
    "manager node's status (autobot-slm-backend/services/compose_fleet.py, #19292).",
    (1, 86400),
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_KEY_PROBE_TIMEOUT_SECONDS",
        type=float,
        default=10.0,
        description=(
            "Wall-clock ceiling on the SSH key-access probe that runs before a stored SSH password's deletion is "
            "proposed (inline in enrollment) and again before it is deleted (#20046). The probe is killed at the "
            "ceiling and counts as failed, so a hung node delays enrollment by at most this long and the proposal "
            "waits for a later enrollment."
        ),
        component="slm",
        range=(2.0, 60.0),
    )
)
