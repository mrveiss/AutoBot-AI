# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Capability decisions for a paired-device credential (#14964).

The pure predicate lives in ``autobot_shared.auth.device_capabilities``; this
module is the thin database-facing half — it loads the credential's row and
turns the predicate's answer into a decision an enforcement point can log and
act on.

Deliberately uncached. ``services.device_jwt`` caches *device existence* for 60
seconds because that check runs on every request; a capability decision runs
once per handshake, and a stale grant is exactly the thing this issue exists to
prevent. A grant or a revocation therefore takes effect on the next handshake,
with no TTL to wait out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from autobot_shared.auth.device_capabilities import DeviceCapability, missing_capabilities
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Reason codes. Two refusals that close a socket the same way must still be
#: told apart in the log and by a test, so every distinct cause has its own code
#: rather than a shared "denied".
REASON_GRANTED = "granted"
REASON_UNKNOWN_DEVICE = "unknown_device"
REASON_NOT_APPROVED = "not_approved"
REASON_MISSING_CAPABILITY = "missing_capability"
#: The row could not be read at all. Denies like the rest, but is kept apart
#: from "unknown_device": a database that will not answer is not the same
#: operational event as a credential nobody paired, and an operator chasing
#: the wrong one of those loses the outage (mirrors STATE_UNREADABLE in
#: services/device_jwt.py).
REASON_STATE_UNREADABLE = "state_unreadable"


@dataclass(frozen=True)
class DeviceCapabilityDecision:
    """The outcome of asking whether a credential holds a set of capabilities."""

    granted: bool
    reason: str
    #: Capability names the credential did not hold. Empty when granted, and
    #: empty when the refusal was decided before grants were consulted.
    missing: tuple[str, ...] = ()

    def describe(self) -> str:
        """A short, credential-free description for a log line or close reason.

        Never includes the device token, the JWT, or any fragment of either —
        only the reason code and the capability names that were required.
        """
        if self.granted:
            return REASON_GRANTED
        if self.missing:
            return f"{self.reason}:{','.join(self.missing)}"
        return self.reason


async def evaluate_device_capabilities(
    device_id: str,
    required: Iterable[DeviceCapability | str],
) -> DeviceCapabilityDecision:
    """Decide whether the paired device ``device_id`` holds every capability in ``required``.

    Fail-closed at every step: a device row that cannot be found, a credential
    that was never approved, or any capability not positively present in the
    stored grant set all produce a refusal. There is no branch that returns a
    grant without the row having said so.
    """
    device, readable = await _load_device(device_id)
    if not readable:
        return DeviceCapabilityDecision(granted=False, reason=REASON_STATE_UNREADABLE)
    if device is None:
        return DeviceCapabilityDecision(granted=False, reason=REASON_UNKNOWN_DEVICE)

    missing = missing_capabilities(
        required=required,
        permissions_raw=device.permissions,
        is_approved=device.is_approved,
        revoked_at=device.revoked_at,
    )
    if not missing:
        return DeviceCapabilityDecision(granted=True, reason=REASON_GRANTED)
    if device.is_approved is not True:
        return DeviceCapabilityDecision(granted=False, reason=REASON_NOT_APPROVED, missing=missing)
    return DeviceCapabilityDecision(granted=False, reason=REASON_MISSING_CAPABILITY, missing=missing)


async def _load_device(device_id: str) -> "tuple[object | None, bool]":
    """Read the paired-device row as ``(row, readable)``.

    ``readable`` is ``False`` only when the lookup itself failed — a malformed
    id, a database that will not answer, a schema predating migration
    ``20260824_084``. ``(None, True)`` means the read succeeded and there is no
    such device. Both deny; separating them is what lets the refusal say which
    happened instead of reporting an outage as an unknown credential.

    Never raises: keeping the failure on the same path as an ordinary refusal
    means no caller can grant access by forgetting a ``try``.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from models.mobile_device import MobileDevice  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    try:
        async for session in get_async_session():
            result = await session.execute(select(MobileDevice).where(MobileDevice.id == device_id).limit(1))
            return result.scalar_one_or_none(), True
    except Exception:
        # No credential material is in scope here, and none is logged: the
        # message carries the device id and nothing else.
        logger.warning("device_capabilities: lookup failed for device %s — denying", device_id, exc_info=True)
        return None, False
    return None, True
