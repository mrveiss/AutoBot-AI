# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Branch Health and Divergence Metrics (Issue #4112).

Monitors branch health including divergence, file conflicts,
age, and activity to enable early detection of problematic branches.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from autobot_shared.time_utils import now_utc, parse_utc_iso

logger = get_logger(__name__)


@dataclass
class BranchDivergence:
    """Git branch divergence metrics."""

    branch: str
    ahead: int = 0
    behind: int = 0
    conflicting_files: List[str] = field(default_factory=list)
    total_commits_diverged: int = 0


@dataclass
class BranchMetrics:
    """Complete branch health metrics."""

    branch: str
    divergence: BranchDivergence
    created_at: datetime | None = None
    last_activity: datetime | None = None
    days_since_activity: float = 0
    file_conflict_density: float = 0.0
    is_stale: bool = False
    health_score: float = 0.0


class BranchMetricsCollector:
    """Collects and analyzes branch health metrics."""

    def __init__(
        self,
        repo_path: str | None = None,
        base_branch: str = "Dev_new_gui",
        stale_threshold_days: int = 30,
    ):
        """Initialize branch metrics collector."""
        self.repo_path = repo_path if repo_path is not None else str(config.path.code_source_path)
        self.base_branch = base_branch
        self.stale_threshold_days = stale_threshold_days

    async def _run_git_cmd(self, *args: str) -> Tuple[str, int]:
        """Run git command and return (output, returncode)."""
        cmd = ["git", "-C", self.repo_path, *args]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return stdout.decode(encoding="utf-8").strip(), proc.returncode
        except Exception as e:
            logger.error("Git command failed: %s", e)
            return "", 1

    async def get_branch_divergence(self, branch: str) -> BranchDivergence:
        """Calculate commits ahead/behind from base."""
        divergence = BranchDivergence(branch=branch)

        # Commits ahead
        ahead_out, ahead_code = await self._run_git_cmd("rev-list", "--count", f"{self.base_branch}..{branch}")
        if ahead_code == 0 and ahead_out:
            try:
                divergence.ahead = int(ahead_out)
            except ValueError:
                logger.warning("Failed to parse ahead count: %s", ahead_out)

        # Commits behind
        behind_out, behind_code = await self._run_git_cmd("rev-list", "--count", f"{branch}..{self.base_branch}")
        if behind_code == 0 and behind_out:
            try:
                divergence.behind = int(behind_out)
            except ValueError:
                logger.warning("Failed to parse behind count: %s", behind_out)

        divergence.total_commits_diverged = divergence.ahead + divergence.behind
        return divergence

    async def get_branch_last_activity(self, branch: str) -> datetime | None:
        """Get last commit timestamp on branch."""
        timestamp_out, code = await self._run_git_cmd("log", "-1", "--format=%ai", branch)

        if code == 0 and timestamp_out:
            try:
                return parse_utc_iso(timestamp_out)
            except (ValueError, AttributeError):
                logger.warning("Failed to parse activity time: %s", timestamp_out)

        return None

    async def get_all_branches(self) -> List[str]:
        """Get all remote branches."""
        branches_out, code = await self._run_git_cmd("branch", "-r", "--format=%(refname:short)")

        if code == 0 and branches_out:
            branches = [b.replace("origin/", "") for b in branches_out.split("\n") if b.strip() and "HEAD" not in b]
            return branches

        return []

    async def calculate_branch_health(self, branch: str) -> BranchMetrics:
        """Calculate health metrics for a branch."""
        divergence = await self.get_branch_divergence(branch)
        last_activity = await self.get_branch_last_activity(branch)

        now = now_utc()
        days_since_activity = 0
        if last_activity:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            days_since_activity = (now - last_activity).days

        is_stale = days_since_activity > self.stale_threshold_days
        health_score = self._calculate_health_score(divergence, days_since_activity)

        return BranchMetrics(
            branch=branch,
            divergence=divergence,
            last_activity=last_activity,
            days_since_activity=days_since_activity,
            is_stale=is_stale,
            health_score=health_score,
        )

    def _calculate_health_score(self, divergence: BranchDivergence, days_since_activity: int) -> float:
        """Calculate health score (0-100), higher is better."""
        score = 100.0

        # Penalize commits behind
        behind_penalty = min(50, (divergence.behind / 20) * 50)
        score -= behind_penalty

        # Penalize staleness
        stale_penalty = min(50, (days_since_activity / self.stale_threshold_days) * 50)
        score -= stale_penalty

        return max(0, score)

    async def analyze_all_branches(self) -> List[BranchMetrics]:
        """Analyze all branches and return sorted by health."""
        all_branches = await self.get_all_branches()
        branches_to_check = [b for b in all_branches if b != self.base_branch and "HEAD" not in b]

        metrics = []
        for branch in branches_to_check:
            try:
                metric = await self.calculate_branch_health(branch)
                metrics.append(metric)
            except Exception as e:
                logger.error("Failed to calculate health for %s: %s", branch, e)

        metrics.sort(key=lambda m: m.health_score)
        return metrics


async def get_unhealthy_branches(
    repo_path: str | None = None,
    base_branch: str = "Dev_new_gui",
    health_threshold: float = 50.0,
) -> List[BranchMetrics]:
    """Get branches with health scores below threshold."""
    collector = BranchMetricsCollector(repo_path, base_branch)
    all_metrics = await collector.analyze_all_branches()
    return [m for m in all_metrics if m.health_score < health_threshold]


async def get_highly_diverged_branches(
    repo_path: str | None = None,
    base_branch: str = "Dev_new_gui",
    threshold: int = 20,
) -> List[BranchMetrics]:
    """Get branches with high divergence from base."""
    collector = BranchMetricsCollector(repo_path, base_branch)
    all_metrics = await collector.analyze_all_branches()
    diverged = [m for m in all_metrics if m.divergence.total_commits_diverged > threshold]
    diverged.sort(key=lambda m: m.divergence.total_commits_diverged, reverse=True)
    return diverged
