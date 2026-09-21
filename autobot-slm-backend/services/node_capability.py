# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Heartbeat extra_data -> persisted capability profile (#15495).

Values arrive through the existing heartbeat ``extra_data`` blob -- no new
side-channel (#15495 AC2) -- exactly like GPU telemetry already does
(``services/node_gpu.py``, #16280), whose ``GPUDevice`` validation this
module reuses rather than re-parsing the same list a second way.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.gpu_schemas import GPUDevice
from models.node_capability import node_capability_profiles
from models.npu_schemas import NPUDeviceType

_GPU_DEVICE_TYPES = frozenset({NPUDeviceType.NVIDIA_GPU, NPUDeviceType.AMD_GPU})

# health_collector.py (#15495) always sends these three together once an
# agent is updated -- unlike "gpu", which pre-updated agents already send
# (#16280), so it cannot serve as the "this agent knows about #15495" gate.
# Gating on these three specifically means a not-yet-updated agent's
# heartbeat (partial keys) never reaches the write below and so can never
# blank a real prior value with the None a partial row would carry.
_PROFILE_KEYS = ("total_ram_mb", "npu_present", "free_disk_model_dir_mb")


def _gpu_summary(raw: Any) -> tuple[bool | None, str | None, int | None]:
    """``(gpu_present, gpu_model, total_vram_mb)`` from a heartbeat's ``gpu`` list.

    ``None`` for all three when the agent never reported GPUs at all (the
    ``NOT_REPORTED`` case #16280 defines) -- distinct from an empty list,
    which is a real, measured "no GPU" (so ``total_vram_mb=0`` there is a
    true zero, not the fabricated one #15495 AC7 forbids).
    """
    if not isinstance(raw, list):
        return None, None, None
    devices = []
    for entry in raw:
        try:
            device = GPUDevice.model_validate(entry)
        except ValidationError:
            continue
        if device.device_type in _GPU_DEVICE_TYPES:
            devices.append(device)
    if not devices:
        return False, None, 0
    names = [device.name for device in devices if device.name]
    measured = [device.memory_total_mb for device in devices if device.memory_total_mb is not None]
    total_vram_mb = int(sum(measured)) if measured else None
    return True, ", ".join(names) or None, total_vram_mb


async def apply_capability_profile(db: AsyncSession, node_id: str, extra_data: dict) -> None:
    """Upsert *node_id*'s capability profile from one heartbeat's ``extra_data``.

    A no-op unless this heartbeat carries all three #15495 keys together (an
    agent that predates #15495 sends none of them) -- nothing here should
    overwrite a real prior value with the None a partial row would carry.
    """
    if not all(key in extra_data for key in _PROFILE_KEYS):
        return
    gpu_present, gpu_model, total_vram_mb = _gpu_summary(extra_data.get("gpu"))
    values = {
        "total_ram_mb": extra_data.get("total_ram_mb"),
        "total_vram_mb": total_vram_mb,
        "gpu_present": gpu_present,
        "gpu_model": gpu_model,
        "npu_present": extra_data.get("npu_present"),
        "free_disk_model_dir_mb": extra_data.get("free_disk_model_dir_mb"),
        "updated_at": datetime.now(timezone.utc),
    }

    existing = await db.execute(
        select(node_capability_profiles.c.node_id).where(node_capability_profiles.c.node_id == node_id)
    )
    if existing.scalar_one_or_none() is None:
        await db.execute(insert(node_capability_profiles).values(node_id=node_id, **values))
    else:
        await db.execute(
            update(node_capability_profiles).where(node_capability_profiles.c.node_id == node_id).values(**values)
        )
