# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for branch health metrics (Issue #4112).

Tests branch divergence calculation, health scoring, and metrics collection.
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.time_utils import now_utc
from utils.branch_metrics import (
    BranchDivergence,
    BranchMetrics,
    BranchMetricsCollector,
    get_highly_diverged_branches,
    get_unhealthy_branches,
)


class TestBranchDivergence:
    """Test BranchDivergence dataclass."""

    def test_initialization(self):
        """Test divergence initialization."""
        div = BranchDivergence(branch="feature/test", ahead=5, behind=3)
        assert div.branch == "feature/test"
        assert div.ahead == 5
        assert div.behind == 3
        assert div.total_commits_diverged == 0  # Not set automatically

    def test_conflicting_files_default(self):
        """Test default empty conflicting files list."""
        div = BranchDivergence(branch="feature/test")
        assert div.conflicting_files == []


class TestBranchMetrics:
    """Test BranchMetrics dataclass."""

    def test_initialization(self):
        """Test metrics initialization."""
        div = BranchDivergence(branch="feature/test")
        metrics = BranchMetrics(
            branch="feature/test",
            divergence=div,
            health_score=75.0,
        )
        assert metrics.branch == "feature/test"
        assert metrics.health_score == 75.0
        assert metrics.is_stale is False

    def test_with_timestamps(self):
        """Test metrics with activity timestamps."""
        div = BranchDivergence(branch="feature/test")
        now = now_utc()
        metrics = BranchMetrics(
            branch="feature/test",
            divergence=div,
            last_activity=now,
            days_since_activity=0,
        )
        assert metrics.last_activity == now


class TestBranchMetricsCollector:
    """Test BranchMetricsCollector class."""

    @pytest.fixture
    def collector(self):
        """Create a collector instance."""
        return BranchMetricsCollector(
            repo_path="/tmp/test-repo",  # nosec B108 - test/controlled code uses tmpdir intentionally
            base_branch="Dev_new_gui",
            stale_threshold_days=30,
        )

    @pytest.mark.asyncio
    async def test_initialization(self, collector):
        """Test collector initialization."""
        assert collector.repo_path == "/tmp/test-repo"  # nosec B108 - test/controlled code uses tmpdir intentionally
        assert collector.base_branch == "Dev_new_gui"
        assert collector.stale_threshold_days == 30

    @pytest.mark.asyncio
    async def test_get_branch_divergence_success(self, collector):
        """Test successful divergence calculation."""
        with patch.object(collector, "_run_git_cmd") as mock_run:
            # Mock git responses
            async def mock_git_cmd(*args):
                if "ahead" in str(args):
                    return "5", 0
                elif "behind" in str(args):
                    return "3", 0
                return "", 1

            mock_run.side_effect = mock_git_cmd

            div = await collector.get_branch_divergence("feature/test")

            assert div.branch == "feature/test"
            assert div.ahead == 5
            assert div.behind == 3
            assert div.total_commits_diverged == 8

    @pytest.mark.asyncio
    async def test_get_branch_divergence_invalid_output(self, collector):
        """Test divergence with invalid git output."""
        with patch.object(collector, "_run_git_cmd") as mock_run:
            mock_run.return_value = ("invalid", 0)

            div = await collector.get_branch_divergence("feature/test")

            assert div.ahead == 0
            assert div.behind == 0

    @pytest.mark.asyncio
    async def test_get_all_branches(self, collector):
        """Test getting all branches."""
        with patch.object(collector, "_run_git_cmd") as mock_run:
            branch_output = "origin/Dev_new_gui\norigin/feature/test1\norigin/feature/test2"
            mock_run.return_value = (branch_output, 0)

            branches = await collector.get_all_branches()

            assert "Dev_new_gui" in branches
            assert "feature/test1" in branches
            assert "feature/test2" in branches
            assert len(branches) == 3

    @pytest.mark.asyncio
    async def test_get_all_branches_empty(self, collector):
        """Test getting branches with empty repo."""
        with patch.object(collector, "_run_git_cmd") as mock_run:
            mock_run.return_value = ("", 1)

            branches = await collector.get_all_branches()

            assert branches == []

    @pytest.mark.asyncio
    async def test_calculate_health_score(self, collector):
        """Test health score calculation."""
        # New branch, no divergence
        div = BranchDivergence(branch="feature/new", ahead=0, behind=0)
        score = collector._calculate_health_score(div, days_since_activity=0)
        assert score == 100.0

        # Branch with some behind commits
        div = BranchDivergence(branch="feature/old", ahead=0, behind=10)
        score = collector._calculate_health_score(div, days_since_activity=0)
        assert 50 < score < 100

        # Very old branch
        div = BranchDivergence(branch="feature/stale", ahead=0, behind=0)
        score = collector._calculate_health_score(div, days_since_activity=60)
        assert score < 100

    @pytest.mark.asyncio
    async def test_analyze_all_branches_skips_base(self, collector):
        """Test that analyze_all_branches skips base branch."""
        with (
            patch.object(collector, "get_all_branches") as mock_branches,
            patch.object(collector, "calculate_branch_health") as mock_health,
        ):
            # Setup
            mock_branches.return_value = ["Dev_new_gui", "feature/test"]
            mock_health.return_value = BranchMetrics(
                branch="feature/test",
                divergence=BranchDivergence(branch="feature/test"),
                health_score=75.0,
            )

            metrics = await collector.analyze_all_branches()

            # Should only analyze non-base branches
            assert len(metrics) == 1
            assert metrics[0].branch == "feature/test"


class TestModuleFunctions:
    """Test module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_get_unhealthy_branches(self):
        """Test get_unhealthy_branches function."""
        with patch("utils.branch_metrics.BranchMetricsCollector") as mock_collector_class:
            # Setup mock
            mock_collector = AsyncMock()
            mock_collector_class.return_value = mock_collector

            metrics1 = BranchMetrics(
                branch="good",
                divergence=BranchDivergence(branch="good"),
                health_score=75.0,
            )
            metrics2 = BranchMetrics(
                branch="bad",
                divergence=BranchDivergence(branch="bad"),
                health_score=30.0,
            )
            mock_collector.analyze_all_branches.return_value = [metrics1, metrics2]

            result = await get_unhealthy_branches(threshold=50.0)

            assert len(result) == 1
            assert result[0].branch == "bad"

    @pytest.mark.asyncio
    async def test_get_highly_diverged_branches(self):
        """Test get_highly_diverged_branches function."""
        with patch("utils.branch_metrics.BranchMetricsCollector") as mock_collector_class:
            # Setup mock
            mock_collector = AsyncMock()
            mock_collector_class.return_value = mock_collector

            metrics1 = BranchMetrics(
                branch="clean",
                divergence=BranchDivergence(branch="clean", total_commits_diverged=5),
                health_score=90.0,
            )
            metrics2 = BranchMetrics(
                branch="diverged",
                divergence=BranchDivergence(branch="diverged", total_commits_diverged=50),
                health_score=40.0,
            )
            mock_collector.analyze_all_branches.return_value = [metrics1, metrics2]

            result = await get_highly_diverged_branches(threshold=20)

            assert len(result) == 1
            assert result[0].branch == "diverged"
            assert result[0].divergence.total_commits_diverged == 50
