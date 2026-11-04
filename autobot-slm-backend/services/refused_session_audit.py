# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A refused non-admin session leaves a record, and repeats can't flood the store (#20664).

Maintainer decision: audit these, grouped. One person gets one record per window, and the next record
says how many refusals came since; the grouping is the shared ``RepeatGrouper`` (also the backend's
role denials, #16333). The subject comes from a token whose signature has been checked, so nobody can
make up names to grow this; the tracked set is capped anyway. Like the permission gate's denials, a
record that can't be written is logged and counted by the writer and never changes the 403.
"""

from __future__ import annotations

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.repeat_grouping import RepeatGrouper

logger = get_logger(__name__)

WINDOW_S = env_int_clamped("AUTOBOT_SLM_REFUSED_SESSION_AUDIT_WINDOW_S", 300, 1, 86400)
_PERMISSION = "slm.admin_session"
_PATH = "slm:get_current_user"

_GROUPER = RepeatGrouper(WINDOW_S)


def repeats_to_record(subject: str) -> int | None:
    """Refusals since the last record if this one should be written, else None."""
    return _GROUPER.repeats_to_record(subject)


async def note_refused_session(subject: object) -> None:
    """Record a refusal if this person's window allows it. Never raises: the caller is answering 403."""
    repeats = repeats_to_record(str(subject))
    if repeats is None:
        return
    try:
        from autobot_shared.user_management.middleware.rbac_middleware import _emit_permission_denied_audit
        from user_management.middleware import rbac_middleware  # noqa: F401, PLC0415  # wires the writer

        await _emit_permission_denied_audit(
            None, _PERMISSION, _PATH, subject=f"{subject} (+{repeats} refused since the last record)"
        )
    except Exception as exc:  # noqa: BLE001 - the unwired case too; see the module docstring
        logger.error("Refused-session audit not written (%s)", type(exc).__name__)
