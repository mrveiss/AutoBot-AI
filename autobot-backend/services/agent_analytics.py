# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Analytics Service - Track and analyze agent performance.

This module provides comprehensive analytics for AI agent operations:
- Task completion rates
- Execution time tracking
- Error rate analysis
- Resource consumption monitoring
- Agent comparison metrics

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from autobot_shared.redis_client import RedisDatabase, get_redis_client

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of agents in the system"""

    CHAT = "chat"
    ORCHESTRATOR = "orchestrator"
    KNOWLEDGE = "knowledge"
    CODE_ANALYSIS = "code_analysis"
    TERMINAL = "terminal"
    BROWSER = "browser"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    """Task execution status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class AgentTaskRecord:
    """Record of an agent task execution"""

    agent_id: str
    agent_type: str
    task_id: str
    task_name: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    input_size: Optional[int] = None
    output_size: Optional[int] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "input_size": self.input_size,
            "output_size": self.output_size,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTaskRecord":
        """Create from dictionary"""
        return cls(
            agent_id=data["agent_id"],
            agent_type=data["agent_type"],
            task_id=data["task_id"],
            task_name=data["task_name"],
            status=data["status"],
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            duration_ms=data.get("duration_ms"),
            input_size=data.get("input_size"),
            output_size=data.get("output_size"),
            tokens_used=data.get("tokens_used"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


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
    last_activity: Optional[str] = None

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


class AgentAnalytics:
    """
    Tracks and analyzes agent performance across the system.

    Features:
    - Per-agent task tracking
    - Performance aggregation
    - Error rate analysis
    - Agent comparison
    - Historical trends
    """

    REDIS_KEY_PREFIX = "agent_analytics:"
    TASK_LIST_KEY = f"{REDIS_KEY_PREFIX}tasks"
    AGENT_METRICS_KEY = f"{REDIS_KEY_PREFIX}metrics"
    AGENT_HISTORY_KEY = f"{REDIS_KEY_PREFIX}history"

    def __init__(self):
        """Initialize agent analytics service with lazy Redis client."""
        self._redis_client = None

    async def get_redis(self):
        """Get async Redis client"""
        if self._redis_client is None:
            self._redis_client = await get_redis_client(
                async_client=True, database=RedisDatabase.ANALYTICS
            )
        return self._redis_client

    async def track_task_start(
        self,
        agent_id: str,
        agent_type: str,
        task_id: str,
        task_name: str,
        input_size: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentTaskRecord:
        """
        Track the start of an agent task.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent
            task_id: Unique task identifier
            task_name: Human-readable task name
            input_size: Size of input data (optional)
            metadata: Additional task metadata

        Returns:
            AgentTaskRecord for tracking
        """
        record = AgentTaskRecord(
            agent_id=agent_id,
            agent_type=agent_type,
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.RUNNING.value,
            started_at=datetime.utcnow().isoformat(),
            input_size=input_size,
            metadata=metadata or {},
        )

        # Store running task
        try:
            redis = await self.get_redis()
            running_key = f"{self.REDIS_KEY_PREFIX}running:{task_id}"
            await redis.set(
                running_key, json.dumps(record.to_dict()), ex=3600
            )  # 1 hour TTL
        except Exception as e:
            logger.error("Failed to track task start: %s", e)

        return record

    async def track_task_complete(
        self,
        task_id: str,
        status: TaskStatus,
        output_size: Optional[int] = None,
        tokens_used: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Optional[AgentTaskRecord]:
        """
        Track task completion.

        Args:
            task_id: Task identifier from track_task_start
            status: Final task status
            output_size: Size of output data
            tokens_used: Tokens consumed during task
            error_message: Error message if failed

        Returns:
            Updated AgentTaskRecord or None if not found
        """
        try:
            redis = await self.get_redis()
            running_key = f"{self.REDIS_KEY_PREFIX}running:{task_id}"

            # Get running task
            task_data = await redis.get(running_key)
            if not task_data:
                logger.warning("Task not found for completion: %s", task_id)
                return None

            task_str = (
                task_data if isinstance(task_data, str) else task_data.decode("utf-8")
            )
            record = AgentTaskRecord.from_dict(json.loads(task_str))

            # Update completion info
            completed_at = datetime.utcnow()
            started_at = datetime.fromisoformat(record.started_at)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            record.status = status.value
            record.completed_at = completed_at.isoformat()
            record.duration_ms = duration_ms
            record.output_size = output_size
            record.tokens_used = tokens_used
            record.error_message = error_message

            # Store completed task
            await self._store_completed_task(record)

            # Update agent metrics
            await self._update_agent_metrics(record)

            # Clean up running task
            await redis.delete(running_key)

            return record

        except Exception as e:
            logger.error("Failed to track task completion: %s", e)
            return None

    async def _store_completed_task(self, record: AgentTaskRecord) -> None:
        """Store completed task record"""
        try:
            redis = await self.get_redis()

            # Add to task list (keep last 50k tasks)
            await redis.lpush(self.TASK_LIST_KEY, json.dumps(record.to_dict()))
            await redis.ltrim(self.TASK_LIST_KEY, 0, 49999)

            # Add to agent-specific history
            agent_key = f"{self.AGENT_HISTORY_KEY}:{record.agent_id}"
            await redis.lpush(agent_key, json.dumps(record.to_dict()))
            await redis.ltrim(agent_key, 0, 999)  # Keep last 1000 per agent
            await redis.expire(agent_key, 86400 * 30)  # 30 day retention

        except Exception as e:
            logger.error("Failed to store completed task: %s", e)

    async def _update_agent_metrics(self, record: AgentTaskRecord) -> None:
        """Update aggregated metrics for an agent"""
        try:
            redis = await self.get_redis()
            metrics_key = f"{self.AGENT_METRICS_KEY}:{record.agent_id}"

            # Increment counters - use dispatch table to flatten if/elif chain (Issue #315)
            status_counter_map = {
                TaskStatus.COMPLETED.value: "completed_tasks",
                TaskStatus.FAILED.value: "failed_tasks",
                TaskStatus.CANCELLED.value: "cancelled_tasks",
                TaskStatus.TIMEOUT.value: "timeout_tasks",
            }
            await redis.hincrby(metrics_key, "total_tasks", 1)
            if counter_field := status_counter_map.get(record.status):
                await redis.hincrby(metrics_key, counter_field, 1)

            if record.duration_ms:
                await redis.hincrbyfloat(
                    metrics_key, "total_duration_ms", record.duration_ms
                )

            if record.tokens_used:
                await redis.hincrby(
                    metrics_key, "total_tokens_used", record.tokens_used
                )

            # Update metadata
            await redis.hset(metrics_key, "agent_type", record.agent_type)
            await redis.hset(
                metrics_key, "last_activity", record.completed_at or record.started_at
            )

        except Exception as e:
            logger.error("Failed to update agent metrics: %s", e)

    async def get_agent_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        """Get aggregated metrics for an agent"""
        try:
            redis = await self.get_redis()
            metrics_key = f"{self.AGENT_METRICS_KEY}:{agent_id}"

            data = await redis.hgetall(metrics_key)
            if not data:
                return None

            # Convert bytes to string if needed
            metrics_data = {}
            for k, v in data.items():
                key = k if isinstance(k, str) else k.decode("utf-8")
                val = v if isinstance(v, str) else v.decode("utf-8")
                metrics_data[key] = val

            total_tasks = int(metrics_data.get("total_tasks", 0))
            completed_tasks = int(metrics_data.get("completed_tasks", 0))
            failed_tasks = int(metrics_data.get("failed_tasks", 0))
            total_duration = float(metrics_data.get("total_duration_ms", 0))

            # Calculate rates
            if total_tasks > 0:
                error_rate = (failed_tasks / total_tasks) * 100
                success_rate = (completed_tasks / total_tasks) * 100
                avg_duration = total_duration / total_tasks
            else:
                error_rate = 0
                success_rate = 0
                avg_duration = 0

            return AgentMetrics(
                agent_id=agent_id,
                agent_type=metrics_data.get("agent_type", "unknown"),
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                cancelled_tasks=int(metrics_data.get("cancelled_tasks", 0)),
                timeout_tasks=int(metrics_data.get("timeout_tasks", 0)),
                avg_duration_ms=avg_duration,
                total_tokens_used=int(metrics_data.get("total_tokens_used", 0)),
                error_rate=error_rate,
                success_rate=success_rate,
                last_activity=metrics_data.get("last_activity"),
            )

        except Exception as e:
            logger.error("Failed to get agent metrics: %s", e)
            return None

    async def get_all_agents_metrics(self) -> List[AgentMetrics]:
        """Get metrics for all agents"""
        try:
            redis = await self.get_redis()
            pattern = f"{self.AGENT_METRICS_KEY}:*"
            keys = await redis.keys(pattern)

            if not keys:
                return []

            # Batch fetch all metrics using pipeline (fix N+1 query)
            pipe = redis.pipeline()
            for key in keys:
                pipe.hgetall(key)
            results = await pipe.execute()

            # Process results
            metrics_list = []
            for key, data in zip(keys, results):
                if not data:
                    continue

                key_str = key if isinstance(key, str) else key.decode("utf-8")
                agent_id = key_str.split(":")[-1]

                # Convert bytes to string if needed
                metrics_data = {}
                for k, v in data.items():
                    dict_key = k if isinstance(k, str) else k.decode("utf-8")
                    val = v if isinstance(v, str) else v.decode("utf-8")
                    metrics_data[dict_key] = val

                total_tasks = int(metrics_data.get("total_tasks", 0))
                completed_tasks = int(metrics_data.get("completed_tasks", 0))
                failed_tasks = int(metrics_data.get("failed_tasks", 0))
                total_duration = float(metrics_data.get("total_duration_ms", 0))

                # Calculate rates
                if total_tasks > 0:
                    error_rate = (failed_tasks / total_tasks) * 100
                    success_rate = (completed_tasks / total_tasks) * 100
                    avg_duration = total_duration / total_tasks
                else:
                    error_rate = 0
                    success_rate = 0
                    avg_duration = 0

                metrics = AgentMetrics(
                    agent_id=agent_id,
                    agent_type=metrics_data.get("agent_type", "unknown"),
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    failed_tasks=failed_tasks,
                    cancelled_tasks=int(metrics_data.get("cancelled_tasks", 0)),
                    timeout_tasks=int(metrics_data.get("timeout_tasks", 0)),
                    avg_duration_ms=avg_duration,
                    total_tokens_used=int(metrics_data.get("total_tokens_used", 0)),
                    error_rate=error_rate,
                    success_rate=success_rate,
                    last_activity=metrics_data.get("last_activity"),
                )
                metrics_list.append(metrics)

            # Sort by total tasks descending
            metrics_list.sort(key=lambda x: x.total_tasks, reverse=True)

            return metrics_list

        except Exception as e:
            logger.error("Failed to get all agents metrics: %s", e)
            return []

    async def get_agent_history(
        self, agent_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get task history for an agent"""
        try:
            redis = await self.get_redis()
            agent_key = f"{self.AGENT_HISTORY_KEY}:{agent_id}"
            records = await redis.lrange(agent_key, 0, limit - 1)

            return [json.loads(r) for r in records]

        except Exception as e:
            logger.error("Failed to get agent history: %s", e)
            return []

    async def get_recent_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent tasks across all agents"""
        try:
            redis = await self.get_redis()
            records = await redis.lrange(self.TASK_LIST_KEY, 0, limit - 1)
            return [json.loads(r) for r in records]

        except Exception as e:
            logger.error("Failed to get recent tasks: %s", e)
            return []

    async def compare_agents(
        self, agent_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compare performance across agents.

        Args:
            agent_ids: Specific agents to compare (all if None)

        Returns:
            Comparison data including rankings
        """
        if agent_ids:
            metrics_list = []
            for agent_id in agent_ids:
                metrics = await self.get_agent_metrics(agent_id)
                if metrics:
                    metrics_list.append(metrics)
        else:
            metrics_list = await self.get_all_agents_metrics()

        if not metrics_list:
            return {"agents": [], "rankings": {}}

        # Calculate rankings
        by_success_rate = sorted(
            metrics_list, key=lambda x: x.success_rate, reverse=True
        )
        by_speed = sorted(
            metrics_list,
            key=lambda x: x.avg_duration_ms if x.avg_duration_ms > 0 else float("inf"),
        )
        by_volume = sorted(metrics_list, key=lambda x: x.total_tasks, reverse=True)

        return {
            "agents": [m.to_dict() for m in metrics_list],
            "rankings": {
                "by_success_rate": [m.agent_id for m in by_success_rate],
                "by_speed": [m.agent_id for m in by_speed],
                "by_volume": [m.agent_id for m in by_volume],
            },
            "summary": {
                "total_agents": len(metrics_list),
                "avg_success_rate": round(
                    sum(m.success_rate for m in metrics_list) / len(metrics_list), 2
                ),
                "total_tasks_processed": sum(m.total_tasks for m in metrics_list),
            },
        }

    async def get_performance_trends(
        self, agent_id: Optional[str] = None, days: int = 7
    ) -> Dict[str, Any]:
        """
        Get performance trends over time.

        Args:
            agent_id: Specific agent (all if None)
            days: Number of days to analyze

        Returns:
            Daily performance metrics
        """
        try:
            if agent_id:
                tasks = await self.get_agent_history(agent_id, limit=1000)
            else:
                tasks = await self.get_recent_tasks(limit=5000)

            # Filter to requested time range
            cutoff = datetime.utcnow() - timedelta(days=days)
            filtered_tasks = [
                t for t in tasks if datetime.fromisoformat(t["started_at"]) > cutoff
            ]

            # Group by day
            daily_stats = {}
            for task in filtered_tasks:
                day = task["started_at"][:10]  # YYYY-MM-DD
                if day not in daily_stats:
                    daily_stats[day] = {
                        "total": 0,
                        "completed": 0,
                        "failed": 0,
                        "total_duration_ms": 0,
                    }
                daily_stats[day]["total"] += 1
                if task["status"] == "completed":
                    daily_stats[day]["completed"] += 1
                elif task["status"] == "failed":
                    daily_stats[day]["failed"] += 1
                if task.get("duration_ms"):
                    daily_stats[day]["total_duration_ms"] += task["duration_ms"]

            # Calculate daily averages
            for day in daily_stats:
                stats = daily_stats[day]
                if stats["total"] > 0:
                    stats["success_rate"] = round(
                        (stats["completed"] / stats["total"]) * 100, 2
                    )
                    stats["avg_duration_ms"] = round(
                        stats["total_duration_ms"] / stats["total"], 2
                    )
                else:
                    stats["success_rate"] = 0
                    stats["avg_duration_ms"] = 0

            return {
                "period_days": days,
                "agent_id": agent_id,
                "daily_stats": daily_stats,
                "total_tasks": len(filtered_tasks),
            }

        except Exception as e:
            logger.error("Failed to get performance trends: %s", e)
            return {"error": str(e)}


# Singleton instance (thread-safe)
import threading

_agent_analytics: Optional[AgentAnalytics] = None
_agent_analytics_lock = threading.Lock()


def get_agent_analytics() -> AgentAnalytics:
    """Get the singleton agent analytics instance (thread-safe)."""
    global _agent_analytics
    if _agent_analytics is None:
        with _agent_analytics_lock:
            # Double-check after acquiring lock
            if _agent_analytics is None:
                _agent_analytics = AgentAnalytics()
    return _agent_analytics
