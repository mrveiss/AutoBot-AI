# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bounds on the two anonymous RUM ingest routes, ``/event`` and ``/metrics`` (#16375).

Those routes are open by design (see ``api/rum.py``): the browser's RumAgent
sends a bare ``fetch``/``sendBeacon`` with no credential, from every page
including ``/login`` and ``/shared/:token``. An open write must not be a free
amplifier, so each request is held to the #17007 treatment:

* **rate-limited** per client address with the shared ``IPRateLimiter``
  (``AUTOBOT_RUM_INGEST_RATE_LIMIT``); over it, 429 and nothing is written;
* **size-capped** while the body streams, before any JSON is parsed
  (``AUTOBOT_RUM_*_MAX_BYTES``, ``api.rum_body_cap``), 413;
* **field-capped**: each identifying event string has a maximum length, and a
  metrics batch caps every list (``AUTOBOT_RUM_METRICS_MAX_ITEMS``) and every
  string (``AUTOBOT_RUM_METRICS_MAX_FIELD_CHARS``), 422;
* **label-bounded**: every metric label value passes the recorder's bounded
  vocabulary (``autobot_shared.monitoring.metrics.label_bounds``, #18368);
* **one bounded row**: an event appends one entry to a capped buffer and
  upserts one entry in a capped session table -- the oldest is evicted, so no
  number of requests grows either past its cap.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List

from fastapi import HTTPException, Request
from pydantic import BaseModel

from autobot_shared.env_registry import REGISTRY, env
from autobot_shared.proxy_utils import get_client_ip
from autobot_shared.rate_limit import IPRateLimiter

_RATE_ENV = "AUTOBOT_RUM_INGEST_RATE_LIMIT"

_ingest_limiter = IPRateLimiter(
    key_prefix="ratelimit:rum_ingest",
    limit_env=_RATE_ENV,
    default_limit=REGISTRY[_RATE_ENV].default,
    window_seconds=60,
)

#: Longest accepted value of each top-level ``RumEvent`` string. The body cap
#: bounds ``data``; these stop the identifying fields carrying the payload.
EVENT_FIELD_CAPS: Dict[str, int] = {
    "type": 64,
    "timestamp": 64,
    "sessionId": 128,
    "url": 2048,
    "userAgent": 512,
}


async def _rate_limit(request: Request) -> None:
    await _ingest_limiter.check_or_429(get_client_ip(request) or "unknown")


async def bound_event_ingest(request: Request) -> None:
    """Route dependency for ``POST /rum/event``: per-address rate limit.

    The body cap runs earlier, while the body streams (``api.rum_body_cap``).
    """
    await _rate_limit(request)


async def bound_metrics_ingest(request: Request) -> None:
    """Route dependency for ``POST /rum/metrics``: per-address rate limit."""
    await _rate_limit(request)


def enforce_event_field_caps(event: Any) -> None:
    """422 when an identifying ``RumEvent`` string is longer than its cap."""
    for name, cap in EVENT_FIELD_CAPS.items():
        if len(getattr(event, name, "") or "") > cap:
            raise HTTPException(
                status_code=422,
                detail=f"RUM event field '{name}' exceeds {cap} characters",
            )


def append_bounded(events: List[dict], event_data: dict) -> None:
    """Append one event, dropping the oldest beyond ``AUTOBOT_RUM_MAX_EVENTS``."""
    events.append(event_data)
    overflow = len(events) - int(env("AUTOBOT_RUM_MAX_EVENTS"))
    if overflow > 0:
        del events[:overflow]


def track_session(sessions: Dict[str, dict], event_data: dict) -> int:
    """Upsert the event's session, evicting the oldest beyond the cap; returns its count."""
    session_id = event_data["sessionId"]
    session = sessions.get(session_id)
    if session is None:
        session = sessions[session_id] = {
            "start_time": event_data["server_timestamp"],
            "event_count": 0,
            "user_agent": event_data["userAgent"],
            "initial_url": event_data["url"],
        }
        while len(sessions) > int(env("AUTOBOT_RUM_MAX_SESSIONS")):
            sessions.pop(next(iter(sessions)))
    session["event_count"] += 1
    session["last_activity"] = event_data["server_timestamp"]
    return session["event_count"]


def _refuse(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _strings(model: BaseModel) -> Iterator[tuple[str, str]]:
    """Every string in *model*, nested models and lists of models included."""
    for name, value in model:
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, str):
                yield name, item
            elif isinstance(item, BaseModel):
                yield from _strings(item)


def enforce_metrics_caps(metrics: BaseModel) -> None:
    """422 when a ``RumMetrics`` list or string is over its cap (#18368)."""
    max_items = int(env("AUTOBOT_RUM_METRICS_MAX_ITEMS"))
    for name, value in metrics:
        if isinstance(value, list) and len(value) > max_items:
            raise _refuse(f"RUM metrics list '{name}' exceeds {max_items} items")
    max_chars = int(env("AUTOBOT_RUM_METRICS_MAX_FIELD_CHARS"))
    for name, text in _strings(metrics):
        if len(text) > max_chars:
            raise _refuse(f"RUM metrics field '{name}' exceeds {max_chars} characters")
