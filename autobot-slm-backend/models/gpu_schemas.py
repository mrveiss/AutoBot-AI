# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-node GPU state, as the agent's heartbeat reports it (#16281).

The agent sends ``extra_data["gpu"]`` (``autobot_shared.gpu_telemetry``) and the
SLM stores it on the node untouched. These models are how it leaves again: one
entry per node, in one of three states the monitoring UI shows as-is (#15226).
"""

from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from models.npu_schemas import NPUDeviceType


class GPUReportState(str, Enum):
    """What a node's latest heartbeat said about its GPUs."""

    NOT_REPORTED = "not_reported"  # no ``gpu`` key: an agent that predates #16280
    NONE = "none"  # probed, and no GPU is present
    PRESENT = "present"  # one or more GPUs, each measured or marked unmonitored


class GPUDevice(BaseModel):
    """One GPU. Metrics are null when the vendor tool could not read them."""

    device_type: NPUDeviceType
    index: int | None = None
    name: str | None = None
    monitored: bool
    utilization_percent: float | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    temperature_celsius: float | None = None
    power_watts: float | None = None


class GPUNodeStatus(BaseModel):
    """A node's GPU state from its latest heartbeat."""

    node_id: str
    hostname: str
    node_status: str
    state: GPUReportState
    devices: List[GPUDevice] = Field(default_factory=list)
    last_heartbeat: datetime | None = None


class GPUNodeListResponse(BaseModel):
    """Every node's GPU state."""

    nodes: List[GPUNodeStatus]
    total: int
