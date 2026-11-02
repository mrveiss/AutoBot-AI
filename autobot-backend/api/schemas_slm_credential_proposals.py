# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the SLM stored-credential deletion proposal route (#20046)."""

from typing import Literal

from pydantic import BaseModel, Field


class SshPasswordDeletionProposal(BaseModel):
    """What the SLM proposes: a node and a credential kind, never a value."""

    node_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    credential_kind: Literal["ssh_password"] = "ssh_password"  # nosec B105  # pragma: allowlist secret


class SshPasswordDeletionProposalResponse(BaseModel):
    """The pending approval, and whether this call created it or found it already pending."""

    approval_id: str
    status: str
    created: bool
