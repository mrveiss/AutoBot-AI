# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response schemas for the per-node capability profile API (#15495).

Split from ``models/schemas.py``, which is at its file-size ratchet ceiling --
the same move ``models/gpu_schemas.py`` and ``models/npu_schemas.py`` already
made for the same reason.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NodeCapabilityProfileResponse(BaseModel):
    """One node's hardware capability profile. Unset fields mean "not yet reported"."""

    node_id: str
    total_ram_mb: int | None = None
    total_vram_mb: int | None = None
    gpu_present: bool | None = None
    gpu_model: str | None = None
    npu_present: bool | None = None
    free_disk_model_dir_mb: int | None = None
    updated_at: datetime | None = None
