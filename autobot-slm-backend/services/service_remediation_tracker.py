# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A (node, service)'s remediation tracker, persisted on the row itself (#16712).

Was `ReconcilerService._service_remediation_tracker`, process memory every
SLM backend restart silently reset -- and every update-all deploy restarts
the backend in its first play, so a permanently-failing service got three
fresh attempts after every single deploy, forever. `Service.extra_data` is
already read and written every heartbeat, so the tracker rides along with it
instead of a second, unreliable store.
"""

from __future__ import annotations

from autobot_shared.time_utils import parse_utc_iso
from models.database import Service


def read_service_remediation(service: Service) -> dict:
    """The tracker, read from the row. Absent means never attempted."""
    raw = (service.extra_data or {}).get("remediation") or {}
    last_attempt_raw = raw.get("last_attempt")
    return {
        "count": raw.get("count", 0),
        "last_attempt": parse_utc_iso(last_attempt_raw) if last_attempt_raw else None,
        "exhausted": bool(raw.get("exhausted", False)),
    }


def write_service_remediation(service: Service, tracker: dict) -> None:
    """Persist *tracker* onto the row.

    A genuine COPY of ``extra_data``, not the same dict mutated in place and
    handed back -- SQLAlchemy's JSON column does not reliably flag that as
    dirty (same gotcha as ``reconciler.py``'s ``_update_existing_service``).
    """
    last_attempt = tracker.get("last_attempt")
    existing_extra = dict(service.extra_data or {})
    existing_extra["remediation"] = {
        "count": tracker["count"],
        "last_attempt": last_attempt.isoformat() if last_attempt else None,
        "exhausted": bool(tracker.get("exhausted", False)),
    }
    service.extra_data = existing_extra


def clear_service_remediation(service: Service) -> bool:
    """Drop the row's tracker entirely. Returns False (a no-op) when there was none."""
    if not (service.extra_data or {}).get("remediation"):
        return False
    existing_extra = dict(service.extra_data or {})
    existing_extra.pop("remediation", None)
    service.extra_data = existing_extra
    return True
