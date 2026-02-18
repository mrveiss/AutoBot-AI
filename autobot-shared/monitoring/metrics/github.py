# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GitHub Metrics Recorder

Metrics for GitHub API operations.
Extracted from PrometheusMetricsManager as part of Issue #394.
"""

from typing import Optional

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class GitHubMetricsRecorder(BaseMetricsRecorder):
    """Recorder for GitHub operation metrics."""

    def _init_metrics(self) -> None:
        """Initialize GitHub metrics."""
        self.github_operations_total = Counter(
            "autobot_github_operations_total",
            "Total GitHub API operations",
            ["operation", "status"],
            registry=self.registry,
        )

        self.github_api_duration = Histogram(
            "autobot_github_api_duration_seconds",
            "GitHub API call duration in seconds",
            ["operation"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry,
        )

        self.github_rate_limit_remaining = Gauge(
            "autobot_github_rate_limit_remaining",
            "GitHub API rate limit remaining",
            ["resource_type"],
            registry=self.registry,
        )

        self.github_commits = Counter(
            "autobot_github_commits_total",
            "Total GitHub commits created",
            ["repository", "status"],
            registry=self.registry,
        )

        self.github_pull_requests = Counter(
            "autobot_github_pull_requests_total",
            "Total GitHub pull requests",
            ["repository", "action", "status"],
            registry=self.registry,
        )

        self.github_issues = Counter(
            "autobot_github_issues_total",
            "Total GitHub issues",
            ["repository", "action", "status"],
            registry=self.registry,
        )

    def record_operation(
        self, operation: str, status: str, duration: Optional[float] = None
    ) -> None:
        """Record a GitHub API operation."""
        self.github_operations_total.labels(operation=operation, status=status).inc()
        if duration is not None:
            self.github_api_duration.labels(operation=operation).observe(duration)

    def update_rate_limit(self, resource_type: str, remaining: int) -> None:
        """Update GitHub rate limit remaining."""
        self.github_rate_limit_remaining.labels(resource_type=resource_type).set(
            remaining
        )

    def record_commit(self, repository: str, status: str) -> None:
        """Record a GitHub commit."""
        self.github_commits.labels(repository=repository, status=status).inc()

    def record_pull_request(self, repository: str, action: str, status: str) -> None:
        """Record a GitHub pull request operation."""
        self.github_pull_requests.labels(
            repository=repository, action=action, status=status
        ).inc()

    def record_issue(self, repository: str, action: str, status: str) -> None:
        """Record a GitHub issue operation."""
        self.github_issues.labels(
            repository=repository, action=action, status=status
        ).inc()


__all__ = ["GitHubMetricsRecorder"]
