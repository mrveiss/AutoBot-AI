# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the internal stored-SSH-password routes (#20046)."""

from pydantic import BaseModel


class NodeSshPasswordDeleteResponse(BaseModel):
    """What a deletion removed. Carries the node and a flag, never a value."""

    node_id: str
    deleted: bool
