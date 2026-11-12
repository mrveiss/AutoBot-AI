# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Aggregated per-agent metrics model, split out of ``agent_analytics`` (#21270)."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class AgentMetrics:
    """Aggregated metrics for an agent"""

    agent_id: str
    agent_type: str
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    timeout_tasks: int = 0
    avg_duration_ms: float = 0
    min_duration_ms: float = 0
    max_duration_ms: float = 0
    total_tokens_used: int = 0
    error_rate: float = 0
    success_rate: float = 0
    last_activity: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "cancelled_tasks": self.cancelled_tasks,
            "timeout_tasks": self.timeout_tasks,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "total_tokens_used": self.total_tokens_used,
            "error_rate": round(self.error_rate, 2),
            "success_rate": round(self.success_rate, 2),
            "last_activity": self.last_activity,
        }

    # === Issue #372: Feature Envy Reduction Methods ===

    def get_prometheus_labels(self) -> str:
        """Get Prometheus label string for this agent (Issue #372 - reduces feature envy)."""
        return f'agent_id="{self.agent_id}",agent_type="{self.agent_type}"'

    def to_prometheus_tasks_line(self) -> str:
        """Generate Prometheus line for total tasks (Issue #372 - reduces feature envy)."""
        return f"autobot_agent_tasks_total{{{self.get_prometheus_labels()}}} {self.total_tasks}"

    def to_prometheus_success_rate_line(self) -> str:
        """Generate Prometheus line for success rate (Issue #372 - reduces feature envy)."""
        return f"autobot_agent_success_rate{{{self.get_prometheus_labels()}}} {self.success_rate}"

    def to_prometheus_error_rate_line(self) -> str:
        """Generate Prometheus line for error rate (Issue #372 - reduces feature envy)."""
        return f"autobot_agent_error_rate{{{self.get_prometheus_labels()}}} {self.error_rate}"

    def to_prometheus_duration_line(self) -> str:
        """Generate Prometheus line for avg duration (Issue #372 - reduces feature envy)."""
        return f"autobot_agent_avg_duration_ms{{{self.get_prometheus_labels()}}} {self.avg_duration_ms}"

    def to_csv_row(self) -> List[Any]:
        """Generate CSV row for export (Issue #372 - reduces feature envy)."""
        return [
            self.agent_id,
            self.agent_type,
            self.total_tasks,
            self.completed_tasks,
            self.failed_tasks,
            self.timeout_tasks,
            self.success_rate,
            self.error_rate,
            self.avg_duration_ms,
            self.total_tokens_used,
            self.last_activity or "",
        ]
