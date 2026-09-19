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

import logging

from autobot_shared.time_utils import parse_utc_iso
from models.database import Service

# Plain stdlib logging, deliberately (matches CLAUDE.md's pattern table and
# autobot_shared/user_management/password_epoch.py's own rationale). This
# module is real-loaded at conftest collection time by autobot-slm-backend's
# own `_REAL_SERVICE_MODULES` -- `autobot_shared.logging_manager.get_logger`
# builds a RotatingFileHandler from config at call time and raises under
# that harness (the config stack is itself mocked that early).
logger = logging.getLogger(__name__)

_ZERO_TRACKER = {"count": 0, "last_attempt": None, "exhausted": False, "last_cause": None}


def read_service_remediation(service: Service) -> dict:
    """The tracker, read from the row. Absent means never attempted.

    A malformed stored value (#17096 review: anything not a dict -- a stray
    string or list some other writer left behind) resets to never-attempted
    and is logged, rather than raising ``AttributeError`` out of ``.get()``
    into the caller. One bad row must not be indistinguishable from a crash.

    ``last_cause`` (#17096 review, #16712 AC: exhaustion must name "the node,
    the service AND the captured cause") is the last restart attempt's own
    failure reason -- ``None`` when the last attempt succeeded, or when there
    has not been one yet.
    """
    raw = (service.extra_data or {}).get("remediation") or {}
    if not isinstance(raw, dict):
        logger.warning(
            "service_remediation_tracker: %s has a malformed remediation value (%r), resetting to zero",
            getattr(service, "service_name", "<unknown>"),
            raw,
        )
        return dict(_ZERO_TRACKER)
    last_attempt_raw = raw.get("last_attempt")
    return {
        "count": raw.get("count", 0),
        "last_attempt": parse_utc_iso(last_attempt_raw) if last_attempt_raw else None,
        "exhausted": bool(raw.get("exhausted", False)),
        "last_cause": raw.get("last_cause"),
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
        "last_cause": tracker.get("last_cause"),
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


def log_restart_result(service_name: str, hostname: str, timeout_s: int, result: dict) -> tuple[bool, str | None]:
    """Log and interpret one execute_playbook result. Helper for
    ``reconciler.py``'s ``_restart_service_via_ansible`` -- extracted here (not
    the ratchet-grandfathered ``reconciler.py``) purely for line-count room.

    A timeout must read as a failure, never a silent success (#14524) --
    ``result["success"]`` already reflects that (execute_playbook's
    ``returncode == 0`` check), this only chooses which message to log.
    ``result.get("output", ...)``, not ``.get("error", ...)``: execute_playbook
    never returns an "error" key, only "output".

    Returns ``(success, cause)``, ``cause`` ``None`` on success -- the last
    attempt's own failure reason otherwise (#16712 AC: an exhaustion event
    must name it, not only the node and service).
    """
    if result.get("success"):
        logger.info("Successfully restarted %s on %s", service_name, hostname)
        return True, None
    if result.get("timed_out"):
        cause = str(result.get("output") or f"timed out after {timeout_s}s")
        logger.warning("Restart of %s on %s timed out after %ds -- killed (#14524)", service_name, hostname, timeout_s)
        return False, cause
    cause = str(result.get("output", "Unknown error"))
    logger.warning("Failed to restart %s on %s: %s", service_name, hostname, cause)
    return False, cause
