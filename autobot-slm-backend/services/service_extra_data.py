# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dependency-free helpers for shaping Service.extra_data payloads (#11718).

Kept separate from services/reconciler.py — which pulls in SQLAlchemy,
config, and models.database at import time — so these pure functions stay
real-load testable without needing to stub a heavy module.
"""


def engine_degraded_fields(svc_data: dict) -> dict:
    """Extract engine_degraded/degraded_reason from heartbeat svc_data.

    Populated only when the node agent's service probe reports an app-level
    degraded state (e.g. a TTS worker that fell back to an ungated model
    after HF auth failed) alongside the systemd status. Returns an empty
    dict when the key is absent, so callers merging into extra_data never
    clobber unrelated data for services that only report systemd state.
    """
    if "engine_degraded" not in svc_data:
        return {}
    return {
        "engine_degraded": bool(svc_data.get("engine_degraded")),
        "degraded_reason": svc_data.get("degraded_reason"),
    }


def is_managed_autobot_service(svc_data: dict) -> bool:
    """Is this systemd unit one AutoBot manages and expects running on this node?

    #14465: scope for node-status degrade signals, deliberately NOT
    `extra_data["services"]` / `slm_services_to_monitor`. That operator
    -declared set defaults to `[]` per role, is `[]` on at least one real
    inventory node, and never contains `slm-agent` -- the one unit
    remediation actually restarts -- so a check scoped to it goes dark on
    most of a fleet for the one service that matters most.

    Scoped instead by naming convention (`autobot*`, or `slm-agent` itself)
    plus `enabled` -- systemd's own `UnitFileState`, already collected by
    `health_collector._get_service_details` on every discovered unit, no
    monitored-list dependency required. `enabled` reflects what THIS node's
    deployment actually turned on (e.g. `autobot-vnc` only when `install_vnc`
    is set in the browser role) -- exactly the signal #1709 needed to avoid
    flagging a non-primary autobot unit a node was never meant to run.
    """
    name = svc_data.get("name", "")
    if not (name.startswith("autobot") or name == "slm-agent"):
        return False
    return bool(svc_data.get("enabled", False))
