# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Required fields of a /secrets ``infrastructure_host`` entry (#22145, owner default E7).

A host must say who to log in as and what it offers. Neither has a default: a
guessed ``root`` / ``ssh`` made every incomplete entry look usable and sent
credentials to an account the user never named.
"""

from typing import Any, Dict, List

from fastapi import HTTPException

HOST_REQUIRED_FIELDS = ("username", "capabilities")

HOST_FIELDS_MESSAGE = "Infrastructure host is missing required field(s): {fields}. Set them in Secrets."


def missing_host_fields(meta: Dict[str, Any] | None) -> List[str]:
    """Names of the required host fields that are absent or empty in *meta*."""
    meta = meta or {}
    return [name for name in HOST_REQUIRED_FIELDS if not meta.get(name)]


def refuse_incomplete_host(secret_type: Any, meta: Dict[str, Any] | None) -> None:
    """Raise a 422 naming the missing fields when an infrastructure host is incomplete."""
    if str(getattr(secret_type, "value", secret_type)) != "infrastructure_host":
        return
    missing = missing_host_fields(meta)
    if missing:
        raise HTTPException(status_code=422, detail=HOST_FIELDS_MESSAGE.format(fields=", ".join(missing)))
