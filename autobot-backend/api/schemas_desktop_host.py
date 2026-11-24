# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Base for every chat Desktop control request (#22145): the selected /secrets host id is required."""

from pydantic import BaseModel, Field


class DesktopHostRequest(BaseModel):
    """A control acts on the host being shown, never on a default display."""

    host_id: str = Field(
        ..., min_length=1, description="Selected /secrets infrastructure host id; also the control-lock key"
    )


class DesktopVmEndpointResponse(BaseModel):
    """Where the chat Desktop's desktop VM is: the one answer both the page and the controls use."""

    host: str
    port: int = Field(..., description="noVNC web port")
