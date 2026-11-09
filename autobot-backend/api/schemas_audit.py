# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Response models of the audit-log query API (``api/audit.py``)."""

from typing import List, Optional

from pydantic import BaseModel

from services.audit_logger import AuditResult
from type_defs.common import Metadata


class AuditEntryResponse(BaseModel):
    """One audit row, as ``AuditEntry.to_response_dict`` sends it (#20173).

    ``timestamp`` is epoch SECONDS; the operation's data is in ``details``.
    """

    id: str
    timestamp: float
    date: str
    operation: str
    result: AuditResult
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    session_id: Optional[str] = None
    user_role: Optional[str] = None
    resource: Optional[str] = None
    vm_source: Optional[str] = None
    vm_name: Optional[str] = None
    details: Metadata
    performance_ms: Optional[float] = None


class AuditQueryResponse(BaseModel):
    """Audit log query response."""

    success: bool
    total_returned: int
    has_more: bool
    entries: List[AuditEntryResponse]
    query: dict
