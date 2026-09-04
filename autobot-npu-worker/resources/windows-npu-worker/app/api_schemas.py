# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response bodies for the worker's HTTP API (#15642).

The four Pydantic models the FastAPI routes declare. Kept apart from the
handlers so the contract can be read — or imported by a test — without pulling
in ONNX Runtime, OpenVINO or the model manager.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

from typing import Any, Dict

from pydantic import BaseModel


# Pydantic models
class NPUTaskRequest(BaseModel):
    """NPU task request model"""

    task_type: str
    model_name: str
    input_data: Dict[str, Any]
    priority: int = 1
    timeout_seconds: int = 30
    optimization_level: str = "balanced"


class NPUTaskResponse(BaseModel):
    """NPU task response model"""

    task_id: str
    status: str
    result: Dict[str, Any] | None = None
    error: str | None = None
    processing_time_ms: float | None = None
    npu_utilization_percent: float | None = None
    optimization_metrics: Dict[str, Any] | None = None


class PairRequest(BaseModel):
    """
    Issue #641: Request from main host to pair with this worker.

    Main host sends this request to assign a permanent worker ID.
    """

    worker_id: str  # ID assigned by main host
    main_host: str  # IP/hostname of the main host
    config: Dict[str, Any] | None = None  # Optional config from main host


class PairResponse(BaseModel):
    """
    Issue #641: Response after successful pairing.
    """

    success: bool
    worker_id: str
    message: str
    device_info: Dict[str, Any] | None = None
