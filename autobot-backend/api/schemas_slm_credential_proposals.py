# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the SLM credential-action routes: propose, claim, report (#20046, #20750)."""

from typing import Literal

from pydantic import BaseModel, Field

# Never "." or "..": URL normalisation would drop such a segment from the SLM delete path (#20046).
NODE_ID_PATTERN = r"^([A-Za-z0-9_-][A-Za-z0-9._-]*|\.[A-Za-z0-9_-][A-Za-z0-9._-]*|\.\.[A-Za-z0-9._-]+)$"

#: The actions a proposal may name; autobot_shared.slm_credential_actions.ACTIONS holds their specs.
CredentialActionName = Literal["slm_node_ssh_password_delete", "slm_backend_internal_key_realign"]
_NODE_ID = Field(min_length=1, max_length=64, pattern=NODE_ID_PATTERN)


class CredentialProposal(BaseModel):
    """What is proposed: an action and a node, never a credential value."""

    action: CredentialActionName
    node_id: str = _NODE_ID


class CredentialProposalResponse(BaseModel):
    """The node's open approval for the action, and whether this call created it."""

    approval_id: str
    status: str
    created: bool


class CredentialClaim(BaseModel):
    """The applying side names the action and node it is about to change; the approval must name the same."""

    action: CredentialActionName
    node_id: str = _NODE_ID


class CredentialClaimResponse(BaseModel):
    """The approval was valid and is now spent."""

    approval_id: str
    node_id: str


class CredentialOutcome(BaseModel):
    """How applying a claimed approval went, for its audit trail and its comment thread."""

    action: CredentialActionName
    node_id: str = _NODE_ID
    result: Literal["applied", "apply_failed"]
    #: What the applying side saw, never a credential value.
    detail: str = Field(default="", max_length=500)
