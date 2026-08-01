# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

This file's only diff from SLM's copy was cosmetic/documentation (an unused
``Optional`` import, ``Mapped[Optional[...]]`` style, and stale
"encrypted at rest" comments predating the SystemSecret-table design) — see
``autobot_shared/user_management/models/sso.py`` for the reconciliation
note. Kept as a shim, not deleted, so every existing
``from user_management.models.sso import ...`` importer keeps working
unchanged.
"""

from autobot_shared.user_management.models.sso import (  # noqa: F401
    SSOProvider,
    SSOProviderType,
    UserSSOLink,
)

__all__ = ["SSOProvider", "SSOProviderType", "UserSSOLink"]
