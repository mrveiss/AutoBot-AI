# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-node GPU state from heartbeat telemetry (#16281).

Every agent reports its GPUs as ``extra_data["gpu"]`` (#16280), and the
reconciler merges that onto the node untouched. This module reads it back two
ways: as ``GPUNodeStatus`` for ``GET /api/monitoring/gpu/nodes``, and as the
per-node ``autobot_gpu_*`` series ``/metrics`` serves to Prometheus.

The series are published from mapper events on ``Node``. Every heartbeat
flushes its node, so the series follow each heartbeat without a hook in the
heartbeat path -- ``api/nodes.py`` and ``services/reconciler.py``, like
``main.py``, sit at their file-size ceilings. The SLM runs one uvicorn worker,
so the registry these events write is the one ``/metrics`` reads. After a
restart a node's series reappear with its next heartbeat.
"""

import logging
from typing import Any, Dict, List

from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Node
from models.gpu_schemas import GPUDevice, GPUNodeStatus, GPUReportState
from models.npu_schemas import NPUDeviceType
from status_enums import NodeStatus

logger = logging.getLogger(__name__)

# The NPUDeviceType values a GPU entry may carry; anything else is not a GPU.
GPU_DEVICE_TYPES = frozenset({NPUDeviceType.NVIDIA_GPU, NPUDeviceType.AMD_GPU})

# Nodes whose last heartbeat is history rather than a measurement.
_NOT_MEASURING = frozenset({NodeStatus.OFFLINE.value, NodeStatus.DECOMMISSIONED.value})

# node_id -> the ``node`` label its series were last published under, so a
# renamed node's old series are retracted too.
_published_as: Dict[str, str] = {}


def _gpu_devices(node: Node, raw: List[Any]) -> List[GPUDevice]:
    """The valid GPU entries of a heartbeat's ``gpu`` list; malformed ones are logged and skipped."""
    devices = []
    for entry in raw:
        try:
            device = GPUDevice.model_validate(entry)
        except ValidationError as exc:
            logger.warning("node=%s sent a malformed GPU entry: %s", node.node_id, exc.errors()[:1])
            continue
        if device.device_type in GPU_DEVICE_TYPES:
            devices.append(device)
    return devices


def node_gpu_status(node: Node) -> GPUNodeStatus:
    """One node's GPU state from the ``gpu`` block of its latest heartbeat."""
    raw = (node.extra_data or {}).get("gpu")
    if isinstance(raw, list):
        devices = _gpu_devices(node, raw)
        state = GPUReportState.PRESENT if devices else GPUReportState.NONE
    else:
        devices, state = [], GPUReportState.NOT_REPORTED
    return GPUNodeStatus(
        node_id=node.node_id,
        hostname=node.hostname or node.node_id,
        node_status=node.status or "",
        state=state,
        devices=devices,
        last_heartbeat=node.last_heartbeat,
    )


async def fleet_gpu_statuses(db: AsyncSession) -> List[GPUNodeStatus]:
    """Every node's GPU state, ordered by hostname."""
    result = await db.execute(select(Node).order_by(Node.hostname))
    return [node_gpu_status(node) for node in result.scalars().all()]


def _memory_percent(device: GPUDevice) -> float | None:
    """Used over total VRAM, or None when either is unknown."""
    if device.memory_used_mb is None or not device.memory_total_mb:
        return None
    return round(device.memory_used_mb / device.memory_total_mb * 100, 1)


def retract_node_gpu(metrics: Any, node_id: str) -> None:
    """Drop every series published for *node_id*, under whatever name it had."""
    label = _published_as.pop(node_id, None)
    if label is not None:
        metrics.remove_gpu_node(label)


def publish_node_gpu(metrics: Any, node: Node) -> None:
    """Replace *node*'s ``autobot_gpu_*`` series with what its latest heartbeat says.

    Offline and decommissioned nodes, and agents that never reported, publish
    nothing -- their last numbers are history, not a measurement. An unmonitored
    device counts toward ``autobot_gpu_available`` but sets no metric series.
    """
    status = node_gpu_status(node)
    retract_node_gpu(metrics, node.node_id)
    if status.state is GPUReportState.NOT_REPORTED or status.node_status in _NOT_MEASURING:
        return
    _published_as[node.node_id] = status.hostname
    metrics.set_gpu_available(bool(status.devices), node=status.hostname)
    for device in status.devices:
        if not device.monitored:
            continue
        metrics.update_gpu_metrics(
            gpu_id=str(device.index),
            gpu_name=device.name or device.device_type.value,
            utilization=device.utilization_percent,
            memory_utilization=_memory_percent(device),
            temperature=device.temperature_celsius,
            power_watts=device.power_watts,
            node=status.hostname,
        )


def _metrics_manager() -> Any:
    """The process registry's manager, imported late like ``main.py``'s ``/metrics``.

    Its import chain builds file log handlers from ``config`` at import time,
    which a module the SLM loads at startup must not trigger early.
    """
    from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager  # noqa: PLC0415

    return get_metrics_manager()


def _on_node_written(_mapper: Any, _connection: Any, node: Node) -> None:
    """Mapper hook. It runs inside the flush, so it must never raise into the node's write."""
    try:
        publish_node_gpu(_metrics_manager(), node)
    except Exception:  # noqa: BLE001 -- the series are a side channel; the heartbeat write must land
        logger.exception("GPU series not published for node=%s", getattr(node, "node_id", "?"))


def _on_node_deleted(_mapper: Any, _connection: Any, node: Node) -> None:
    """Mapper hook: a deleted node takes its series with it."""
    try:
        retract_node_gpu(_metrics_manager(), node.node_id)
    except Exception:  # noqa: BLE001 -- as above: never fail the delete over a metric
        logger.exception("GPU series not retracted for node=%s", getattr(node, "node_id", "?"))


event.listen(Node, "after_insert", _on_node_written)
event.listen(Node, "after_update", _on_node_written)
event.listen(Node, "after_delete", _on_node_deleted)
