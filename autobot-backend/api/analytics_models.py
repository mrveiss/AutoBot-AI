# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics API Models - Pydantic models for analytics endpoints.

This module contains all Pydantic models used by the analytics API endpoints.
Extracted from analytics.py for better maintainability (Issue #185).

Models:
- AnalyticsOverview: Dashboard overview model
- CommunicationPattern: Communication pattern analysis model
- CodeAnalysisRequest: Code analysis request model
- PerformanceMetrics: Performance metrics model
- RealTimeEvent: Real-time analytics event model

Related Issues: #185 (Split oversized files)
"""

from typing import List, Optional

from constants import PATH
from pydantic import BaseModel, Field
from type_defs.common import Metadata


class AnalyticsOverview(BaseModel):
    """Comprehensive analytics dashboard overview model"""

    timestamp: str
    system_health: Metadata
    performance_metrics: Metadata
    communication_patterns: Metadata
    code_analysis_status: Metadata
    usage_statistics: Metadata
    realtime_metrics: Metadata
    trends: Metadata


class CommunicationPattern(BaseModel):
    """Communication pattern analysis model"""

    endpoint: str
    frequency: int
    avg_response_time: float
    error_rate: float
    last_accessed: str
    pattern_type: str = Field(description="API, WebSocket, or Internal")


class CodeAnalysisRequest(BaseModel):
    """Code analysis request model"""

    target_path: Optional[str] = Field(default_factory=lambda: str(PATH.PROJECT_ROOT))
    analysis_type: str = Field(
        default="full", description="full, incremental, or communication_chains"
    )
    include_metrics: bool = True


class PerformanceMetrics(BaseModel):
    """Performance metrics model"""

    response_times: List[float]
    throughput: float
    error_rates: Metadata
    resource_utilization: Metadata
    bottlenecks: List[str]


class RealTimeEvent(BaseModel):
    """Real-time analytics event model"""

    event_type: str
    timestamp: str
    data: Metadata
    severity: str = "info"
