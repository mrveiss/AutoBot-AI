# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Device-code poll limiter for ``provider_auth`` (#11061), moved verbatim out of ``device_poll``.

Split out (#17576) so ``provider_auth.py`` stays under its recorded size ceiling and ``device_poll`` under
the function-length limit once it gained the egress guard. Behaviour is unchanged: honour RFC-8628
server-side -- reject polls faster than the current interval, back off on ``slow_down``, and cap total
attempts per device_code. Best-effort: skipped when Redis is unavailable.
"""

import hashlib
import json

from fastapi import HTTPException, status

from autobot_shared.env_utils import env_int
from autobot_shared.redis_client import client_get, client_getdel, client_setex

# All overridable via env.
_DEVICE_POLL_MIN_INTERVAL = env_int("AUTOBOT_DEVICE_POLL_MIN_INTERVAL_SECONDS", 5)
_DEVICE_POLL_BACKOFF = env_int("AUTOBOT_DEVICE_POLL_BACKOFF_SECONDS", 5)
_DEVICE_POLL_MAX_ATTEMPTS = env_int("AUTOBOT_DEVICE_POLL_MAX_ATTEMPTS", 360)
_DEVICE_POLL_WINDOW = env_int("AUTOBOT_DEVICE_POLL_WINDOW_SECONDS", 1800)
_DEVICE_POLL_PREFIX = "llm-auth:device:poll:"


def device_poll_key(device_code: str) -> str:
    # Hash the device_code so the raw grant secret never becomes a Redis key.
    return "%s%s" % (_DEVICE_POLL_PREFIX, hashlib.sha256(device_code.encode("utf-8")).hexdigest())


async def load_and_check_poll_state(redis, poll_key: str, now: float) -> dict:
    """Return the persisted poll state, raising 429 when polling too fast or attempts are exhausted."""
    poll_state = {"interval": _DEVICE_POLL_MIN_INTERVAL, "count": 0, "last_ts": 0.0}
    if redis is None:
        return poll_state
    raw = await client_get(redis, poll_key)
    if raw:
        poll_state = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    if poll_state["count"] >= _DEVICE_POLL_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="device-code polling attempts exhausted"
        )
    if now - poll_state["last_ts"] < poll_state["interval"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="polling too fast; honor the device-code interval",
        )
    return poll_state


async def record_poll(redis, poll_key: str, poll_state: dict, now: float, error) -> None:
    """Update the limiter: back off on ``slow_down``, persist a pending grant, clear on a terminal outcome."""
    if redis is None:
        return
    if error == "slow_down":
        poll_state["interval"] += _DEVICE_POLL_BACKOFF
    poll_state["count"] += 1
    poll_state["last_ts"] = now
    if error in ("authorization_pending", "slow_down"):
        await client_setex(redis, poll_key, _DEVICE_POLL_WINDOW, json.dumps(poll_state))
    else:
        await client_getdel(redis, poll_key)
