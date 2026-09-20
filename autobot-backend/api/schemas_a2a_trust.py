# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request schemas for A2A trust administration (#16950)."""

from pydantic import BaseModel, Field

from autobot_shared.trust_enums import TrustLevel


class A2ATrustGrantRequest(BaseModel):
    """An admin grant of trust to one (credential, peer id) pair -- never to a bare peer id."""

    subject: str = Field(..., min_length=1, description="The verified credential subject presenting the peer id")
    peer_id: str = Field(..., min_length=1, description="The peer's X-A2A-Agent-Id")
    level: TrustLevel = Field(..., description="The level to grant, held as a floor until misconduct revokes it")
