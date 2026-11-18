# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The user an agent request runs for (#16665).

Read from ``request.metadata["user_id"]``, which the dispatching layer stamps -- never from
``request.payload``, which a caller or an LLM tool call controls. None means no user, and every
KB read then returns nothing.
"""

from typing import Any


def request_user_id(request: Any) -> str | None:
    """The dispatcher-stamped user of an agent *request*, or None."""
    return (getattr(request, "metadata", None) or {}).get("user_id")
