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


_EXPLICITLY_DISABLED_UNIT_FILE_STATES = frozenset({"disabled", "masked", "masked-runtime"})


def is_managed_autobot_service(svc_data: dict) -> bool:
    """Is this systemd unit one AutoBot manages and expects running on this node?

    #14465: scope for node-status degrade signals, deliberately NOT
    `extra_data["services"]` / `slm_services_to_monitor`. That operator
    -declared set defaults to `[]` per role, is `[]` on at least one real
    inventory node, and never contains `slm-agent` -- the one unit
    remediation actually restarts -- so a check scoped to it goes dark on
    most of a fleet for the one service that matters most.

    Scoped instead by naming convention (`autobot*`, or `slm-agent` itself)
    plus `unit_file_state` -- the RAW `UnitFileState` string, already
    collected by `health_collector._get_service_details` on every discovered
    unit, no monitored-list dependency required.

    Gated on NOT explicitly disabled, not on `enabled` (review): `UnitFileState
    == "enabled"` alone excludes `static`, `indirect`, `enabled-runtime`,
    `generated` and `alias` -- and `autobot-key-rotation.service.j2` /
    `autobot-pg-backup.service.j2` have no `[Install]` section, so they are
    `static` and would be permanently invisible to this check under an
    `enabled`-only gate. A unit burning its own start limit does NOT get
    disabled by systemd -- `UnitFileState` is untouched by that -- so this
    guard is not accidentally empty for a crash-looping unit either; it was
    just narrower than base's `discovered_services` sweep in the wrong place.

    Absent `unit_file_state` (the field is new; a stale cached snapshot or a
    caller outside `discovered_services` may not carry it) is treated as
    OUT of scope, matching the previous conservative default.
    """
    name = svc_data.get("name", "")
    if not (name.startswith("autobot") or name == "slm-agent"):
        return False
    unit_file_state = svc_data.get("unit_file_state")
    if unit_file_state is None:
        return False
    return unit_file_state not in _EXPLICITLY_DISABLED_UNIT_FILE_STATES
