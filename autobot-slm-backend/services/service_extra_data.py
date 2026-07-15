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
