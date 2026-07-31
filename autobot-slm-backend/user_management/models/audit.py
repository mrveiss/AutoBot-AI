# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

This file's only diff from the backend's copy was comment wording (the
backend's ``# nosec``/``# nosemgrep`` suppression comments were more verbose)
— see ``autobot_shared/user_management/models/audit.py`` for the
reconciliation note. Kept as a shim, not deleted, so every existing
``from user_management.models.audit import ...`` importer keeps working
unchanged.
"""

from autobot_shared.user_management.models.audit import (  # noqa: F401
    AuditAction,
    AuditLog,
    AuditResourceType,
)

__all__ = ["AuditLog", "AuditAction", "AuditResourceType"]
