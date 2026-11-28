# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response models for the stored-connector-credential routes (``api/admin_connector_credentials.py``, #20701).

No model here has a field that can carry a credential value: records are described by id, type and field NAMES.
"""

from pydantic import BaseModel


class ConnectorCredentialFindingResponse(BaseModel):
    """One record holding sensitive values. ``fields`` are names, never values."""

    connector_id: str
    connector_type: str
    fields: list[str]
    has_secrets_store_copy: bool


class ConnectorCredentialScanResponse(BaseModel):
    """Counts of affected records. ``unscannable_ids`` could not be checked: never read them as clean."""

    scanned: int
    affected: int
    with_store_copy_count: int
    without_store_copy_count: int
    findings: list[ConnectorCredentialFindingResponse]
    unscannable_ids: list[str]


class ConnectorCredentialCleanupRequest(BaseModel):
    """Propose removing the clear-text copies from one connector record."""

    connector_id: str


class ConnectorCredentialCleanupResponse(BaseModel):
    """The PENDING approval created; nothing has been rewritten."""

    approval_id: str
    status: str
    action: str
    connector_id: str
