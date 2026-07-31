# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

This file's only diff from the backend's copy was cosmetic (the backend
carried a redundant ``from __future__ import annotations`` plus the unused
``Optional`` import / ``Mapped[Optional[...]]`` style already noted on the
other model files) — see
``autobot_shared/user_management/models/api_key.py`` for the reconciliation
note. Kept as a shim, not deleted, so every existing
``from user_management.models.api_key import ...`` importer keeps working
unchanged.
"""

from autobot_shared.user_management.models.api_key import (  # noqa: F401
    API_KEY_SCOPES,
    APIKey,
)

__all__ = ["APIKey", "API_KEY_SCOPES"]
