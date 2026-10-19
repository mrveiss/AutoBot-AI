# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Result and status records for :mod:`services.redis_service_manager`.

Split out of ``redis_service_manager.py`` (#17576) so that module stays within its file-size ceiling; the
manager imports all three, so ``from services.redis_service_manager import ...`` is unchanged for callers.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ServiceOperationResult:
    """Result of a service operation"""

    success: bool
    operation: str  # "start", "stop", "restart", "status"
    message: str
    duration_seconds: float
    timestamp: datetime
    new_status: str  # "running", "stopped", "failed", "unknown"
    error: str | None = None


@dataclass
class ManagedServiceStatus:
    """Current service status"""

    status: str  # "running", "stopped", "failed", "unknown"
    pid: int | None = None
    uptime_seconds: float | None = None
    memory_mb: float | None = None
    last_check: datetime = None


@dataclass
class ServiceHealthReport:
    """Detailed health status"""

    overall_status: str  # "healthy", "degraded", "critical"
    service_running: bool
    connectivity: bool
    response_time_ms: float
    last_successful_command: datetime | None = None
    error_count_last_hour: int = 0
    recommendations: list = None
