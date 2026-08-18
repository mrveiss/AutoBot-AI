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


def monitored_autobot_service_failed(extra_data: dict | None) -> bool:
    """Check if any explicitly monitored autobot-* service is failed or crash-looping.

    Shared by `api.nodes._has_failed_autobot_service` (Issue #1605/#1709, code_status)
    and `services.reconciler._calculate_node_status` (#14465, node.status): both need
    the identical, narrower signal this function provides, and neither module may
    import the other (`api.nodes` already imports `services.reconciler`).

    Issue #1709: scope is monitored services only (extra_data["services"]), never
    discovered_services (all systemd units) -- a failed unit outside the operator's
    own `slm_services_to_monitor` (e.g. autobot-vnc on a headless browser node) must
    not be read as this node's monitored service being broken.

    Format: {"service-name": {"active": bool, "status": "<systemctl is-active output>"}}
    Failure statuses: "failed", "crash-loop".
    """
    if not extra_data:
        return False
    monitored = extra_data.get("services", {})
    if not monitored:
        return False
    for name, info in monitored.items():
        if not name.startswith("autobot"):
            continue
        svc_status = info.get("status", "") if isinstance(info, dict) else ""
        if svc_status in ("failed", "crash-loop"):
            return True
    return False
