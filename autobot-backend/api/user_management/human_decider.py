# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Refuse approval decisions that do not come from a person (#17042).

Both approval systems — the LLC board approvals and the general approval
gates — are human-in-the-loop by definition, and no in-repo caller other than
the frontend decides them. A decision made with the internal service key, a
run/device JWT, a non-login token, the dev header or an auth-disabled
deployment is refused here rather than recorded as if a person had made it.
"""

from typing import Any, Mapping, Optional

from fastapi import HTTPException, status

from autobot_shared.auth.interactive_principal import is_interactive_human
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

HUMAN_DECISION_REQUIRED = "This decision requires a person signed in interactively"


def require_interactive_human(user: Optional[Mapping[str, Any]], action: str) -> None:
    """Raise 403 unless *user* is a person's interactive login."""
    if is_interactive_human(user):
        return
    user = user or {}
    logger.warning(
        "Refused %s: credential is not an interactive human login (auth_method=%s, username=%s)",
        action,
        user.get("auth_method"),
        user.get("username"),
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=HUMAN_DECISION_REQUIRED)
