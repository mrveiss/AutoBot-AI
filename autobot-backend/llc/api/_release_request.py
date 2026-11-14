# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The request body of ``POST /work-items/{id}/release``."""

from pydantic import BaseModel

from ._common import FenceSafeAgentId


class ReleaseRequest(BaseModel):
    agent_id: FenceSafeAgentId
