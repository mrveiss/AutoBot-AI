# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DataResponse payload models for GET /agent/agents/available and /status (#5772, #22141)."""

from typing import List

from pydantic import BaseModel

from type_defs.ai_stack_agents import AIStackAgent


class AgentCapabilityInfo(BaseModel):
    """Single agent entry in the /agents/available response."""

    name: str
    description: str
    capabilities: List[str]
    status: str


class AgentAvailableData(BaseModel):
    """data payload for GET /agent/agents/available."""

    total_agents: int
    agents: List[AgentCapabilityInfo]
    coordination_modes: List[str]
    multi_agent_support: bool


class AgentStatusData(BaseModel):
    """data payload for GET /agent/agents/status."""

    ai_stack_status: str
    total_agents: int
    available_agents: List[AIStackAgent]  # #22141: the client's typed shape
    multi_agent_coordination: bool
    npu_acceleration: bool
    research_capabilities: bool
    development_tools: bool
